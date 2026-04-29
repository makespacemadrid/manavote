import os
import sqlite3
import hashlib
import secrets
from datetime import datetime, date, timedelta
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    logging.getLogger(__name__).warning("python-dotenv not installed; skipping .env loading")

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    send_file,
    jsonify,
)
from app.config import Config
from app.extensions import limiter, csrf
from app.db.connection import get_db as repo_get_db, set_db_path
from app.db.migrations import run_migrations
from app.integrations.telegram_client import TelegramClient
from app.repositories.settings_repo import SettingsRepository
from app.services.auth_service import verify_and_migrate_password
from app.services.budget_service import calculate_min_backers
from app.services.proposal_service import ProposalService
from app.web.decorators import login_required, admin_required
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import markdown
import imghdr
import logging
import warnings

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"), static_folder=os.path.join(BASE_DIR, "static"))
app.config.from_object(Config)

warnings.filterwarnings("ignore", category=DeprecationWarning, module="imghdr")

if not app.debug:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler("app.log"),
            logging.StreamHandler(),
        ],
    )
else:
    logging.basicConfig(level=logging.DEBUG)
app_env = os.getenv("FLASK_ENV", "").lower()
is_production = app_env == "production"
secret_key = app.config.get("SECRET_KEY")
if is_production and (not secret_key or secret_key == "dev-insecure-secret-change-me"):
    raise RuntimeError("SECRET_KEY must be set to a non-default value when FLASK_ENV=production")
app.secret_key = secret_key
app.permanent_session_lifetime = app.config["PERMANENT_SESSION_LIFETIME"]
app.jinja_env.cache = None
limiter.init_app(app)
csrf.init_app(app)


@app.template_filter("username")
def truncate_username(username):
    if "@" in username:
        return username.split("@")[0]
    return username


from translations import TRANSLATIONS


@app.template_filter("markdown")
def render_markdown(text):
    if not text:
        return ""
    return markdown.markdown(text, extensions=["nl2br"])


@app.template_filter("lang")
def get_lang(key):
    from flask import session

    lang = session.get("lang", "en")
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, key)


DB_PATH = os.path.join(BASE_DIR, "app.db")
set_db_path(DB_PATH)
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_THREAD_ID = os.environ.get("TELEGRAM_THREAD_ID", "")
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS proposals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        amount REAL NOT NULL,
        url TEXT,
        image_filename TEXT,
        created_by INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'active',
        processed_at TEXT,
        purchased_at TEXT,
        basic_supplies INTEGER DEFAULT 0
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proposal_id INTEGER NOT NULL,
        member_id INTEGER NOT NULL,
        vote TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(proposal_id, member_id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proposal_id INTEGER NOT NULL,
        member_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        amount REAL NOT NULL,
        description TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        created_by INTEGER,
        proposal_id INTEGER
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")

    c.execute("SELECT COUNT(*) FROM members WHERE is_admin = 1")
    if c.fetchone()[0] == 0:
        bootstrap_password = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD")
        if not bootstrap_password:
            if app.config.get("TESTING"):
                bootstrap_password = "test-admin-password"
            else:
                raise RuntimeError("ADMIN_BOOTSTRAP_PASSWORD must be set before first startup")
        admin_password = generate_password_hash(bootstrap_password)
        c.execute(
            "INSERT INTO members (username, password_hash, is_admin) VALUES (?, ?, 1)",
            ("admin", admin_password),
        )

    c.execute("SELECT value FROM settings WHERE key = 'current_budget'")
    row = c.fetchone()
    if row is None:
        c.execute("INSERT INTO settings (key, value) VALUES ('current_budget', '300')")
        c.execute("INSERT INTO settings (key, value) VALUES ('monthly_topup', '50')")
        c.execute("INSERT INTO settings (key, value) VALUES ('threshold_basic', '5')")
        c.execute("INSERT INTO settings (key, value) VALUES ('threshold_over50', '20')")
        c.execute(
            "INSERT INTO settings (key, value) VALUES ('threshold_default', '10')"
        )
        c.execute(
            "INSERT INTO activity_log (amount, description) VALUES (300, 'Ventas mercadillo marzo')"
        )
        c.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('registration_enabled', 'true')"
        )
    run_migrations(c)

    conn.commit()
    conn.close()


def ensure_db_ready():
    conn = repo_get_db()
    try:
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='members'")
        has_members = c.fetchone() is not None
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='settings'")
        has_settings = c.fetchone() is not None
    finally:
        conn.close()

    if not (has_members and has_settings):
        init_db()


def get_db():
    set_db_path(DB_PATH)
    ensure_db_ready()
    return repo_get_db()


def get_setting_value(key, default=None):
    conn = get_db()
    value = SettingsRepository(conn).get_value(key, default)
    conn.close()
    return value


def get_setting_float(key, default=0.0):
    value = get_setting_value(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def get_base_url():
    url = get_setting_value("url", "")
    if url:
        return url
    if request:
        return request.host_url
    return ""


def get_current_budget():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT SUM(amount) as total FROM activity_log")
    total = c.fetchone()["total"]
    conn.close()
    return total if total else 0


def get_member_count():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM members")
    count = c.fetchone()[0]
    conn.close()
    return count


def get_thresholds():
    conn = get_db()
    thresholds = SettingsRepository(conn).get_thresholds()
    conn.close()
    return thresholds




def get_vote_counts(cursor, proposal_id):
    cursor.execute(
        "SELECT COUNT(*) FROM votes WHERE proposal_id = ? AND vote = 'in_favor'",
        (proposal_id,),
    )
    approve_count = cursor.fetchone()[0]
    cursor.execute(
        "SELECT COUNT(*) FROM votes WHERE proposal_id = ? AND vote = 'against'",
        (proposal_id,),
    )
    reject_count = cursor.fetchone()[0]
    return approve_count, reject_count


def is_registration_enabled():
    value = get_setting_value("registration_enabled", "true")
    return str(value).lower() == "true"


def send_telegram_message(message):
    client = TelegramClient(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_THREAD_ID)
    return client.send_message(message)


def process_proposal(proposal_id):
    conn = get_db()
    service = ProposalService(conn, TelegramClient(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_THREAD_ID), get_base_url)
    result = service.process_proposal(proposal_id)
    conn.close()
    if result is True:
        check_over_budget_proposals()
    return result


def check_over_budget_proposals():
    conn = get_db()
    service = ProposalService(conn, TelegramClient(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_THREAD_ID), get_base_url)
    service.check_over_budget_proposals()
    conn.close()


@app.route("/")
def index():
    if "member_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/healthz")
