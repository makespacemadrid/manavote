import json
import sqlite3

import pytest

from app import app
from app.db.connection import set_db_path
from app.services.coin_service import CoinValidationError, record_movement
from app.web.routes import main_routes
from app import mcp_server


@pytest.fixture
def coin_client(tmp_path, monkeypatch):
    db_path = tmp_path / "coins.db"
    previous_db_path = main_routes.DB_PATH
    monkeypatch.setattr(main_routes, "DB_PATH", str(db_path))
    set_db_path(str(db_path))
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    main_routes.init_db()
    client = app.test_client()
    with client.session_transaction() as user_session:
        user_session.update(member_id=1, username="admin", is_admin=1, lang="en")
    try:
        yield client, db_path
    finally:
        set_db_path(previous_db_path)


def test_seeded_items_and_web_ledger_actions(coin_client):
    client, db_path = coin_client
    response = client.get("/koins")
    assert response.status_code == 200
    assert client.get("/coins").status_code == 404
    assert b"Koins" in response.data
    assert b"Consuming one can debits one koin. Replenishing one can credits one koin." in response.data
    assert b"Coke Zero" in response.data
    assert b"I bought 12" in response.data
    assert b"Manage koin items" not in response.data
    assert b'href="/admin/koins/qr-labels"' not in response.data

    with sqlite3.connect(db_path) as connection:
        coke_id = connection.execute("SELECT id FROM coin_items WHERE name = 'Coke'").fetchone()[0]
    response = client.post("/koins/move", data={"item_id": coke_id, "action": "consume", "quantity": 1, "idempotency_key": "consume-once"})
    assert response.status_code == 302
    client.post("/koins/move", data={"item_id": coke_id, "action": "replenish", "quantity": 12, "idempotency_key": "buy-twelve"})

    with sqlite3.connect(db_path) as connection:
        stock, balance, count = connection.execute(
            "SELECT SUM(inventory_delta), SUM(coin_delta), COUNT(*) FROM coin_movements"
        ).fetchone()
    assert (stock, balance, count) == (11, 11, 2)
    page = client.get("/koins")
    assert b"Other quantity" in page.data
    assert b"Consume quantity" in page.data


def test_idempotency_and_quantity_validation(coin_client):
    _, db_path = coin_client
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    first = record_movement(connection, item="Coke", member_id=1, action="replenish", quantity=12, idempotency_key="same")
    replay = record_movement(connection, item="Coke", member_id=1, action="replenish", quantity=12, idempotency_key="same")
    assert first["movement_id"] == replay["movement_id"]
    assert replay["replayed"] is True
    assert connection.execute("SELECT COUNT(*) FROM coin_movements").fetchone()[0] == 1
    with pytest.raises(CoinValidationError):
        record_movement(connection, item="Coke", member_id=1, action="consume", quantity=0)
    connection.close()


def test_coins_page_ranks_balances_and_shows_lifetime_totals(coin_client):
    client, db_path = coin_client
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO members (username, password_hash) VALUES ('debtor', 'x')")
        debtor_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.row_factory = sqlite3.Row
        record_movement(connection, item="Coke", member_id=1, action="replenish", quantity=8)
        record_movement(connection, item="Coke", member_id=1, action="consume", quantity=3)
        record_movement(connection, item="Coke Zero", member_id=debtor_id, action="consume", quantity=7)

    page = client.get("/koins")
    assert page.status_code == 200
    assert b"Koin credit &amp; debts per member" in page.data
    assert b"Total consumed" in page.data
    assert b"Total purchased" in page.data
    assert b"data-sortable-table" in page.data
    ranking_html = page.data[page.data.index(b"Koin credit &amp; debts per member") :]
    assert ranking_html.index(b">debtor<") < ranking_html.index(b">admin<")
    assert b'data-sort-type="number" aria-sort="descending">Balance' in page.data
    assert b'data-sort-value="5" class="amount-positive">+5</td><td>3</td><td>8</td>' in page.data
    assert b'data-sort-value="7" class="amount-negative">-7</td><td>7</td><td>0</td>' in page.data


