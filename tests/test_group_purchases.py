import sqlite3
import os
from io import BytesIO
from unittest.mock import patch

import pytest

from app import app
from app.db.connection import set_db_path
from app.db.migrations import run_migrations
from app.web.routes.group_purchase_routes import (
    _component_names,
    _component_specs,
    _component_specs_from_fields,
    _shared_cost_specs,
    _allocate_shared_costs,
    _valid_deadline,
    _valid_product_url,
)
from app.web.routes import main_routes


@pytest.fixture
def group_purchase_client(tmp_path, monkeypatch):
    db_path = tmp_path / "group-purchases.db"
    previous_db_path = main_routes.DB_PATH
    previous_upload_folder = app.config["UPLOAD_FOLDER"]
    monkeypatch.setattr(main_routes, "DB_PATH", str(db_path))
    set_db_path(str(db_path))
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    main_routes.init_db()
    client = app.test_client()
    with client.session_transaction() as user_session:
        user_session.update(member_id=1, username="admin", is_admin=1, lang="en")
    try:
        yield client, db_path
    finally:
        set_db_path(previous_db_path)
        app.config["UPLOAD_FOLDER"] = previous_upload_folder


def test_component_names_removes_blanks_and_duplicates():
    assert _component_names("AA\n\n aaa \naa\nAAA") == ["AA", "aaa"]
    assert _component_specs("AA | 2.50\nAAA | 3,75\naa | 4") == [("AA", 2.5), ("AAA", 3.75)]
    with pytest.raises(ValueError, match="Invalid component price"):
        _component_specs("AA | free")
    assert _component_specs_from_fields(["AA", "AAA"], ["2.5", "3.75"]) == [
        ("AA", 2.5),
        ("AAA", 3.75),
    ]
    assert _shared_cost_specs(["Shipping", "Tax"], ["12", "3.00"]) == [
        ("Shipping", 12.0),
        ("Tax", 3.0),
    ]


def test_deadline_and_url_validation():
    assert _valid_deadline("2026-12-31")
    assert not _valid_deadline("31/12/2026")
    assert _valid_product_url("https://example.com/batteries")
    assert not _valid_product_url("javascript:alert(1)")


def test_shared_costs_are_split_by_selection_value():
    debts = _allocate_shared_costs(
        [{"selection_amount": 30.0}, {"selection_amount": 70.0}],
        shared_cost_total=20.0,
    )
    assert debts == [
        {
            "selection_amount": 30.0,
            "selection_percentage": 30.0,
            "shared_cost_share": 6.0,
            "amount_owed": 36.0,
        },
        {
            "selection_amount": 70.0,
            "selection_percentage": 70.0,
            "shared_cost_share": 14.0,
            "amount_owed": 84.0,
        },
    ]


def test_group_purchase_migration_supports_quantities_per_member():
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute("CREATE TABLE proposals (id INTEGER PRIMARY KEY, title TEXT, amount REAL, basic_supplies INTEGER)")
    cursor.execute("CREATE TABLE activity_log (id INTEGER PRIMARY KEY, description TEXT)")
    cursor.execute("CREATE TABLE members (id INTEGER PRIMARY KEY)")

    run_migrations(cursor)
    cursor.execute("INSERT INTO group_purchases (title, created_by) VALUES ('Batteries', 1)")
    purchase_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO group_purchase_components (group_purchase_id, name) VALUES (?, 'AA')",
        (purchase_id,),
    )
    component_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO group_purchase_quantities (component_id, member_id, quantity) VALUES (?, 1, 3)",
        (component_id,),
    )

    assert cursor.execute(
        "SELECT quantity FROM group_purchase_quantities WHERE component_id = ? AND member_id = 1",
        (component_id,),
    ).fetchone()[0] == 3


