"""Invalid uploads must not discard proposal drafts or the current image."""

from html.parser import HTMLParser
from io import BytesIO
import sqlite3
from unittest.mock import Mock

import pytest

import app as budget_app
from app.web.routes import main_routes
from app.services import proposal_image_service


PNG = b"\x89PNG\r\n\x1a\n" + b"test image payload"


class FormValues(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.inputs = {}
        self.description = ""
        self.in_description = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and "name" in attrs:
            self.inputs[attrs["name"]] = attrs
        if tag == "textarea" and attrs.get("name") == "description":
            self.in_description = True

    def handle_endtag(self, tag):
        if tag == "textarea":
            self.in_description = False

    def handle_data(self, data):
        if self.in_description:
            self.description += data


@pytest.fixture
def proposal_form(isolated_db_path, monkeypatch, tmp_path):
    monkeypatch.setitem(budget_app.app.config, "TESTING", True)
    monkeypatch.setitem(budget_app.app.config, "WTF_CSRF_ENABLED", False)
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setitem(budget_app.app.config, "UPLOAD_FOLDER", str(uploads))
    budget_app.init_db()
    conn = budget_app.get_db()
    conn.execute(
        "INSERT OR REPLACE INTO members (id, username, password_hash) VALUES (1, 'owner', 'unused')"
    )
    proposal_id = conn.execute(
        "INSERT INTO proposals (title, description, amount, url, created_by, basic_supplies, image_filename) "
        "VALUES ('Original title', 'Original description', 10, 'https://example.org/old', 1, 1, 'original.png')"
    ).lastrowid
    conn.commit()
    conn.close()
    (uploads / "original.png").write_bytes(PNG)
    monkeypatch.setattr(main_routes, "process_proposal", Mock())
    monkeypatch.setattr(main_routes, "can_record_proposal_vote", lambda source: False)
    notification = Mock()
    monkeypatch.setattr(main_routes, "send_telegram_message", notification)
    client = budget_app.app.test_client()
    with client.session_transaction() as session:
        session.update(member_id=1, username="owner", is_admin=False)
    return client, uploads, proposal_id, notification


def draft(*, checked=True):
    values = {
        "title": 'Draft "title" <script>alert(1)</script>',
        "description": "First line & details\n</textarea><script>draft</script>",
        "amount": "19.95",
        "url": "https://example.org/product?a=1&b=2",
        "voting_deadline": "2026-11-12T19:30",
    }
    if checked:
        values["basic_supplies"] = "1"
    return values


@pytest.mark.parametrize("mode", ["new", "edit"])
@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("filename,payload,checked", [
    ("broken.jpg", b"not an image", True),
    ("photo.webp", b"RIFF0000WEBP", False),
    ("empty.png", b"", False),
])
def test_invalid_image_keeps_draft_and_existing_data(proposal_form, mode, language, filename, payload, checked):
    client, uploads, proposal_id, notification = proposal_form
    with client.session_transaction() as session:
        session["lang"] = language
    conn = budget_app.get_db()
    before = [tuple(row) for row in conn.execute("SELECT * FROM proposals")]
    conn.close()
    values = draft(checked=checked)
    response = client.post(
        "/proposal/new" if mode == "new" else f"/proposal/{proposal_id}/edit",
        data={**values, "image": (BytesIO(payload), filename)},
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert ("Invalid image format" if language == "en" else "El formato de imagen no es válido") in html
    form = FormValues(html)
    for name in ("title", "amount", "url"):
        assert form.inputs[name]["value"] == values[name]
    assert form.description == values["description"]
    assert ("checked" in form.inputs["basic_supplies"]) == checked
    if mode == "new":
        assert form.inputs["voting_deadline"]["value"] == values["voting_deadline"]
    assert '<script>alert(1)</script>' not in html
    assert '<script>draft</script>' not in html
    assert form.inputs["image"]["aria-invalid"] == "true"
    assert "value" not in form.inputs["image"]
    assert (
        "Your other entries have been kept." if language == "en"
        else "Se han conservado los demás datos."
    ) in html
    conn = budget_app.get_db()
    assert [tuple(row) for row in conn.execute("SELECT * FROM proposals")] == before
    assert conn.execute("SELECT COUNT(*) FROM votes").fetchone()[0] == 0
    conn.close()
    assert list(uploads.iterdir()) == [uploads / "original.png"]
    assert (uploads / "original.png").read_bytes() == PNG
    notification.assert_not_called()


@pytest.mark.parametrize("mode", ["new", "edit"])
@pytest.mark.parametrize("replacement", [False, True])
def test_draft_can_be_resubmitted_after_invalid_image(proposal_form, mode, replacement):
    client, uploads, proposal_id, notification = proposal_form
    endpoint = "/proposal/new" if mode == "new" else f"/proposal/{proposal_id}/edit"
    assert client.post(endpoint, data={**draft(), "image": (BytesIO(b"bad"), "bad.jpg")}).status_code == 200
    values = draft(checked=False)
    if replacement:
        values["image"] = (BytesIO(PNG), "valid.PNG")
    response = client.post(endpoint, data=values)
    assert response.status_code == 302
    conn = budget_app.get_db()
    rows = conn.execute("SELECT * FROM proposals ORDER BY id").fetchall()
    conn.close()
    assert len(rows) == (2 if mode == "new" else 1)
    saved = rows[-1]
    assert saved["title"] == values["title"]
    assert saved["description"] == values["description"]
    assert saved["amount"] == 19.95
    assert saved["url"] == values["url"]
    assert saved["basic_supplies"] == 0
    if replacement:
        assert saved["image_filename"] != "original.png"
        assert (uploads / saved["image_filename"]).read_bytes() == PNG
        assert (uploads / "original.png").exists() == (mode == "new")
    else:
        assert saved["image_filename"] == (None if mode == "new" else "original.png")
        assert list(uploads.iterdir()) == [uploads / "original.png"]
    assert notification.call_count == (1 if mode == "new" else 0)


@pytest.mark.parametrize("mode", ["new", "edit"])
@pytest.mark.parametrize("amount", ["-1", "not-a-number"])
def test_invalid_amount_also_retains_entered_fields(proposal_form, mode, amount):
    client, _, proposal_id, notification = proposal_form
    values = {**draft(checked=False), "amount": amount}
    response = client.post(
        "/proposal/new" if mode == "new" else f"/proposal/{proposal_id}/edit", data=values,
    )
    assert response.status_code == 200
    form = FormValues(response.get_data(as_text=True))
    assert form.inputs["title"]["value"] == values["title"]
    assert form.inputs["amount"]["value"] == amount
    assert form.description == values["description"]
    assert "checked" not in form.inputs["basic_supplies"]
    notification.assert_not_called()


def test_invalid_deadline_retains_the_draft(proposal_form):
    client, _, _, notification = proposal_form
    values = {**draft(), "voting_deadline": "invalid-date"}
    response = client.post("/proposal/new", data=values)
    assert response.status_code == 200
    assert b"Invalid voting deadline" in response.data
    form = FormValues(response.get_data(as_text=True))
    assert form.inputs["title"]["value"] == values["title"]
    assert form.inputs["voting_deadline"]["value"] == values["voting_deadline"]
    assert form.description == values["description"]
    notification.assert_not_called()


def test_failed_edit_keeps_original_image_and_removes_uncommitted_replacement(proposal_form):
    client, uploads, proposal_id, _ = proposal_form
    conn = budget_app.get_db()
    conn.execute("CREATE TRIGGER fail_edit BEFORE UPDATE ON proposals BEGIN SELECT RAISE(ABORT, 'edit blocked'); END")
    conn.commit()
    conn.close()
    with pytest.raises(sqlite3.IntegrityError, match="edit blocked"):
        client.post(
            f"/proposal/{proposal_id}/edit",
            data={**draft(), "image": (BytesIO(PNG), "replacement.png")},
        )
    assert list(uploads.iterdir()) == [uploads / "original.png"]
    assert (uploads / "original.png").read_bytes() == PNG
    conn = budget_app.get_db()
    row = conn.execute("SELECT title, image_filename FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
    conn.close()
    assert tuple(row) == ("Original title", "original.png")


def test_image_inspection_failure_cleans_up_temporary_upload(proposal_form, monkeypatch):
    client, uploads, _, _ = proposal_form
    monkeypatch.setattr(main_routes, "detect_image_type", Mock(side_effect=OSError("inspection failed")))
    with pytest.raises(OSError, match="inspection failed"):
        client.post("/proposal/new", data={**draft(), "image": (BytesIO(PNG), "photo.png")})
    assert list(uploads.iterdir()) == [uploads / "original.png"]


def test_partial_upload_failure_cleans_up_temporary_file(tmp_path):
    image = Mock(filename="photo.png")

    def fail_save(path):
        path.write_bytes(b"partial")
        raise OSError("upload failed")

    image.save.side_effect = fail_save
    with pytest.raises(OSError, match="upload failed"):
        proposal_image_service.save_proposal_image(
            image, upload_folder=tmp_path, detect_image_type=Mock(),
        )
    assert list(tmp_path.iterdir()) == []