def healthz():
    return {"status": "ok"}, 200


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM members WHERE username = ?", (username,))
        member = c.fetchone()

        if member:
            stored_hash = member["password_hash"]

            valid, migrated_hash = verify_and_migrate_password(stored_hash, password)
            if migrated_hash:
                c.execute(
                    "UPDATE members SET password_hash = ? WHERE id = ?",
                    (migrated_hash, member["id"]),
                )
                conn.commit()
        else:
            valid = False

        conn.close()

        if member and valid:
            session["member_id"] = member["id"]
            session["username"] = member["username"]
            session["is_admin"] = member["is_admin"]
            if "lang" not in session:
                session["lang"] = "en"
            session.permanent = True

            return redirect(url_for("dashboard"))
        else:
            flash("Invalid credentials", "error")

    return render_template("login.html", session_lang=session.get("lang", "en"))


@app.route("/api/register", methods=["POST"])
@limiter.limit("10 per minute")
@csrf.exempt
def api_register():
    if not ADMIN_API_KEY:
        return jsonify({"error": "API not configured"}), 503

    provided_key = request.headers.get("X-Admin-Key", "")
    if provided_key != ADMIN_API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 415
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    username = data.get("username")
    password = data.get("password")
    is_admin = data.get("is_admin", False)

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    password_hash = generate_password_hash(password)

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT id FROM members WHERE username = ?", (username,))
    if c.fetchone():
        conn.close()
        return jsonify({"error": "Username already exists"}), 409

    try:
        c.execute(
            "INSERT INTO members (username, password_hash, is_admin) VALUES (?, ?, ?)",
            (username, password_hash, 1 if is_admin else 0),
        )
        conn.commit()
        member_id = c.lastrowid
        conn.close()
        return jsonify(
            {
                "success": True,
                "message": f"User {username} created",
                "member_id": member_id,
            }
        ), 201
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 500


def require_api_key():
    if not ADMIN_API_KEY:
        return jsonify({"error": "API not configured"}), 503
    provided_key = request.headers.get("X-Admin-Key", "")
    if provided_key != ADMIN_API_KEY:
        return jsonify({"error": "Unauthorized"}), 401
    return None


def _parse_positive_amount(value):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    if amount <= 0:
        return None
    return amount


@app.route("/api/proposals", methods=["POST"])
@csrf.exempt
def api_create_proposal():
    auth_error = require_api_key()
    if auth_error:
        return auth_error

    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 415
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    title = data.get("title")
    description = data.get("description", "")
    amount = data.get("amount")
    url = data.get("url", "")
    basic_supplies = 1 if data.get("basic_supplies", False) else 0
    created_by = data.get("created_by")

    if not title or amount is None:
        return jsonify({"error": "title and amount are required"}), 400

    amount = _parse_positive_amount(amount)
    if amount is None:
        return jsonify({"error": "amount must be positive"}), 400

    if not created_by:
        return jsonify({"error": "created_by is required"}), 400

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT id FROM members WHERE id = ?", (created_by,))
    if not c.fetchone():
        conn.close()
        return jsonify({"error": "Creator member not found"}), 404

    try:
        c.execute(
            "INSERT INTO proposals (title, description, amount, url, created_by, basic_supplies) VALUES (?, ?, ?, ?, ?, ?)",
            (title, description, amount, url, created_by, basic_supplies),
        )
        conn.commit()
        proposal_id = c.lastrowid

        if basic_supplies and amount > 20.0:
            c.execute(
                "UPDATE proposals SET basic_supplies = 0 WHERE id = ?", (proposal_id,)
            )
            c.execute(
                "INSERT INTO comments (proposal_id, member_id, content) VALUES (?, ?, ?)",
                (
                    proposal_id,
                    created_by,
                    "Auto-removed basic supplies flag: amount over €20",
                ),
            )
            conn.commit()

        conn.close()
        return jsonify(
            {
                "success": True,
                "message": "Proposal created",
                "proposal_id": proposal_id,
            }
        ), 201
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/proposals/<int:proposal_id>", methods=["PUT", "PATCH"])
@csrf.exempt
def api_edit_proposal(proposal_id):
    auth_error = require_api_key()
    if auth_error:
        return auth_error

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))
    proposal = c.fetchone()

    if not proposal:
        conn.close()
        return jsonify({"error": "Proposal not found"}), 404

    if proposal["status"] != "active":
        conn.close()
        return jsonify({"error": "Cannot edit processed proposals"}), 400

    if not request.is_json:
        conn.close()
        return jsonify({"error": "Content-Type must be application/json"}), 415

    data = request.get_json(silent=True)
    if not data:
        conn.close()
        return jsonify({"error": "JSON body required"}), 400

    title = data.get("title", proposal["title"])
    description = data.get("description", proposal["description"])
    amount = data.get("amount", proposal["amount"])
    url = data.get("url", proposal["url"])
    basic_supplies = 1 if data.get("basic_supplies", proposal["basic_supplies"]) else 0

    amount = _parse_positive_amount(amount)
    if amount is None:
        conn.close()
        return jsonify({"error": "amount must be positive"}), 400

    try:
        c.execute(
            "UPDATE proposals SET title = ?, description = ?, amount = ?, url = ?, basic_supplies = ? WHERE id = ?",
            (title, description, amount, url, basic_supplies, proposal_id),
        )
        conn.commit()
        conn.close()
        return jsonify(
            {
                "success": True,
                "message": "Proposal updated",
                "proposal_id": proposal_id,
            }
        )
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/about")
def about():
    return render_template("about.html", session_lang=session.get("lang", "en"))


