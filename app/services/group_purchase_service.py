"""Group purchase validation, authorization, allocation, and lifecycle ownership."""
from contextlib import contextmanager
from datetime import date
import math
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
from app.repositories.group_purchase_repo import GroupPurchaseRepository
from app.db.transactions import write_transaction


def _component_names(raw_components):
    """Return unique, non-empty component names while preserving their order."""
    names = []
    seen = set()
    for line in raw_components.splitlines():
        name = line.strip()
        key = name.casefold()
        if name and key not in seen:
            names.append(name)
            seen.add(key)
    return names


def _component_specs(raw_components):
    """Parse ``name | unit price`` lines; the price is optional."""
    specs = []
    seen = set()
    for line in raw_components.splitlines():
        value = line.strip()
        if not value:
            continue
        name, separator, raw_price = value.rpartition("|")
        if separator:
            name = name.strip()
            try:
                unit_price = round(float(raw_price.strip().replace(",", ".")), 2)
            except ValueError as exc:
                raise ValueError("Invalid component price") from exc
        else:
            name = value
            unit_price = 0
        if not name or len(name) > 100 or unit_price < 0 or unit_price > 1000000:
            raise ValueError("Invalid component name or price")
        key = name.casefold()
        if key not in seen:
            specs.append((name, unit_price))
            seen.add(key)
    return specs


def _component_specs_from_fields(names, prices):
    """Validate component rows submitted by the purchase form."""
    lines = []
    for index, name in enumerate(names):
        price = prices[index] if index < len(prices) else ""
        if name.strip() or price.strip():
            lines.append(f"{name} | {price or '0'}")
    return _component_specs("\n".join(lines))


def _shared_cost_specs(labels, amounts):
    """Validate shared costs such as shipping, customs, or taxes."""
    costs = []
    for index, label in enumerate(labels):
        amount = amounts[index] if index < len(amounts) else ""
        if not label.strip() and not amount.strip():
            continue
        try:
            value = round(float(amount.strip().replace(",", ".")), 2)
        except ValueError as exc:
            raise ValueError("Invalid shared cost") from exc
        label = label.strip()
        if not label or len(label) > 100 or value < 0 or value > 1000000:
            raise ValueError("Invalid shared cost")
        costs.append((label, value))
    if len(costs) > 20:
        raise ValueError("A group purchase can have at most 20 shared costs")
    return costs


def _allocate_shared_costs(debts, shared_cost_total):
    """Add proportional shared-cost and total fields to participant debts."""
    selection_total = sum(debt["selection_amount"] for debt in debts)
    allocated = 0.0
    for index, debt in enumerate(debts):
        percentage = debt["selection_amount"] / selection_total if selection_total else 0
        debt["selection_percentage"] = percentage * 100
        if selection_total and index == len(debts) - 1:
            debt["shared_cost_share"] = round(shared_cost_total - allocated, 2)
        else:
            debt["shared_cost_share"] = round(shared_cost_total * percentage, 2)
            allocated += debt["shared_cost_share"]
        debt["amount_owed"] = round(debt["selection_amount"] + debt["shared_cost_share"], 2)
    return debts


def _valid_product_url(url):
    if not url:
        return True
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _valid_deadline(deadline):
    try:
        date.fromisoformat(deadline)
        return True
    except ValueError:
        return False


@contextmanager
def _transaction(connection):
    try:
        yield
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def manageable_purchase(connection, purchase_id, member_id, is_admin=False):
    purchase = GroupPurchaseRepository(connection).get_by_id(purchase_id)
    if purchase is not None and (purchase['created_by'] == member_id or is_admin):
        return purchase
    return None


def validate_creation(*, title, components, deadline, product_url, payment_method, component_error, shared_cost_error):
    if component_error:
        return component_error
    if shared_cost_error:
        return shared_cost_error
    if not title or not components:
        return 'Add a title and at least one component'
    if len(title) > 150:
        return 'The title or a component is too long'
    if len(components) > 30:
        return 'A group purchase can have at most 30 components'
    if deadline and not _valid_deadline(deadline):
        return 'Invalid deadline'
    if not _valid_product_url(product_url):
        return 'Invalid URL'
    if len(payment_method) > 250:
        return 'Payment method is too long'
    return None