def test_member_can_create_purchase_and_update_quantity(group_purchase_client):
    client, db_path = group_purchase_client

    with patch.object(main_routes, "send_telegram_message", return_value=True) as telegram:
        response = client.post(
            "/group-purchases",
            data={
                "title": "Batteries",
                "description": "Bulk order",
                "component_name": ["AA", "AAA"],
                "component_price": ["2.50", "3.75"],
                "cost_label": ["Shipping", "Tax"],
                "cost_amount": ["12.00", "3.00"],
                "deadline": "2026-12-31",
                "url": "https://example.com/batteries",
                "payment_method": "Bank transfer: ES00 1234",
                "image": (BytesIO(b"\x89PNG\r\n\x1a\nimage-data"), "batteries.png"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
    telegram.assert_called_once()
    telegram_message = telegram.call_args.args[0]
    assert "New group purchase: Batteries" in telegram_message
    assert "AA: €2.50" in telegram_message
    assert "Deadline: 2026-12-31" in telegram_message
    assert "Shared costs: Shipping: €12.00, Tax: €3.00" in telegram_message
    assert response.status_code == 200
    assert b"Batteries" in response.data
    assert b"AA" in response.data
    assert b"2026-12-31" in response.data
    assert b"https://example.com/batteries" in response.data

    conn = sqlite3.connect(db_path)
    components = conn.execute(
        "SELECT id, name FROM group_purchase_components ORDER BY position"
    ).fetchall()
    component_id = components[0][0]
    purchase = conn.execute(
        "SELECT id, deadline, url, image_filename FROM group_purchases"
    ).fetchone()
    purchase_id = purchase[0]
    assert purchase[1:3] == ("2026-12-31", "https://example.com/batteries")
    assert purchase[3].startswith("group-")
    conn.close()

    response = client.post(
        f"/group-purchases/{purchase_id}/edit",
        data={
            "title": "Batteries bulk order",
            "description": "Updated details",
            "deadline": "2026-12-30",
            "url": "https://example.com/updated",
            "payment_method": "PayPal to buyer@example.com",
            f"component_name_{components[0][0]}": "AA",
            f"component_price_{components[0][0]}": "2.50",
            f"component_name_{components[1][0]}": "AAA",
            f"component_price_{components[1][0]}": "3.75",
            "cost_label": ["Shipping", "Tax"],
            "cost_amount": ["12.00", "3.00"],
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Batteries bulk order" in response.data
    assert b"PayPal to buyer@example.com" in response.data

    response = client.post(
        f"/group-purchases/{purchase_id}/quantity",
        data={"component_id": component_id, "quantity": 4},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"admin: 4" in response.data
    assert b"Total units" in response.data
    assert b"25.00" in response.data
    assert b"Shipping" in response.data

    response = client.post(
        f"/group-purchases/{purchase_id}/payments/1",
        data={"received": "1"},
        follow_redirects=True,
    )
    assert b"Received" in response.data

    with patch.object(main_routes, "send_telegram_message", return_value=True) as telegram:
        response = client.post(
            f"/group-purchases/{purchase_id}/status",
            data={"status": "ordered"},
            follow_redirects=True,
        )
        assert b"order placed" in response.data
        response = client.post(
            f"/group-purchases/{purchase_id}/status",
            data={"status": "received"},
            follow_redirects=True,
        )
    assert b"shipment received" in response.data
    assert telegram.call_count == 2
    assert "📦 Order placed" in telegram.call_args_list[0].args[0]
    assert "✅ Shipment received" in telegram.call_args_list[1].args[0]
    assert "Batteries bulk order" in telegram.call_args_list[1].args[0]


def test_invalid_purchase_keeps_submitted_values(group_purchase_client):
    client, _ = group_purchase_client

    response = client.post(
        "/group-purchases",
        data={"title": "Remember this title", "description": "Details", "components": ""},
    )

    assert response.status_code == 200
    assert b"Add a title and at least one component" in response.data
    assert b'value="Remember this title"' in response.data


def test_creator_can_delete_own_purchase(group_purchase_client):
    client, db_path = group_purchase_client
    client.post("/group-purchases", data={"title": "Creator order", "components": "Part"})
    conn = sqlite3.connect(db_path)
    purchase_id = conn.execute("SELECT id FROM group_purchases").fetchone()[0]
    conn.close()
    with client.session_transaction() as user_session:
        user_session["is_admin"] = 0

    page = client.get("/group-purchases")
    assert f'/group-purchases/{purchase_id}/edit'.encode() in page.data
    assert f'/group-purchases/{purchase_id}/delete'.encode() in page.data

    response = client.post(
        f"/group-purchases/{purchase_id}/delete",
        follow_redirects=True,
    )
    assert b"Group purchase deleted" in response.data
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM group_purchases").fetchone()[0] == 0
    conn.close()


def test_only_creator_can_edit_status_and_payments(group_purchase_client):
    client, db_path = group_purchase_client
    client.post("/group-purchases", data={"title": "Order", "components": "Part"})
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO members (username, password_hash, is_admin) VALUES ('other', 'x', 0)"
    )
    other_id = conn.execute("SELECT id FROM members WHERE username = 'other'").fetchone()[0]
    purchase_id = conn.execute("SELECT id FROM group_purchases").fetchone()[0]
    conn.commit()
    conn.close()
    with client.session_transaction() as user_session:
        user_session.update(member_id=other_id, username="other", is_admin=0)

    edit_response = client.get(f"/group-purchases/{purchase_id}/edit", follow_redirects=True)
    status_response = client.post(
        f"/group-purchases/{purchase_id}/status",
        data={"status": "ordered"},
        follow_redirects=True,
    )
    delete_response = client.post(
        f"/group-purchases/{purchase_id}/delete",
        follow_redirects=True,
    )

    assert b"Only the creator or an admin can edit" in edit_response.data
    assert b"Invalid status change" in status_response.data
    assert b"Only the creator or an admin can delete" in delete_response.data
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT status FROM group_purchases").fetchone()[0] == "open"
    conn.close()


def test_admin_can_edit_and_delete_another_members_purchase(group_purchase_client):
    client, db_path = group_purchase_client
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO members (username, password_hash, is_admin) VALUES ('creator', 'x', 0)"
    )
    creator_id = conn.execute("SELECT id FROM members WHERE username = 'creator'").fetchone()[0]
    conn.execute(
        "INSERT INTO group_purchases (title, created_by, image_filename) VALUES (?, ?, ?)",
        ("Member order", creator_id, "group-test.png"),
    )
    purchase_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO group_purchase_components (group_purchase_id, name, unit_price) VALUES (?, 'Part', 2.5)",
        (purchase_id,),
    )
    component_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO group_purchase_quantities (component_id, member_id, quantity) VALUES (?, ?, 2)",
        (component_id, creator_id),
    )
    conn.execute(
        "INSERT INTO group_purchase_payments (group_purchase_id, member_id) VALUES (?, ?)",
        (purchase_id, creator_id),
    )
    conn.execute(
        "INSERT INTO group_purchase_shared_costs (group_purchase_id, label, amount) VALUES (?, 'Shipping', 3)",
        (purchase_id,),
    )
    conn.commit()
    conn.close()
    image_path = app.config["UPLOAD_FOLDER"] + "/group-test.png"
    with open(image_path, "wb") as image:
        image.write(b"test")

    page = client.get("/group-purchases")
    assert f'/group-purchases/{purchase_id}/edit'.encode() in page.data
    assert f'/group-purchases/{purchase_id}/delete'.encode() in page.data

    edit_response = client.post(
        f"/group-purchases/{purchase_id}/edit",
        data={
            "title": "Admin corrected order",
            f"component_name_{component_id}": "Corrected part",
            f"component_price_{component_id}": "4.50",
        },
        follow_redirects=True,
    )
    assert b"Group purchase updated" in edit_response.data
    assert b"Admin corrected order" in edit_response.data

    delete_response = client.post(
        f"/group-purchases/{purchase_id}/delete",
        follow_redirects=True,
    )
    assert b"Group purchase deleted" in delete_response.data
    assert not os.path.exists(image_path)

    conn = sqlite3.connect(db_path)
    for table in (
        "group_purchase_quantities",
        "group_purchase_payments",
        "group_purchase_shared_costs",
        "group_purchase_components",
        "group_purchases",
    ):
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    conn.close()
