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
    response = client.get("/coins")
    assert response.status_code == 200
    assert b"Coke Zero" in response.data
    assert b"I bought 12" in response.data
    assert b"Manage coin items" in response.data
    assert b'href="/admin/coins/qr-labels"' in response.data

    with sqlite3.connect(db_path) as connection:
        coke_id = connection.execute("SELECT id FROM coin_items WHERE name = 'Coke'").fetchone()[0]
    response = client.post("/coins/move", data={"item_id": coke_id, "action": "consume", "quantity": 1, "idempotency_key": "consume-once"})
    assert response.status_code == 302
    client.post("/coins/move", data={"item_id": coke_id, "action": "replenish", "quantity": 12, "idempotency_key": "buy-twelve"})

    with sqlite3.connect(db_path) as connection:
        stock, balance, count = connection.execute(
            "SELECT SUM(inventory_delta), SUM(coin_delta), COUNT(*) FROM coin_movements"
        ).fetchone()
    assert (stock, balance, count) == (11, 11, 2)
    page = client.get("/coins")
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
        record_movement(connection, item="Coke Zero", member_id=debtor_id, action="consume", quantity=2)

    page = client.get("/coins")
    assert page.status_code == 200
    assert b"Coin ranking" in page.data
    assert b"Total consumed" in page.data
    assert b"Total bought" in page.data
    assert page.data.index(b">admin<") < page.data.index(b">debtor<")
    assert b'<td class="amount-positive">+5</td><td>3</td><td>8</td>' in page.data
    assert b'<td class="amount-negative">-2</td><td>2</td><td>0</td>' in page.data


def test_admin_printable_qr_labels_and_png(coin_client):
    client, _ = coin_client
    response = client.get("/admin/coins/qr-labels")
    assert response.status_code == 200
    assert response.data.count(b'class="qr-label"') == 6
    assert b"debits 1 ManaVote coin" in response.data
    assert b"Coke Zero" in response.data
    token_path = response.data.split(b'/coins/qr/', 1)[1].split(b'.png', 1)[0].decode()
    png = client.get(f"/coins/qr/{token_path}.png")
    assert png.status_code == 200
    assert png.mimetype == "image/png"
    assert png.data.startswith(b"\x89PNG")


def test_qr_uses_configured_public_base_url(coin_client):
    client, db_path = coin_client
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('url', 'https://vote.example')")
        connection.commit()
    response = client.get("/admin/coins/qr-labels")
    assert b"https://vote.example/coins/scan/" in response.data
    token = response.data.split(b'/coins/qr/', 1)[1].split(b'.png', 1)[0].decode()
    # Inspect the URL helper directly; PNG generation itself is covered above.
    from app.web.routes.coin_routes import _public_scan_url
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    with app.test_request_context():
        assert _public_scan_url(connection, token).startswith("https://vote.example/coins/scan/")
    connection.close()


def test_non_admin_cannot_print_or_manage_qr_labels(coin_client):
    client, _ = coin_client
    with client.session_transaction() as user_session:
        user_session["is_admin"] = 0
    assert client.get("/admin/coins/qr-labels").status_code == 302
    assert client.post("/admin/coins/adjust", data={"item_id": 1, "inventory_delta": 1}).status_code == 302
    assert client.post("/admin/coins/items", data={"name": "Icecream", "pack_size": 8}).status_code == 302


def test_admin_can_adjust_stock_without_changing_balance(coin_client):
    client, db_path = coin_client
    client.post("/admin/coins/adjust", data={"item_id": 1, "inventory_delta": -3, "note": "count", "idempotency_key": "adjust-once"})
    with sqlite3.connect(db_path) as connection:
        movement = connection.execute("SELECT inventory_delta, coin_delta, kind FROM coin_movements").fetchone()
    assert movement == (-3, 0, "adjustment")


def test_admin_can_create_item_with_custom_pack_size(coin_client):
    client, db_path = coin_client
    response = client.post(
        "/admin/coins/items",
        data={"name": "Icecream Minis mix", "pack_size": 8},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Coin item created" in response.data
    assert response.data.count(b'class="qr-label"') == 8
    page = client.get("/coins")
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
    assert token_count == 2


def test_admin_coins_section_has_item_creation_and_printable_qrs(coin_client):
    client, db_path = coin_client
    page = client.get("/admin?tab=coins")

    assert page.status_code == 200
    assert b'data-section="coins"' in page.data
    assert b'id="coins" class="card"' in page.data
    assert b"View and print QR labels" in page.data
    assert b'href="/admin/coins/qr-labels"' in page.data
    assert b'action="/admin/coins/items"' in page.data
    assert b'name="pack_size"' in page.data

    response = client.post(
        "/admin/coins/items",
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
        "/admin/coins/items", data={"name": "coke", "pack_size": 8}, follow_redirects=True
    )
    assert b"An item with that name already exists" in duplicate.data
    invalid = client.post(
        "/admin/coins/items", data={"name": "Icecream", "pack_size": 0}, follow_redirects=True
    )
    assert b"Pack size must be between 1 and 1000" in invalid.data
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM coin_items").fetchone()[0] == 3


def test_admin_can_disable_and_rotate_qr_token(coin_client):
    client, db_path = coin_client
    client.get("/admin/coins/qr-labels")
    with sqlite3.connect(db_path) as connection:
        item_id, action, old_token = connection.execute("SELECT item_id, action, token FROM coin_qr_tokens LIMIT 1").fetchone()
    client.post(f"/admin/coins/qr-tokens/{item_id}/{action}", data={"operation": "disable"})
    assert client.get(f"/coins/scan/{old_token}").status_code == 404
    client.post(f"/admin/coins/qr-tokens/{item_id}/{action}", data={"operation": "rotate"})
    with sqlite3.connect(db_path) as connection:
        new_token, active = connection.execute("SELECT token, active FROM coin_qr_tokens WHERE item_id = ? AND action = ?", (item_id, action)).fetchone()
    assert new_token != old_token
    assert active == 1


def test_scan_requires_login_then_returns_after_login(coin_client):
    client, db_path = coin_client
    client.get("/admin/coins/qr-labels")
    with sqlite3.connect(db_path) as connection:
        token = connection.execute("SELECT token FROM coin_qr_tokens LIMIT 1").fetchone()[0]
    with client.session_transaction() as user_session:
        user_session.clear()
    response = client.get(f"/coins/scan/{token}")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    with client.session_transaction() as user_session:
        assert user_session["login_next"] == f"/coins/scan/{token}"


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


def test_member_history_is_private_and_return_redirect_is_local(coin_client):
    client, db_path = coin_client
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO members (username, password_hash) VALUES ('other', 'x')")
        other_id = connection.execute("SELECT id FROM members WHERE username = 'other'").fetchone()[0]
        connection.row_factory = sqlite3.Row
        record_movement(connection, item="Coke", member_id=other_id, action="consume")
    page = client.get("/coins")
    assert b">other<" in page.data  # Public aggregate ranking includes every member.
    private_history = page.data.split(b"Recent coin movements", 1)[1]
    assert b">other<" not in private_history
    response = client.post("/coins/move", data={"item_id": 1, "action": "consume", "quantity": 1, "return_to": "https://evil.example"})
    assert response.headers["Location"].endswith("/coins")