def validate_edit(*, title, deadline, product_url, payment_method, invalid_component, shared_cost_error):
    if not title or len(title) > 150:
        return 'Invalid title'
    if deadline and not _valid_deadline(deadline):
        return 'Invalid deadline'
    if not _valid_product_url(product_url):
        return 'Invalid URL'
    if len(payment_method) > 250:
        return 'Payment method is too long'
    if invalid_component:
        return 'Invalid component name or price'
    return shared_cost_error


def component_updates(purchase_id, components, values):
    updates = []
    for component, (name, raw_price) in zip(components, values):
        name = name.strip()
        try:
            price = round(float(raw_price), 2)
        except (TypeError, ValueError):
            return [], True
        if not name or len(name) > 100 or price < 0 or price > 1000000:
            return [], True
        updates.append((name, price, component['id'], purchase_id))
    return updates, False


def create_purchase(connection, *, title, description, deadline, product_url, image_filename,
                    payment_method, member_id, components, shared_costs, join_member_limit=None, cap_at_125=False):
    join_member_limit = parse_join_member_limit(join_member_limit)
    error = validate_creation(title=title, components=components, deadline=deadline, product_url=product_url,
                              payment_method=payment_method, component_error=None, shared_cost_error=None)
    if error:
        raise ValueError(error)
    repo = GroupPurchaseRepository(connection)
    with _transaction(connection):
        purchase_id = repo.create(title, description, deadline, product_url, image_filename, payment_method, member_id)
        repo.set_join_limit(purchase_id, join_member_limit)
        repo.set_amount_cap(purchase_id, cap_at_125)
        repo.insert_components(purchase_id, components)
        repo.insert_shared_costs(purchase_id, shared_costs)
        enforce_purchase_limits(repo, purchase_id)
    return purchase_id


def build_purchase_page(connection, member_id):
    repo = GroupPurchaseRepository(connection)
    purchases = [dict(row) for row in repo.list_with_creators()]
    for purchase in purchases:
        purchase['components'] = [dict(row) for row in repo.component_totals(purchase['id'])]
        for component in purchase['components']:
            component['orders'] = [dict(row) for row in repo.orders(component['id'])]
            component['user_quantity'] = next((o['quantity'] for o in component['orders'] if o['member_id'] == member_id), 0)
        purchase['shared_costs'] = [dict(row) for row in repo.shared_costs(purchase['id'])]
        purchase['shared_cost_total'] = sum(c['amount'] for c in purchase['shared_costs'])
        purchase['order_total'] = purchase_amount(repo.selected_prices(purchase['id']), [(c['label'], c['amount']) for c in purchase['shared_costs']])
        purchase['debts'] = [dict(row) for row in repo.debts(purchase['id'])]
        purchase['joined_members'] = len(purchase['debts'])
        _allocate_shared_costs(purchase['debts'], purchase['shared_cost_total'])
    return purchases


def set_quantity(connection, *, purchase_id, component_id, member_id, quantity):
    if component_id is None or quantity is None or quantity < 0 or quantity > 999:
        raise ValueError('Quantity must be between 0 and 999')
    repo = GroupPurchaseRepository(connection)
    with write_transaction(connection):
        if repo.open_component(purchase_id, component_id) is None:
            raise ValueError('Component not found')
        repo.set_quantity(component_id, member_id, quantity)
        enforce_purchase_limits(repo, purchase_id)


def purchase_amount(prices, shared_costs, updates=()):
    replacements = {row[2]: row[1] for row in updates}
    def money(value):
        try:
            result = Decimal(str(value))
            if not result.is_finite() or result < 0:
                raise ValueError('Invalid component name or price')
            return result.quantize(Decimal('0.01'))
        except (InvalidOperation, TypeError):
            raise ValueError('Invalid component name or price') from None
    return sum((money(replacements.get(row['id'], row['unit_price'])) * row['quantity'] for row in prices), Decimal('0')) + sum((money(amount) for _, amount in shared_costs), Decimal('0'))


def validate_amount_cap(total, enabled):
    if enabled and total > Decimal('125.00'):
        raise ValueError('This order cannot exceed €125 including shared costs. Reduce quantities or costs.')