@app.route("/calendar")
def calendar():
    if not session.get("member_id"):
        return redirect(url_for("login"))

    sort_by = request.args.get("sort", "date_desc")
    page = request.args.get("page", 1, type=int)
    per_page = 20

    if sort_by == "date_asc":
        order_clause = "created_at ASC"
    elif sort_by == "amount_desc":
        order_clause = "amount DESC"
    elif sort_by == "amount_asc":
        order_clause = "amount ASC"
    else:
        order_clause = "created_at DESC"

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM proposals")
    total_proposals = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM activity_log")
    total_budget = c.fetchone()[0]

    total_items = total_proposals + total_budget
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    offset = (page - 1) * per_page

    c.execute(
        f"""
        SELECT *
        FROM (
            SELECT
                id,
                created_at,
                amount,
                'proposal' AS item_type,
                title,
                status,
                NULL AS description,
                id AS proposal_id
            FROM proposals
            UNION ALL
            SELECT
                id,
                created_at,
                amount,
                'activity' AS item_type,
                NULL AS title,
                NULL AS status,
                description,
                proposal_id
            FROM activity_log
        ) AS calendar_items
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
    """,
        (per_page, offset),
    )
    calendar_items = c.fetchall()

    pending_by_day = {}
    c.execute(
        "SELECT date(over_budget_at) as day, COALESCE(SUM(amount), 0) as pending FROM proposals WHERE over_budget_at IS NOT NULL GROUP BY day"
    )
    for row in c.fetchall():
        pending_by_day[row[0]] = row[1]

    c.execute("""
        SELECT 
            date(created_at) as day,
            SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as cash_in,
            SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as cash_out
        FROM activity_log
        GROUP BY date(created_at)
    """)
    budget_days = set(row[0] for row in c.fetchall())

    over_budget_days = set(pending_by_day.keys())

    approved_by_day = {}
    c.execute(
        "SELECT date(processed_at) as day, COALESCE(SUM(amount), 0) FROM proposals WHERE status = 'approved' AND processed_at IS NOT NULL GROUP BY day"
    )
    for row in c.fetchall():
        approved_by_day[row[0]] = row[1]

    approved_from_pending_by_day = {}
    c.execute(
        "SELECT date(processed_at) as day, COALESCE(SUM(amount), 0) FROM proposals WHERE status = 'approved' AND processed_at IS NOT NULL AND over_budget_at IS NOT NULL GROUP BY day"
    )
    for row in c.fetchall():
        approved_from_pending_by_day[row[0]] = row[1]

    c.execute("SELECT date(created_at) as day, COALESCE(SUM(amount), 0) FROM proposals GROUP BY date(created_at)")
    proposals_by_day = {}
    for row in c.fetchall():
        proposals_by_day[row[0]] = row[1]

    all_days = sorted(budget_days | set(over_budget_days) | set(approved_by_day.keys()) | set(proposals_by_day.keys()))

    daily_budget = []
    cash_balance = 0
    pending_total = 0
    pending_by_day_lookup = dict(pending_by_day)

    for day in all_days:
        cash_in = 0
        cash_out = 0

        if day in budget_days:
            c.execute(
                """SELECT SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END)
                FROM activity_log WHERE date(created_at) = ?""",
                (day,),
            )
            row = c.fetchone()
            cash_in = row[0] or 0
            cash_out = row[1] or 0
            cash_balance += cash_in - cash_out

        if day in over_budget_days:
            pending_total += pending_by_day_lookup.get(day, 0)

        approved_today = approved_by_day.get(day, 0)
        approved_from_pending_today = approved_from_pending_by_day.get(day, 0)
        pending_total -= approved_from_pending_today

        proposals_count = proposals_by_day.get(day, 0)

        daily_budget.append(
            {
                "day": day,
                "cash_in": cash_in,
                "cash_out": -cash_out if cash_out else 0,
                "approved": -approved_today if approved_today else 0,
                "cash_balance": cash_balance,
                "pending": pending_total,
                "proposals": proposals_count,
            }
        )

    current_budget = get_current_budget()

    conn.close()

    return render_template(
        "calendar.html",
        calendar_items=calendar_items,
        daily_budget=daily_budget,
        session_lang=session.get("lang", "en"),
        page=page,
        total_pages=total_pages,
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/set-language/<lang>")
def set_language(lang):
    if lang in ("en", "es"):
        session["lang"] = lang
        session.permanent = True
    return redirect(request.headers.get("Referer", url_for("dashboard")))


@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form["current_password"]
        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]

        if not current_password or not new_password or not confirm_password:
            flash("All fields are required", "error")
            return redirect(url_for("change_password"))

        if new_password != confirm_password:
            flash("New passwords do not match", "error")
            return redirect(url_for("change_password"))

        if len(new_password) < 4:
            flash("Password must be at least 4 characters", "error")
            return redirect(url_for("change_password"))

        conn = get_db()
        c = conn.cursor()
        c.execute(
            "SELECT password_hash FROM members WHERE id = ?",
            (session["member_id"],),
        )
        row = c.fetchone()

        if not row:
            conn.close()
            flash("Error", "error")
            return redirect(url_for("change_password"))

        stored_hash = row[0]

        if stored_hash.startswith("pbkdf2:sha256:"):
            valid = check_password_hash(stored_hash, current_password)
        elif stored_hash == hashlib.sha256(current_password.encode()).hexdigest():
            valid = True
        else:
            valid = False

        if not valid:
            conn.close()
            flash("Current password is incorrect", "error")
            return redirect(url_for("change_password"))

        new_hash = generate_password_hash(new_password)
        c.execute(
            "UPDATE members SET password_hash = ? WHERE id = ?",
            (new_hash, session["member_id"]),
        )
        conn.commit()
        conn.close()

        flash("Password changed successfully!", "success")
        return redirect(url_for("dashboard"))

    return render_template(
        "change_password.html", session_lang=session.get("lang", "en")
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if not is_registration_enabled():
        flash(
            "Self-registration is currently disabled. Please contact an admin.", "error"
        )
        return redirect(url_for("login"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if not username or not password:
            flash("Username and password are required", "error")
            return render_template(
                "register.html", session_lang=session.get("lang", "en")
            )

        password_hash = generate_password_hash(password)

        conn = get_db()
        c = conn.cursor()

        c.execute("SELECT id FROM members WHERE username = ?", (username,))
        if c.fetchone():
            flash("Username already exists", "error")
            conn.close()
            return render_template(
                "register.html", session_lang=session.get("lang", "en")
            )

        c.execute(
            "INSERT INTO members (username, password_hash, is_admin) VALUES (?, ?, 0)",
            (username, password_hash),
        )
        conn.commit()
        conn.close()

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html", session_lang=session.get("lang", "en"))


@app.route("/dashboard")
@login_required
def dashboard():
    from flask import make_response

    conn = get_db()
    c = conn.cursor()

    filter_type = request.args.get("filter", "")

    if filter_type == "basic":
        c.execute(
            "SELECT * FROM proposals WHERE basic_supplies = 1 ORDER BY created_at DESC"
        )
    elif filter_type in ("active", "approved", "over_budget"):
        c.execute(
            "SELECT * FROM proposals WHERE status = ? ORDER BY created_at DESC",
            (filter_type,),
        )
    elif filter_type == "purchased":
        c.execute(
            "SELECT * FROM proposals WHERE purchased_at IS NOT NULL ORDER BY created_at DESC"
        )
    elif filter_type == "not_purchased":
        c.execute(
            "SELECT * FROM proposals WHERE status = 'approved' AND purchased_at IS NULL ORDER BY created_at DESC"
        )
    elif filter_type == "expensive":
        c.execute(
            "SELECT * FROM proposals WHERE amount > 50 AND status IN ('active', 'approved') ORDER BY created_at DESC"
        )
    elif filter_type == "standard":
        c.execute(
            "SELECT * FROM proposals WHERE status = 'approved' AND basic_supplies = 0 AND amount <= 50 ORDER BY created_at DESC"
        )
    else:
        c.execute("SELECT * FROM proposals ORDER BY created_at DESC")

    proposals = [dict(row) for row in c.fetchall()]

    c.execute("SELECT COUNT(*) FROM proposals")
    total_count = c.fetchone()[0]

    c.execute("SELECT * FROM activity_log ORDER BY created_at ASC")
    budget_history_asc = [dict(row) for row in c.fetchall()]

    running = 0
    for log in budget_history_asc:
        running += log["amount"]
        log["balance"] = running

    budget_history = list(reversed(budget_history_asc))

    current_budget = get_current_budget()
    member_count = get_member_count()
    thresholds = get_thresholds()

    for p in proposals:
        p["min_backers"] = calculate_min_backers(
            member_count,
            p["amount"],
            p.get("basic_supplies"),
            thresholds,
        )
        p["approve_count"], p["reject_count"] = get_vote_counts(c, p["id"])
        p["net_votes"] = p["approve_count"] - p["reject_count"]
        c.execute(
            "SELECT vote FROM votes WHERE proposal_id = ? AND member_id = ?",
            (p["id"], session["member_id"]),
        )
        user_vote = c.fetchone()
        p["user_vote"] = user_vote["vote"] if user_vote else None

    conn.close()

    lang = session.get("lang", "en")

    return render_template(
        "dashboard.html",
        proposals=proposals,
        filter=filter_type,
        total_count=total_count,
        current_budget=current_budget,
        budget_history=budget_history,
        member_count=member_count,
        thresholds=thresholds,
        session_lang=lang,
    )


@app.route("/proposal/new", methods=["GET", "POST"])
@login_required
def new_proposal():
    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]
        amount = float(request.form["amount"])
        url = request.form.get("url", "").strip()
        basic_supplies = 1 if request.form.get("basic_supplies") else 0
        if amount <= 0:
            flash("Amount must be positive", "error")
            return redirect(url_for("new_proposal"))

        image_filename = None
        if "image" in request.files:
            image = request.files["image"]
            if image and image.filename:
                ext = image.filename.split(".")[-1].lower()
                if ext in ["jpg", "jpeg", "png"]:
                    image_filename = f"{secrets.token_hex(8)}.{ext}"
                    filepath = os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
                    image.save(filepath)

                    mime_type = imghdr.what(filepath)
                    if mime_type not in ["jpeg", "png"]:
                        os.remove(filepath)
                        flash("Invalid image format", "error")
                        return redirect(url_for("new_proposal"))

        conn = get_db()
        c = conn.cursor()
        c.execute(
            "INSERT INTO proposals (title, description, amount, url, image_filename, created_by, basic_supplies) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                title,
                description,
                amount,
                url,
                image_filename,
                session["member_id"],
                basic_supplies,
            ),
        )
        conn.commit()
        proposal_id = c.lastrowid

        if basic_supplies and amount > 20.0:
            c.execute(
                "UPDATE proposals SET basic_supplies = 0 WHERE id = ?", (proposal_id,)
            )
            c.execute(
                "INSERT INTO comments (proposal_id, member_id, content) VALUES (?, ?, ?)",
                (
                    proposal_id,
                    session["member_id"],
                    "Auto-removed basic supplies flag: amount over €20",
                ),
            )
            conn.commit()

        c.execute(
            "INSERT INTO votes (proposal_id, member_id, vote) VALUES (?, ?, 'in_favor')",
            (proposal_id, session["member_id"]),
        )
        conn.commit()

        process_proposal(proposal_id)

        c.execute("SELECT username FROM members WHERE id = ?", (session["member_id"],))
        creator = c.fetchone()["username"]
        conn.close()

        base_url = get_base_url()

        message = f"🆕 *New Proposal!*\n\n*{title}*\nBy: {creator.split('@')[0]}\nAmount: €{amount}\n\n{description[:200]}{'...' if len(description) > 200 else ''}\n\n👉 {url if url else 'No link'}\n🔗 {base_url}proposal/{proposal_id}"
        send_telegram_message(message)

        flash("Proposal created!", "success")
        return redirect(url_for("dashboard"))

    current_budget = get_current_budget()
    thresholds = get_thresholds()
    return render_template(
        "new_proposal.html",
        current_budget=current_budget,
        thresholds=thresholds,
        session_lang=session.get("lang", "en"),
    )


@app.route("/proposal/<int:proposal_id>", methods=["GET", "POST"])
@login_required
def proposal_detail(proposal_id):
    conn = get_db()
    c = conn.cursor()

    c.execute(
        "SELECT p.*, m.username as creator FROM proposals p JOIN members m ON p.created_by = m.id WHERE p.id = ?",
        (proposal_id,),
    )
    proposal = c.fetchone()

    if not proposal:
        conn.close()
        flash("Proposal not found", "error")
        return redirect(url_for("dashboard"))

    c.execute(
        "SELECT v.*, m.username FROM votes v JOIN members m ON v.member_id = m.id WHERE proposal_id = ?",
        (proposal_id,),
    )
    votes = c.fetchall()

    member_count = get_member_count()
    current_budget = get_current_budget()
    thresholds = get_thresholds()
    min_backers = calculate_min_backers(
        member_count, proposal["amount"], proposal["basic_supplies"], thresholds
    )

    approve_count, reject_count = get_vote_counts(c, proposal_id)
    net_votes = approve_count - reject_count

    if request.method == "POST":
        if "vote" in request.form:
            vote = request.form["vote"]

            c.execute(
                "INSERT OR REPLACE INTO votes (proposal_id, member_id, vote) VALUES (?, ?, ?)",
                (proposal_id, session["member_id"], vote),
            )
            conn.commit()

            flash("Vote recorded!", "success")

            if proposal["status"] == "active":
                result = process_proposal(proposal_id)
                if result is True:
                    flash("Proposal approved!", "success")
                elif result == "over_budget":
                    flash(
                        "Proposal pending - over budget (will auto-approve when budget available)",
                        "error",
                    )

        elif "comment" in request.form:
            comment = request.form["comment"].strip()
            if comment:
                c.execute(
                    "INSERT INTO comments (proposal_id, member_id, content) VALUES (?, ?, ?)",
                    (proposal_id, session["member_id"], comment),
                )
                conn.commit()
                flash("Comment added!", "success")

        return redirect(url_for("proposal_detail", proposal_id=proposal_id))

    c.execute(
        "SELECT vote FROM votes WHERE proposal_id = ? AND member_id = ?",
        (proposal_id, session["member_id"]),
    )
    user_vote = c.fetchone()

    c.execute(
        "SELECT c.*, m.username FROM comments c JOIN members m ON c.member_id = m.id WHERE proposal_id = ? ORDER BY c.created_at DESC",
        (proposal_id,),
    )
    comments = c.fetchall()

    conn.close()

    lang = session.get("lang", "en")

    return render_template(
        "proposal_detail.html",
        proposal=proposal,
        votes=votes,
        comments=comments,
        approve_count=approve_count,
        reject_count=reject_count,
        net_votes=net_votes,
        member_count=member_count,
        min_backers=min_backers,
        current_budget=current_budget,
        user_vote=user_vote["vote"] if user_vote else None,
        thresholds=thresholds,
        session_lang=lang,
    )


@app.route("/comment/<int:comment_id>/edit", methods=["GET", "POST"])
@login_required
def edit_comment(comment_id):
    if not session.get("is_admin"):
        flash("Admin access required", "error")
        return redirect(url_for("dashboard"))

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))
    comment = c.fetchone()

    if not comment:
        conn.close()
        flash("Comment not found", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        content = request.form["content"].strip()
        if content:
            c.execute(
                "UPDATE comments SET content = ? WHERE id = ?", (content, comment_id)
            )
            conn.commit()
            flash("Comment updated!", "success")
        conn.close()
        return redirect(url_for("proposal_detail", proposal_id=comment["proposal_id"]))

    conn.close()
    return render_template(
        "edit_comment.html",
        comment=comment,
        session_lang=session.get("lang", "en"),
        backups=backups,
    )


@app.route("/comment/<int:comment_id>/delete", methods=["POST"])
@login_required
def delete_comment(comment_id):
    if not session.get("is_admin"):
        flash("Admin access required", "error")
        return redirect(url_for("dashboard"))

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))
    comment = c.fetchone()

    if not comment:
        conn.close()
        flash("Comment not found", "error")
        return redirect(url_for("dashboard"))

    proposal_id = comment["proposal_id"]
    c.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    conn.commit()
    conn.close()

    flash("Comment deleted!", "success")
    return redirect(url_for("proposal_detail", proposal_id=proposal_id))