def test_coin_item_cards_show_lifetime_consumed_and_purchased_totals(coin_client):
    client, db_path = coin_client
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        record_movement(connection, item="Coke", member_id=1, action="replenish", quantity=8)
        record_movement(connection, item="Coke", member_id=1, action="consume", quantity=3)

    page = client.get("/koins")

    assert b"In stock" not in page.data
    assert b"Total consumed: <strong>3</strong>, Total purchased: <strong>8</strong>" in page.data
    assert b"Consumption by item" in page.data
    summary = page.data.split(b"Consumption by item", 1)[1].split(b"Koin credit &amp; debts per member", 1)[0]
    assert b"Coke" in summary
    assert b">3</td>" in summary


def test_admin_can_edit_coin_ledger_entry(coin_client):
    client, db_path = coin_client
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        movement_id = record_movement(connection, item="Coke", member_id=1, action="consume", quantity=2)["movement_id"]

    page = client.get("/admin?tab=coins")
    assert b"Edit koin ledger" in page.data
    assert page.data.count(b'<span aria-hidden="true">') == 7
    assert f'action="/admin/koins/movements/{movement_id}"'.encode() in page.data

    response = client.post(
        f"/admin/koins/movements/{movement_id}",
        data={"item_id": 2, "member_id": 1, "kind": "replenish", "quantity": 5, "note": "Corrected receipt"},
        follow_redirects=True,
    )
    assert b"Koin movement updated" in response.data
    with sqlite3.connect(db_path) as connection:
        movement = connection.execute(
            "SELECT item_id, inventory_delta, coin_delta, kind, source, note FROM coin_movements WHERE id = ?",
            (movement_id,),
        ).fetchone()
    assert movement == (2, 5, 5, "replenish", "admin", "Corrected receipt")


def test_admin_printable_qr_labels_and_png(coin_client):
    client, _ = coin_client
    response = client.get("/admin/koins/qr-labels")
    assert response.status_code == 200
    assert response.data.count(b'class="qr-label"') == 3
    assert b"debits 1 koin" in response.data
    assert response.data.count(b"Debit from my account") == 3
    assert b"Pay later" not in response.data
    assert b">Consume</h2>" not in response.data
    assert b">Replenish</h2>" not in response.data
    assert b"/koins/scan/" not in response.data
    assert b"Coke Zero" in response.data
    token_path = response.data.split(b'/koins/qr/', 1)[1].split(b'.png', 1)[0].decode()
    png = client.get(f"/koins/qr/{token_path}.png")
    assert png.status_code == 200
    assert png.mimetype == "image/png"
    assert png.data.startswith(b"\x89PNG")

    with client.session_transaction() as user_session:
        user_session["lang"] = "es"
    spanish_response = client.get("/admin/koins/qr-labels")
    assert b"koins" in spanish_response.data
    assert spanish_response.data.count("Restar de mi crédito".encode()) == 3


def test_qr_uses_configured_public_base_url(coin_client):
    client, db_path = coin_client
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('url', 'https://vote.example')")
        connection.commit()
    response = client.get("/admin/koins/qr-labels")
    assert b"https://vote.example/koins/scan/" not in response.data
    token = response.data.split(b'/koins/qr/', 1)[1].split(b'.png', 1)[0].decode()
    # Inspect the URL helper directly; PNG generation itself is covered above.
    from app.web.routes.coin_routes import _public_scan_url
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    with app.test_request_context():
        assert _public_scan_url(connection, token).startswith("https://vote.example/koins/scan/")
    connection.close()


def test_non_admin_cannot_print_or_manage_qr_labels(coin_client):
    client, _ = coin_client
    with client.session_transaction() as user_session:
        user_session["is_admin"] = 0
    assert client.get("/admin/koins/qr-labels").status_code == 302
    assert client.post("/admin/koins/adjust", data={"item_id": 1, "inventory_delta": 1}).status_code == 302
    assert client.post("/admin/koins/items", data={"name": "Icecream", "pack_size": 8}).status_code == 302
    assert client.post("/admin/koins/items/1", data={"name": "Cola", "pack_size": 6}).status_code == 302
    assert client.post("/admin/koins/items/1/delete").status_code == 302
    assert client.post("/admin/koins/movements/1", data={}).status_code == 302


def test_admin_can_adjust_stock_without_changing_balance(coin_client):
    client, db_path = coin_client
    client.post("/admin/koins/adjust", data={"item_id": 1, "inventory_delta": -3, "note": "count", "idempotency_key": "adjust-once"})
    with sqlite3.connect(db_path) as connection:
        movement = connection.execute("SELECT inventory_delta, coin_delta, kind FROM coin_movements").fetchone()
    assert movement == (-3, 0, "adjustment")


