import os
import sqlite3
import hashlib
import secrets
from datetime import datetime, date
from functools import wraps
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
from werkzeug.utils import secure_filename
import requests

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)


@app.template_filter("username")
def truncate_username(username):
    if "@" in username:
        return username.split("@")[0]
    return username


DB_PATH = os.path.join(os.path.dirname(__file__), "hackerspace.db")
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
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

    c.execute("""CREATE TABLE IF NOT EXISTS budget_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        amount REAL NOT NULL,
        description TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")

    c.execute("SELECT COUNT(*) FROM members WHERE is_admin = 1")
    if c.fetchone()[0] == 0:
        admin_password = hashlib.sha256("carpediem42".encode()).hexdigest()
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
            "INSERT INTO budget_log (amount, description) VALUES (300, 'Ventas mercadillo marzo')"
        )
        c.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('registration_enabled', 'true')"
        )

    try:
        c.execute("ALTER TABLE proposals ADD COLUMN url TEXT")
    except:
        pass
    try:
        c.execute("ALTER TABLE proposals ADD COLUMN image_filename TEXT")
    except:
        pass
    try:
        c.execute("ALTER TABLE proposals ADD COLUMN purchased_at TEXT")
    except:
        pass

    conn.commit()
    conn.close()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_setting_value(key, default=None):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default


def get_setting_float(key, default=0.0):
    value = get_setting_value(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "member_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "member_id" not in session or not session.get("is_admin"):
            flash("Admin access required", "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)

    return decorated_function


def get_current_budget():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT SUM(amount) as total FROM budget_log")
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
    c = conn.cursor()
    c.execute("SELECT key, value FROM settings WHERE key LIKE 'threshold_%'")
    thresholds = {row[0]: float(row[1]) for row in c.fetchall()}
    conn.close()
    return {
        "basic": thresholds.get("threshold_basic", 5),
        "over50": thresholds.get("threshold_over50", 20),
        "default": thresholds.get("threshold_default", 10),
    }


def calculate_min_backers(member_count, amount, basic_supplies, thresholds):
    percentage = (
        thresholds["basic"]
        if basic_supplies
        else thresholds["over50"]
        if amount > 50
        else thresholds["default"]
    )
    return max(1, int(member_count * (percentage / 100)))


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
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(
            url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=10
        )
        return True
    except:
        return False


def process_proposal(proposal_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))
    proposal = c.fetchone()

    member_count = get_member_count()
    current_budget = get_current_budget()
    thresholds = get_thresholds()
    min_backers = calculate_min_backers(
        member_count, proposal["amount"], proposal["basic_supplies"], thresholds
    )
    approve_count, reject_count = get_vote_counts(c, proposal_id)

    net_votes = approve_count - reject_count

    if net_votes >= min_backers and proposal["amount"] <= current_budget:
        c.execute(
            "UPDATE proposals SET status = 'approved', processed_at = ? WHERE id = ?",
            (datetime.now().isoformat(), proposal_id),
        )

        new_budget = current_budget - proposal["amount"]
        c.execute(
            "UPDATE settings SET value = ? WHERE key = 'current_budget'",
            (str(new_budget),),
        )
        c.execute(
            "INSERT INTO budget_log (amount, description) VALUES (?, ?)",
            (-proposal["amount"], f"Approved: {proposal['title']}"),
        )

        conn.commit()

        message = f"💰 *Budget Approved!*\n\n*Proposal:* {proposal['title']}\n*Amount:* €{proposal['amount']}\n*Net votes:* {approve_count} favor - {reject_count} against = {net_votes}\n*Remaining budget:* €{new_budget}"
        send_telegram_message(message)

        conn.close()
        check_over_budget_proposals()
        return True

    elif net_votes >= min_backers and proposal["amount"] > current_budget:
        c.execute(
            "UPDATE proposals SET status = 'over_budget', processed_at = ? WHERE id = ?",
            (datetime.now().isoformat(), proposal_id),
        )
        conn.commit()
        conn.close()
        return "over_budget"

    conn.close()
    return None


def check_over_budget_proposals():
    conn = get_db()
    c = conn.cursor()

    current_budget = get_current_budget()
    thresholds = get_thresholds()

    c.execute(
        "SELECT id, title, amount, basic_supplies FROM proposals WHERE status = 'over_budget' ORDER BY created_at ASC"
    )
    over_budget = c.fetchall()

    for proposal in over_budget:
        if proposal["amount"] <= current_budget:
            member_count = get_member_count()
            min_backers = calculate_min_backers(
                member_count,
                proposal["amount"],
                proposal["basic_supplies"],
                thresholds,
            )
            approve_count, reject_count = get_vote_counts(c, proposal["id"])

            net_votes = approve_count - reject_count

            if net_votes >= min_backers:
                c.execute(
                    "UPDATE proposals SET status = 'approved', processed_at = ? WHERE id = ?",
                    (datetime.now().isoformat(), proposal["id"]),
                )

                new_budget = current_budget - proposal["amount"]
                c.execute(
                    "UPDATE settings SET value = ? WHERE key = 'current_budget'",
                    (str(new_budget),),
                )
                c.execute(
                    "INSERT INTO budget_log (amount, description) VALUES (?, ?)",
                    (-proposal["amount"], f"Approved: {proposal['title']}"),
                )

                conn.commit()

                message = f"💰 *Budget Approved!*\n\n*Proposal:* {proposal['title']}\n*Amount:* €{proposal['amount']}\n*Now has enough budget!*\n*Remaining budget:* €{new_budget}"
                send_telegram_message(message)

                current_budget = new_budget

    conn.close()


@app.route("/")
def index():
    if "member_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        conn = get_db()
        c = conn.cursor()
        c.execute(
            "SELECT * FROM members WHERE username = ? AND password_hash = ?",
            (username, password_hash),
        )
        member = c.fetchone()
        conn.close()

        if member:
            session["member_id"] = member["id"]
            session["username"] = member["username"]
            session["is_admin"] = member["is_admin"]
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid credentials", "error")

    return render_template("login.html")


@app.route("/api/register", methods=["POST"])
def api_register():
    if not ADMIN_API_KEY:
        return jsonify({"error": "API not configured"}), 503

    provided_key = request.headers.get("X-Admin-Key", "")
    if provided_key != ADMIN_API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    username = data.get("username")
    password = data.get("password")
    is_admin = data.get("is_admin", False)

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    password_hash = hashlib.sha256(password.encode()).hexdigest()

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


@app.route("/api/proposals", methods=["POST"])
def api_create_proposal():
    auth_error = require_api_key()
    if auth_error:
        return auth_error

    data = request.get_json()
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

    if amount <= 0:
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

    data = request.get_json()
    if not data:
        conn.close()
        return jsonify({"error": "JSON body required"}), 400

    title = data.get("title", proposal["title"])
    description = data.get("description", proposal["description"])
    amount = data.get("amount", proposal["amount"])
    url = data.get("url", proposal["url"])
    basic_supplies = 1 if data.get("basic_supplies", proposal["basic_supplies"]) else 0

    if amount <= 0:
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
    return render_template("about.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


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

        current_hash = hashlib.sha256(current_password.encode()).hexdigest()

        conn = get_db()
        c = conn.cursor()
        c.execute(
            "SELECT id FROM members WHERE id = ? AND password_hash = ?",
            (session["member_id"], current_hash),
        )
        if not c.fetchone():
            conn.close()
            flash("Current password is incorrect", "error")
            return redirect(url_for("change_password"))

        new_hash = hashlib.sha256(new_password.encode()).hexdigest()
        c.execute(
            "UPDATE members SET password_hash = ? WHERE id = ?",
            (new_hash, session["member_id"]),
        )
        conn.commit()
        conn.close()

        flash("Password changed successfully!", "success")
        return redirect(url_for("dashboard"))

    return render_template("change_password.html")


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
            return render_template("register.html")

        password_hash = hashlib.sha256(password.encode()).hexdigest()

        conn = get_db()
        c = conn.cursor()

        c.execute("SELECT id FROM members WHERE username = ?", (username,))
        if c.fetchone():
            flash("Username already exists", "error")
            conn.close()
            return render_template("register.html")

        c.execute(
            "INSERT INTO members (username, password_hash, is_admin) VALUES (?, ?, 0)",
            (username, password_hash),
        )
        conn.commit()
        conn.close()

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/dashboard")
@login_required
def dashboard():
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
            "SELECT * FROM proposals WHERE status = 'approved' AND amount > 50 ORDER BY created_at DESC"
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

    c.execute("SELECT * FROM budget_log ORDER BY created_at DESC LIMIT 50")
    budget_history = c.fetchall()

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

    return render_template(
        "dashboard.html",
        proposals=proposals,
        filter=filter_type,
        total_count=total_count,
        current_budget=current_budget,
        budget_history=budget_history,
        member_count=member_count,
        thresholds=thresholds,
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
                    image.save(
                        os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
                    )

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
        c.execute("SELECT username FROM members WHERE id = ?", (session["member_id"],))
        creator = c.fetchone()["username"]
        conn.close()

        message = f"🆕 *New Proposal!*\n\n*{title}*\nBy: {creator.split('@')[0]}\nAmount: €{amount}\n\n{description[:200]}{'...' if len(description) > 200 else ''}\n\n👉 {url if url else 'No link'}"
        send_telegram_message(message)

        flash("Proposal created!", "success")
        return redirect(url_for("dashboard"))

    current_budget = get_current_budget()
    thresholds = get_thresholds()
    return render_template(
        "new_proposal.html", current_budget=current_budget, thresholds=thresholds
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
    return render_template("edit_comment.html", comment=comment)


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
                    image.save(
                        os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
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
            "INSERT INTO budget_log (amount, description) VALUES (?, ?)",
            (proposal["amount"], f"Undo approval: {proposal['title']}"),
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
            password_hash = hashlib.sha256(password.encode()).hexdigest()

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

        elif action == "trigger_monthly":
            current = get_current_budget()
            monthly = get_setting_float("monthly_topup", 50)
            c.execute(
                "UPDATE settings SET value = ? WHERE key = 'current_budget'",
                (str(current + monthly),),
            )
            c.execute(
                "INSERT INTO budget_log (amount, description) VALUES (?, ?)",
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
                    "INSERT INTO budget_log (amount, description) VALUES (?, ?)",
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

        elif action == "toggle_registration":
            enabled = "true" if request.form.get("registration_enabled") else "false"
            c.execute(
                "UPDATE settings SET value = ? WHERE key = 'registration_enabled'",
                (enabled,),
            )
            conn.commit()
            status = "enabled" if enabled == "true" else "disabled"
            flash(f"Self-registration {status}!", "success")

    c.execute("SELECT * FROM members ORDER BY created_at")
    members = c.fetchall()

    c.execute("SELECT * FROM budget_log ORDER BY created_at DESC LIMIT 100")
    budget_history = c.fetchall()

    thresholds = get_thresholds()
    registration_enabled = is_registration_enabled()
    current_budget = get_current_budget()

    conn.close()

    return render_template(
        "admin.html",
        members=members,
        budget_history=budget_history,
        current_budget=current_budget,
        thresholds=thresholds,
        registration_enabled=registration_enabled,
    )


@app.route("/check-overbudget")
def check_overbudget():
    check_over_budget_proposals()
    return "OK"


if __name__ == "__main__":
    init_db()
    check_over_budget_proposals()
    app.run(debug=True, host="0.0.0.0", port=5000)