@app.route("/proposal/<int:proposal_id>/delete", methods=["POST"])
@login_required
def delete_proposal(proposal_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))
    proposal = c.fetchone()

    if not proposal:
        conn.close()
        flash("Proposal not found", "error")
        return redirect(url_for("dashboard"))

    if proposal["status"] != "active":
        conn.close()
        flash("Cannot delete processed proposals", "error")
        return redirect(url_for("proposal_detail", proposal_id=proposal_id))

    if proposal["created_by"] != session["member_id"] and not session.get("is_admin"):
        conn.close()
        flash("You can only delete your own proposals", "error")
        return redirect(url_for("proposal_detail", proposal_id=proposal_id))

    c.execute("DELETE FROM votes WHERE proposal_id = ?", (proposal_id,))
    c.execute("DELETE FROM comments WHERE proposal_id = ?", (proposal_id,))
    c.execute("DELETE FROM proposals WHERE id = ?", (proposal_id,))
    conn.commit()
    conn.close()

    flash("Proposal deleted!", "success")
    return redirect(url_for("dashboard"))


@app.route("/proposal/<int:proposal_id>/edit", methods=["GET", "POST"])
@login_required
def edit_proposal(proposal_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))
    proposal = c.fetchone()

    if not proposal:
        conn.close()
        flash("Proposal not found", "error")
        return redirect(url_for("dashboard"))

    if proposal["created_by"] != session["member_id"] and not session.get("is_admin"):
        conn.close()
        flash("You can only edit your own proposals", "error")
        return redirect(url_for("dashboard"))

    if proposal["status"] != "active":
        conn.close()
        flash("Cannot edit processed proposals", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]
        amount = float(request.form["amount"])
        url = request.form.get("url", "").strip()
        basic_supplies = 1 if request.form.get("basic_supplies") else 0
        if amount <= 0:
            flash("Amount must be positive", "error")
            return redirect(url_for("edit_proposal", proposal_id=proposal_id))

        image_filename = proposal["image_filename"]
        if "image" in request.files:
            image = request.files["image"]
            if image and image.filename:
                ext = image.filename.split(".")[-1].lower()
                if ext in ["jpg", "jpeg", "png"]:
                    if image_filename and os.path.exists(
                        os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
                    ):
                        os.remove(
                            os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
                        )
                    image_filename = f"{secrets.token_hex(8)}.{ext}"
                    filepath = os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
                    image.save(filepath)

                    mime_type = imghdr.what(filepath)
                    if mime_type not in ["jpeg", "png"]:
                        os.remove(filepath)
                        flash("Invalid image format", "error")
                        return redirect(
                            url_for("edit_proposal", proposal_id=proposal_id)
                        )

        c.execute(
            "UPDATE proposals SET title = ?, description = ?, amount = ?, url = ?, image_filename = ?, basic_supplies = ? WHERE id = ?",
            (
                title,
                description,
                amount,
                url,
                image_filename,
                basic_supplies,
                proposal_id,
            ),
        )
        conn.commit()

        if basic_supplies and amount > 20.0:
            c.execute(
                "UPDATE proposals SET basic_supplies = 0 WHERE id = ?", (proposal_id,)
            )
            c.execute(
                "INSERT INTO comments (proposal_id, member_id, content) VALUES (?, ?, ?)",
                (
                    proposal_id,
                    session["member_id"],
                    "Auto-removed basic supplies flag: amount over €20",
                ),
            )
            conn.commit()

        conn.close()

        flash("Proposal updated!", "success")
        return redirect(url_for("proposal_detail", proposal_id=proposal_id))

    conn.close()
    current_budget = get_current_budget()
    thresholds = get_thresholds()
    return render_template(
        "edit_proposal.html",
        proposal=proposal,
        current_budget=current_budget,
        thresholds=thresholds,
        session_lang=session.get("lang", "en"),
        backups=backups,
    )