def test_admin_can_create_item_with_custom_pack_size(coin_client):
    client, db_path = coin_client
    response = client.post(
        "/admin/koins/items",
        data={"name": "Icecream Minis mix", "pack_size": 8},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Koin item created" in response.data
    assert response.data.count(b'class="qr-label"') == 4
    page = client.get("/koins")
    assert b"Icecream Minis mix" in page.data
    assert b"I bought 8" in page.data
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT pack_size, position FROM coin_items WHERE name = 'Icecream Minis mix'"
        ).fetchone()
        token_count = connection.execute(
            "SELECT COUNT(*) FROM coin_qr_tokens qt JOIN coin_items ci ON ci.id = qt.item_id WHERE ci.name = 'Icecream Minis mix'"
        ).fetchone()[0]
    assert row == (8, 3)
    assert token_count == 1


def test_admin_coins_section_has_item_creation_and_printable_qrs(coin_client):
    client, db_path = coin_client
    page = client.get("/admin?tab=coins")

    assert page.status_code == 200
    assert b'data-section="coins"' in page.data
    assert b'id="coins" class="card"' in page.data
    assert b"View and print QR labels" in page.data
    assert b'href="/admin/koins/qr-labels"' in page.data
    assert b'action="/admin/koins/items"' in page.data
    assert page.data.index(b'data-section="coins"') < page.data.index(b'data-section="group_purchases"')
    assert b'name="pack_size"' in page.data
    assert b"Edit koin items" in page.data
    assert b"Default purchase amount" in page.data
    assert b'action="/admin/koins/items/1"' in page.data
    assert b'class="coin-admin-items"' in page.data
    assert b'class="coin-admin-edit-form"' in page.data
    assert b'class="coin-admin-delete-form"' in page.data

    response = client.post(
        "/admin/koins/items",
        data={"name": "Icecream Minis mix", "pack_size": 8, "return_to": "admin"},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin?tab=coins")
    with sqlite3.connect(db_path) as connection:
        assert connection.execute(
            "SELECT pack_size FROM coin_items WHERE name = 'Icecream Minis mix'"
        ).fetchone() == (8,)


def test_admin_item_creation_rejects_duplicates_and_bad_pack_sizes(coin_client):
    client, db_path = coin_client
    duplicate = client.post(
        "/admin/koins/items", data={"name": "coke", "pack_size": 8}, follow_redirects=True
    )
    assert b"An item with that name already exists" in duplicate.data
    invalid = client.post(
        "/admin/koins/items", data={"name": "Icecream", "pack_size": 0}, follow_redirects=True
    )
    assert b"Pack size must be between 1 and 1000" in invalid.data
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM coin_items").fetchone()[0] == 3


def test_admin_can_edit_item_name_and_default_purchase_amount(coin_client):
    client, db_path = coin_client

    response = client.post(
        "/admin/koins/items/1",
        data={"name": "Club Cola", "pack_size": 6},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Koin item updated" in response.data
    with sqlite3.connect(db_path) as connection:
        assert connection.execute(
            "SELECT name, pack_size FROM coin_items WHERE id = 1"
        ).fetchone() == ("Club Cola", 6)
    page = client.get("/koins")
    assert b"Club Cola" in page.data
    assert b"I bought 6" in page.data


def test_renamed_default_item_is_not_recreated_on_restart(coin_client):
    client, db_path = coin_client
    response = client.post(
        "/admin/koins/items/1",
        data={"name": "Club Cola", "pack_size": 6},
        follow_redirects=True,
    )
    assert response.status_code == 200

    # Running migrations models the next application startup.
    main_routes.init_db()

    with sqlite3.connect(db_path) as connection:
        names = [row[0] for row in connection.execute("SELECT name FROM coin_items ORDER BY id")]
    assert names == ["Club Cola", "Coke Zero", "Other Can"]


def test_admin_can_delete_item_without_losing_movement_history(coin_client):
    client, db_path = coin_client
    client.get("/admin/koins/qr-labels")
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        record_movement(connection, item="Coke", member_id=1, action="consume", quantity=2)

    response = client.post("/admin/koins/items/1/delete", follow_redirects=True)

    assert response.status_code == 200
    assert b"Koin item deleted" in response.data
    assert b'action="/admin/koins/items/1"' not in response.data
    assert b'action="/admin/koins/items/1/delete"' not in response.data
    assert b"Coke Zero" in response.data
    assert b'id="coin-item-1"' not in client.get("/koins").data
    with sqlite3.connect(db_path) as connection:
        active, movement_count = connection.execute(
            """SELECT ci.active, COUNT(cm.id)
               FROM coin_items ci LEFT JOIN coin_movements cm ON cm.item_id = ci.id
               WHERE ci.id = 1 GROUP BY ci.id"""
        ).fetchone()
        token_states = connection.execute(
            "SELECT DISTINCT active FROM coin_qr_tokens WHERE item_id = 1"
        ).fetchall()
    assert (active, movement_count) == (0, 1)
    assert token_states == [(0,)]


def test_admin_item_edit_rejects_duplicate_name_and_invalid_amount(coin_client):
    client, db_path = coin_client

    duplicate = client.post(
        "/admin/koins/items/1",
        data={"name": "Coke Zero", "pack_size": 6},
        follow_redirects=True,
    )
    invalid = client.post(
        "/admin/koins/items/1",
        data={"name": "Club Cola", "pack_size": 0},
        follow_redirects=True,
    )

    assert b"An item with that name already exists" in duplicate.data
    assert b"Pack size must be between 1 and 1000" in invalid.data
    with sqlite3.connect(db_path) as connection:
        assert connection.execute(
            "SELECT name, pack_size FROM coin_items WHERE id = 1"
        ).fetchone() == ("Coke", 12)


def test_admin_can_disable_and_rotate_qr_token(coin_client):
    client, db_path = coin_client
    client.get("/admin/koins/qr-labels")
    with sqlite3.connect(db_path) as connection:
        item_id, action, old_token = connection.execute("SELECT item_id, action, token FROM coin_qr_tokens LIMIT 1").fetchone()
    client.post(f"/admin/koins/qr-tokens/{item_id}/{action}", data={"operation": "disable"})
    assert client.get(f"/koins/scan/{old_token}").status_code == 404
    client.post(f"/admin/koins/qr-tokens/{item_id}/{action}", data={"operation": "rotate"})
    with sqlite3.connect(db_path) as connection:
        new_token, active = connection.execute("SELECT token, active FROM coin_qr_tokens WHERE item_id = ? AND action = ?", (item_id, action)).fetchone()
    assert new_token != old_token
    assert active == 1


def test_replenish_qr_tokens_are_removed_and_rejected(coin_client):
    client, db_path = coin_client
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO coin_qr_tokens (token, item_id, action) VALUES ('old-replenish', 1, 'replenish')"
        )
        connection.commit()

    response = client.get("/admin/koins/qr-labels")

    assert b"old-replenish" not in response.data
    with sqlite3.connect(db_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM coin_qr_tokens WHERE action = 'replenish'"
        ).fetchone()[0] == 0
    assert client.get("/koins/scan/old-replenish").status_code == 404
    assert client.post("/admin/koins/qr-tokens/1/replenish", data={"operation": "rotate"}).status_code == 404


def test_scan_requires_login_then_returns_after_login(coin_client):
    client, db_path = coin_client
    client.get("/admin/koins/qr-labels")
    with sqlite3.connect(db_path) as connection:
        token = connection.execute("SELECT token FROM coin_qr_tokens LIMIT 1").fetchone()[0]
    with client.session_transaction() as user_session:
        user_session.clear()
    response = client.get(f"/koins/scan/{token}")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    with client.session_transaction() as user_session:
        assert user_session["login_next"] == f"/koins/scan/{token}"


def test_mcp_lists_and_records_coin_actions(coin_client, monkeypatch):
    _, db_path = coin_client
    monkeypatch.setattr(mcp_server, "DB_PATH", str(db_path))
    listed = mcp_server.execute_tool_command("list_coin_items", {"member_id": 1})
    payload = json.loads(listed["result"]["content"][0]["text"])
    assert [item["name"] for item in payload["items"]] == ["Coke", "Coke Zero", "Other Can"]
    recorded = mcp_server.execute_tool_command(
        "consume_coin_item", {"item": "Coke Zero", "member_id": 1, "quantity": 1}
    )
    result = json.loads(recorded["result"]["content"][0]["text"])
    assert result["coin_delta"] == -1
    assert result["resulting_coin_balance"] == -1
    history = mcp_server.execute_tool_command("list_coin_movements", {"member_id": 1})
    history_payload = json.loads(history["result"]["content"][0]["text"])
    assert history_payload["count"] == 1
    assert history_payload["movements"][0]["item_name"] == "Coke Zero"
    invalid = mcp_server.execute_tool_command("list_coin_movements", {"member_id": "1"})
    assert invalid["error"]["code"] == -32602


def test_api_and_mcp_user_statistics_include_detailed_coin_usage(coin_client, monkeypatch):
    client, db_path = coin_client
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        record_movement(connection, item="Coke", member_id=1, action="replenish", quantity=12)
        record_movement(connection, item="Coke", member_id=1, action="consume", quantity=2)
        record_movement(connection, item="Coke Zero", member_id=1, action="consume", quantity=3)

    monkeypatch.setattr(main_routes, "ADMIN_API_KEY", "statistics-key")
    monkeypatch.setattr(mcp_server, "DB_PATH", str(db_path))
    api_response = client.get(
        "/api/members/statistics",
        headers={"X-Admin-Key": "statistics-key"},
    )
    mcp_response = mcp_server.execute_tool_command(
        "list_user_statistics", {"username": "admin"}
    )

    assert api_response.status_code == 200
    api_user = next(user for user in api_response.get_json()["users"] if user["id"] == 1)
    mcp_user = json.loads(mcp_response["result"]["content"][0]["text"])["users"][0]
    expected_coin_usage = {
        "coin_balance": 7,
        "coins_earned": 12,
        "coins_spent": 5,
        "beverages_consumed": 5,
        "beverages_replenished": 12,
        "beverage_consumption": [
            {"item_id": 1, "item_name": "Coke", "consumed": 2, "replenished": 12},
            {"item_id": 2, "item_name": "Coke Zero", "consumed": 3, "replenished": 0},
        ],
    }
    assert {key: api_user[key] for key in expected_coin_usage} == expected_coin_usage
    assert {key: mcp_user[key] for key in expected_coin_usage} == expected_coin_usage


def test_recent_history_includes_all_members_and_return_redirect_is_local(coin_client):
    client, db_path = coin_client
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO members (username, password_hash) VALUES ('other', 'x')")
        other_id = connection.execute("SELECT id FROM members WHERE username = 'other'").fetchone()[0]
        connection.row_factory = sqlite3.Row
        record_movement(connection, item="Coke", member_id=1, action="replenish", quantity=3)
        record_movement(connection, item="Coke", member_id=other_id, action="consume")
    with client.session_transaction() as user_session:
        user_session.update(member_id=other_id, username="other", is_admin=0)
    page = client.get("/koins")
    assert b">other<" in page.data  # Public aggregate ranking includes every member.
    history = page.data.split(b"Recent koin movements", 1)[1]
    assert b">other<" in history
    assert b">admin<" in history
    assert history.index(b">other<") < history.index(b">admin<")
    assert b"Your koin balance: -1" in page.data
    response = client.post("/koins/move", data={"item_id": 1, "action": "consume", "quantity": 1, "return_to": "https://evil.example"})
    assert response.headers["Location"].endswith("/koins")


def test_admin_mcp_coin_actions_target_another_member_and_replay_safely(coin_client, monkeypatch):
    _, db_path = coin_client
    monkeypatch.setattr(mcp_server, "DB_PATH", str(db_path))
    with sqlite3.connect(db_path) as conn:
        target = conn.execute("INSERT INTO members (username, password_hash) VALUES ('koin-target', 'unused')").lastrowid
    for name, quantity, delta in [("admin_replenish_coin_item", 5, 5), ("admin_consume_coin_item", 2, -2)]:
        arguments = {"item": "Coke", "member_id": target, "quantity": quantity, "idempotency_key": name}
        result = mcp_server.execute_tool_command(name, arguments)
        payload = json.loads(result["result"]["content"][0]["text"])
        assert payload["coin_delta"] == delta
        replay = mcp_server.execute_tool_command(name, arguments)
        assert json.loads(replay["result"]["content"][0]["text"])["replayed"] is True
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT SUM(coin_delta), COUNT(*) FROM coin_movements WHERE member_id = ?", (target,)).fetchone() == (3, 2)
        assert conn.execute("SELECT COUNT(*) FROM coin_movements WHERE member_id = 1").fetchone()[0] == 0
    for invalid in ({"member_id": target}, {"member_id": True, "quantity": 1}, {"member_id": target, "quantity": 1.5}):
        result = mcp_server.execute_tool_command("admin_consume_coin_item", {"item": "Coke", **invalid})
        assert result["error"]["code"] == -32602