def enforce_purchase_limits(repo, purchase_id):
    purchase = repo.get_by_id(purchase_id)
    if purchase['cap_at_125']:
        total = purchase_amount(repo.selected_prices(purchase_id), [(r['label'], r['amount']) for r in repo.shared_costs(purchase_id)])
        validate_amount_cap(total, True)
        if total == Decimal('125.00') and purchase['status'] == 'open':
            repo.set_status(purchase_id, 'closed')
    repo.close_at_join_limit(purchase_id)


def parse_join_member_limit(value):
    if value is None or value == '':
        return None
    if isinstance(value, bool) or not str(value).isascii() or not str(value).isdigit() or not 1 <= int(value) <= 10000:
        raise ValueError('Member limit must be between 1 and 10000')
    return int(value)


def validate_component_additions(updates, names, prices):
    additions = []
    seen = {row[0].casefold() for row in updates}
    if len(names) != len(prices):
        raise ValueError('Invalid component name or price')
    for name, raw_price in zip(names, prices):
        name = name.strip()
        if not name and not raw_price.strip():
            continue
        try:
            price = round(float(raw_price), 2)
        except (TypeError, ValueError):
            raise ValueError('Invalid component name or price') from None
        if not name or len(name) > 100 or not math.isfinite(price) or not 0 <= price <= 1000000:
            raise ValueError('Invalid component name or price')
        if name.casefold() in seen:
            raise ValueError('Duplicate component name')
        seen.add(name.casefold())
        additions.append((name, price))
    if len(updates) + len(additions) > 30:
        raise ValueError('A group purchase can have at most 30 components')
    return additions


def edit_purchase(connection, *, purchase_id, member_id, is_admin, title, description,
                  deadline, product_url, image_filename, payment_method, updates, shared_costs,
                  new_components=(), join_member_limit=None, cap_at_125=None):
    join_member_limit = parse_join_member_limit(join_member_limit)
    if manageable_purchase(connection, purchase_id, member_id, is_admin) is None:
        raise ValueError('Only the creator or an admin can edit this group purchase')
    repo = GroupPurchaseRepository(connection)
    with _transaction(connection):
        additions = validate_component_additions(
            updates, [name for name, _ in new_components], [str(price) for _, price in new_components],
        )
        existing = repo.components(purchase_id)
        if len(existing) + len(additions) > 30:
            raise ValueError('A group purchase can have at most 30 components')
        repo.update(purchase_id, title, description, deadline, product_url, image_filename, payment_method)
        repo.set_join_limit(purchase_id, join_member_limit)
        if cap_at_125 is not None:
            repo.set_amount_cap(purchase_id, cap_at_125)
        repo.update_components(updates)
        repo.insert_components(purchase_id, additions, start_position=max((row['position'] for row in existing), default=-1) + 1)
        repo.delete_shared_costs(purchase_id)
        repo.insert_shared_costs(purchase_id, shared_costs)
        enforce_purchase_limits(repo, purchase_id)


def delete_purchase(connection, *, purchase_id, member_id, is_admin):
    purchase = manageable_purchase(connection, purchase_id, member_id, is_admin)
    if purchase is None:
        raise ValueError('Only the creator or an admin can delete this group purchase')
    with _transaction(connection):
        GroupPurchaseRepository(connection).delete(purchase_id)
    return purchase


def update_status(connection, *, purchase_id, member_id, status):
    purchase = manageable_purchase(connection, purchase_id, member_id)
    if purchase is None or {'open': 'ordered', 'closed': 'ordered', 'ordered': 'received'}.get(purchase['status']) != status:
        raise ValueError('Invalid status change')
    with _transaction(connection):
        GroupPurchaseRepository(connection).set_status(purchase_id, status)
    return purchase


def update_payment(connection, *, purchase_id, member_id, actor_id, received):
    repo = GroupPurchaseRepository(connection)
    if manageable_purchase(connection, purchase_id, actor_id) is None or not repo.is_participant(purchase_id, member_id):
        raise ValueError('Payment cannot be updated')
    with _transaction(connection):
        repo.set_payment(purchase_id, member_id, received)