@app.route("/vote/<int:proposal_id>", methods=["POST"])
@login_required
def quick_vote(proposal_id):
    vote = request.form.get("vote")
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO votes (proposal_id, member_id, vote) VALUES (?, ?, ?)",
        (proposal_id, session["member_id"], vote),
    )
    conn.commit()

    c.execute("SELECT status FROM proposals WHERE id = ?", (proposal_id,))
    status = c.fetchone()

    if status and status["status"] == "active":
        process_proposal(proposal_id)

    conn.close()
    flash("Vote recorded!", "success")
    return redirect(url_for("dashboard"))


@app.route("/withdraw-vote/<int:proposal_id>", methods=["GET", "POST"])
@login_required
def withdraw_vote(proposal_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT status FROM proposals WHERE id = ?", (proposal_id,))
    status = c.fetchone()

    if status and status["status"] != "active":
        conn.close()
        flash("Cannot withdraw vote on processed proposals", "error")
        return redirect(url_for("dashboard"))

    c.execute(
        "DELETE FROM votes WHERE proposal_id = ? AND member_id = ?",
        (proposal_id, session["member_id"]),
    )
    conn.commit()

    c.execute("SELECT status FROM proposals WHERE id = ?", (proposal_id,))
    status = c.fetchone()
    if status and status["status"] == "active":
        process_proposal(proposal_id)

    conn.close()

    flash("Vote withdrawn!", "success")
    return redirect(url_for("dashboard"))


@app.route("/undo/<int:proposal_id>")
@admin_required
def undo_approve(proposal_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))
    proposal = c.fetchone()

    if proposal and proposal["status"] == "approved":
        c.execute(
            "UPDATE proposals SET status = 'active', processed_at = NULL WHERE id = ?",
            (proposal_id,),
        )
        c.execute(
            "UPDATE settings SET value = ? WHERE key = 'current_budget'",
            (str(get_current_budget() + proposal["amount"]),),
        )
        c.execute(
            "INSERT INTO activity_log (amount, description, proposal_id) VALUES (?, ?, ?)",
            (proposal["amount"], f"Undo approval: {proposal['title']}", proposal_id),
        )
        conn.commit()
        check_over_budget_proposals()
        flash("Approval undone, budget restored", "success")

    conn.close()
    return redirect(url_for("dashboard"))


@app.route("/purchase/<int:proposal_id>", methods=["POST"])
@login_required
def mark_purchased(proposal_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))
    proposal = c.fetchone()

    if not proposal:
        conn.close()
        flash("Proposal not found", "error")
        return redirect(url_for("dashboard"))

    if proposal["status"] != "approved":
        conn.close()
        flash("Can only mark approved proposals as purchased", "error")
        return redirect(url_for("proposal_detail", proposal_id=proposal_id))

    c.execute(
        "UPDATE proposals SET purchased_at = ? WHERE id = ?",
        (datetime.now().isoformat(), proposal_id),
    )
    conn.commit()
    conn.close()

    flash("Marked as purchased!", "success")
    return redirect(url_for("proposal_detail", proposal_id=proposal_id))


@app.route("/unpurchase/<int:proposal_id>", methods=["POST"])
@login_required
def unmark_purchased(proposal_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))
    proposal = c.fetchone()

    if not proposal:
        conn.close()
        flash("Proposal not found", "error")
        return redirect(url_for("dashboard"))

    if proposal["status"] != "approved":
        conn.close()
        flash("Proposal not found", "error")
        return redirect(url_for("dashboard"))

    c.execute(
        "UPDATE proposals SET purchased_at = NULL WHERE id = ?",
        (proposal_id,),
    )
    conn.commit()
    conn.close()

    flash("Purchase status removed", "success")
    return redirect(url_for("proposal_detail", proposal_id=proposal_id))


@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin():
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_member":
            username = request.form["username"]
            password = request.form["password"]
            is_admin = 1 if request.form.get("is_admin") else 0
            password_hash = generate_password_hash(password)

            try:
                c.execute(
                    "INSERT INTO members (username, password_hash, is_admin) VALUES (?, ?, ?)",
                    (username, password_hash, is_admin),
                )
                conn.commit()
                flash(f"Member {username} added!", "success")
            except sqlite3.IntegrityError:
                flash("Username already exists", "error")

        elif action == "remove_member":
            member_id = request.form["member_id"]
            if int(member_id) == session["member_id"]:
                flash("You can't remove yourself", "error")
            else:
                c.execute("DELETE FROM members WHERE id = ?", (member_id,))
                conn.commit()
                flash("Member removed!", "success")

        elif action == "toggle_admin":
            member_id = request.form["member_id"]
            if int(member_id) == session["member_id"]:
                flash("You can't change your own admin role", "error")
            else:
                current_is_admin = c.execute(
                    "SELECT is_admin FROM members WHERE id = ?", (member_id,)
                ).fetchone()["is_admin"]
                new_is_admin = 0 if current_is_admin else 1
                c.execute(
                    "UPDATE members SET is_admin = ? WHERE id = ?",
                    (new_is_admin, member_id),
                )
                conn.commit()
                flash(
                    f"Admin role {'granted' if new_is_admin else 'removed'}!", "success"
                )

        elif action == "trigger_monthly":
            current = get_current_budget()
            monthly = get_setting_float("monthly_topup", 50)
            c.execute(
                "UPDATE settings SET value = ? WHERE key = 'current_budget'",
                (str(current + monthly),),
            )
            c.execute(
                "INSERT INTO activity_log (amount, description) VALUES (?, ?)",
                (monthly, "Monthly top-up"),
            )
            conn.commit()
            check_over_budget_proposals()
            flash(
                f"Monthly top-up applied! New budget: €{get_current_budget()}",
                "success",
            )

        elif action == "add_budget":
            amount = float(request.form["amount"])
            description = request.form["description"].strip()
            if amount <= 0:
                flash("Amount must be positive", "error")
            else:
                current = get_current_budget()
                c.execute(
                    "UPDATE settings SET value = ? WHERE key = 'current_budget'",
                    (str(current + amount),),
                )
                c.execute(
                    "INSERT INTO activity_log (amount, description) VALUES (?, ?)",
                    (amount, description),
                )
                conn.commit()
                flash(
                    f"Added €{amount} to budget! New balance: €{get_current_budget()}",
                    "success",
                )

        elif action == "update_thresholds":
            basic = request.form.get("threshold_basic", "5")
            over50 = request.form.get("threshold_over50", "20")
            default = request.form.get("threshold_default", "10")
            if basic:
                c.execute(
                    "UPDATE settings SET value = ? WHERE key = 'threshold_basic'",
                    (basic,),
                )
            if over50:
                c.execute(
                    "UPDATE settings SET value = ? WHERE key = 'threshold_over50'",
                    (over50,),
                )
            if default:
                c.execute(
                    "UPDATE settings SET value = ? WHERE key = 'threshold_default'",
                    (default,),
                )
            conn.commit()
            flash("Thresholds updated!", "success")

        elif action == "update_url":
            base_url = request.form.get("base_url", "").rstrip("/")
            if base_url:
                c.execute(
                    "INSERT INTO settings (key, value) VALUES ('url', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (base_url,),
                )
            conn.commit()
            flash("Base URL updated!", "success")

        elif action == "toggle_registration":
            enabled = "true" if request.form.get("registration_enabled") else "false"
            c.execute(
                "UPDATE settings SET value = ? WHERE key = 'registration_enabled'",
                (enabled,),
            )
            conn.commit()
            status = "enabled" if enabled == "true" else "disabled"
            flash(f"Self-registration {status}!", "success")

        elif action == "backup_db":
            try:
                from app.services.backup_service import backup_db

                backup_name, pruned_count = backup_db(DB_PATH, keep_days=7)
                flash(
                    f"Backup created: {backup_name} (pruned {pruned_count} old backup(s))",
                    "success",
                )
            except Exception as exc:
                flash(f"Backup failed: {exc}", "error")

    c.execute("SELECT * FROM members ORDER BY created_at")
    members = c.fetchall()

    c.execute("SELECT * FROM activity_log ORDER BY created_at ASC")
    budget_history_asc = [dict(row) for row in c.fetchall()]

    running = 0
    for log in budget_history_asc:
        running += log["amount"]
        log["balance"] = running

    budget_history = list(reversed(budget_history_asc))

    c.execute("""
        SELECT * FROM (
            SELECT
                p.created_at as event_at,
                'proposal_added' as event_type,
                m.username as actor,
                p.id as proposal_id,
                p.title as proposal_title,
                NULL as vote_value
            FROM proposals p
            JOIN members m ON m.id = p.created_by

            UNION ALL

            SELECT
                v.created_at as event_at,
                'member_voted' as event_type,
                m.username as actor,
                p.id as proposal_id,
                p.title as proposal_title,
                v.vote as vote_value
            FROM votes v
            JOIN members m ON m.id = v.member_id
            JOIN proposals p ON p.id = v.proposal_id

            UNION ALL

            SELECT
                p.processed_at as event_at,
                'proposal_approved' as event_type,
                NULL as actor,
                p.id as proposal_id,
                p.title as proposal_title,
                NULL as vote_value
            FROM proposals p
            WHERE p.status = 'approved' AND p.processed_at IS NOT NULL
        )
        WHERE event_at IS NOT NULL
        ORDER BY event_at DESC
        LIMIT 300
    """)
    proposal_history_rows = c.fetchall()

    proposal_history = []
    for row in proposal_history_rows:
        event_type = row["event_type"]
        actor = row["actor"] or "System"
        vote_value = row["vote_value"]

        if event_type == "proposal_added":
            event_label = "Proposal added"
            details = f"Created by {actor}"
        elif event_type == "member_voted":
            event_label = "Member voted"
            vote_label = "in favor" if vote_value == "in_favor" else "against"
            details = f"{actor} voted {vote_label}"
        elif event_type == "proposal_approved":
            event_label = "Proposal approved"
            details = "Approved automatically after reaching threshold"
        else:
            event_label = event_type
            details = ""

        proposal_history.append(
            {
                "created_at": row["event_at"],
                "event_label": event_label,
                "proposal_id": row["proposal_id"],
                "proposal_title": row["proposal_title"],
                "details": details,
            }
        )

    c.execute("""
        SELECT 
            m.id,
            m.username,
            m.is_admin,
            (SELECT COUNT(*) FROM votes v WHERE v.member_id = m.id) as vote_count,
            (SELECT COUNT(*) FROM proposals p WHERE p.created_by = m.id) as proposal_count,
            (SELECT COUNT(*) FROM proposals p WHERE p.created_by = m.id AND p.status = 'approved') as approved_count,
            (SELECT COUNT(*) FROM comments c WHERE c.member_id = m.id) as comment_count
        FROM members m
        ORDER BY vote_count DESC, proposal_count DESC
    """)
    member_stats = c.fetchall()

    thresholds = get_thresholds()
    registration_enabled = is_registration_enabled()
    current_budget = get_current_budget()

    backup_dir = os.path.dirname(DB_PATH) or "."
    backup_base = os.path.basename(DB_PATH).replace(".db", "")
    backups = []
    for filename in os.listdir(backup_dir):
        if filename.startswith(f"{backup_base}_") and filename.endswith(".db"):
            backup_path = os.path.join(backup_dir, filename)
            backups.append(
                {
                    "name": filename,
                    "size": os.path.getsize(backup_path),
                    "modified": datetime.fromtimestamp(os.path.getmtime(backup_path)).strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
    backups.sort(key=lambda item: item["modified"], reverse=True)

    conn.close()

    return render_template(
        "admin.html",
        members=members,
        member_stats=member_stats,
        budget_history=budget_history,
        proposal_history=proposal_history,
        current_budget=current_budget,
        thresholds=thresholds,
        registration_enabled=registration_enabled,
        get_setting_value=get_setting_value,
        session_lang=session.get("lang", "en"),
        backups=backups,
    )


@app.route("/check-overbudget")
@login_required
def check_overbudget():
    check_over_budget_proposals()
    return "OK"


def migrate_password_if_needed(user_id, plaintext_password):
    """Migrate old SHA256 hash to werkzeug hash on login"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT password_hash FROM members WHERE id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False

    stored_hash = row[0]

    if stored_hash.startswith("pbkdf2:sha256:"):
        conn.close()
        return check_password_hash(stored_hash, plaintext_password)

    if stored_hash == hashlib.sha256(plaintext_password.encode()).hexdigest():
        new_hash = generate_password_hash(plaintext_password)
        c.execute(
            "UPDATE members SET password_hash = ? WHERE id = ?", (new_hash, user_id)
        )
        conn.commit()
        conn.close()
        return True

    conn.close()
    return False


init_db()

if __name__ == "__main__":
    check_over_budget_proposals()
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug, host="0.0.0.0", port=5000)
