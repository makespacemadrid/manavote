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
)
import requests

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

DB_PATH = os.path.join(os.path.dirname(__file__), "hackerspace.db")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


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
        created_by INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'active',
        processed_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proposal_id INTEGER NOT NULL,
        member_id INTEGER NOT NULL,
        vote TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(proposal_id, member_id)
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
        c.execute(
            "INSERT INTO budget_log (amount, description) VALUES (300, 'Initial budget')"
        )

    conn.commit()
    conn.close()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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
    c.execute("SELECT value FROM settings WHERE key = 'current_budget'")
    row = c.fetchone()
    conn.close()
    return float(row[0]) if row else 0


def get_member_count():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM members")
    count = c.fetchone()[0]
    conn.close()
    return count


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
    min_backers = max(1, int(member_count * 0.1))

    c.execute(
        "SELECT COUNT(*) FROM votes WHERE proposal_id = ? AND vote = 'in_favor'",
        (proposal_id,),
    )
    approve_count = c.fetchone()[0]

    current_budget = get_current_budget()

    if approve_count >= min_backers and proposal["amount"] <= current_budget:
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

        message = f"💰 *Budget Approved!*\n\n*Proposal:* {proposal['title']}\n*Amount:* €{proposal['amount']}\n*Approved by:* {approve_count} members\n*Remaining budget:* €{new_budget}"
        send_telegram_message(message)

        conn.close()
        return True

    elif approve_count < min_backers and current_budget < proposal["amount"]:
        c.execute(
            "UPDATE proposals SET status = 'rejected', processed_at = ? WHERE id = ?",
            (datetime.now().isoformat(), proposal_id),
        )
        conn.commit()
        conn.close()
        return False

    conn.close()
    return None


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


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM proposals ORDER BY created_at DESC")
    proposals = [dict(row) for row in c.fetchall()]

    c.execute("SELECT * FROM budget_log ORDER BY created_at DESC LIMIT 10")
    budget_history = c.fetchall()

    current_budget = get_current_budget()
    member_count = get_member_count()
    min_backers = max(1, int(member_count * 0.1))

    for p in proposals:
        c.execute(
            "SELECT COUNT(*) FROM votes WHERE proposal_id = ? AND vote = 'in_favor'",
            (p["id"],),
        )
        p["approve_count"] = c.fetchone()[0]
        c.execute(
            "SELECT COUNT(*) FROM votes WHERE proposal_id = ? AND vote = 'against'",
            (p["id"],),
        )
        p["reject_count"] = c.fetchone()[0]
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
        current_budget=current_budget,
        budget_history=budget_history,
        member_count=member_count,
        min_backers=min_backers,
    )


@app.route("/proposal/new", methods=["GET", "POST"])
@login_required
def new_proposal():
    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]
        amount = float(request.form["amount"])

        if amount <= 0:
            flash("Amount must be positive", "error")
            return redirect(url_for("new_proposal"))

        conn = get_db()
        c = conn.cursor()
        c.execute(
            "INSERT INTO proposals (title, description, amount, created_by) VALUES (?, ?, ?, ?)",
            (title, description, amount, session["member_id"]),
        )
        conn.commit()
        conn.close()

        flash("Proposal created!", "success")
        return redirect(url_for("dashboard"))

    current_budget = get_current_budget()
    return render_template("new_proposal.html", current_budget=current_budget)


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
    min_backers = max(1, int(member_count * 0.1))

    approve_count = sum(1 for v in votes if v["vote"] == "in_favor")
    reject_count = sum(1 for v in votes if v["vote"] == "against")

    current_budget = get_current_budget()

    if request.method == "POST":
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
            elif result is False:
                flash("Proposal rejected (insufficient backers or budget)", "error")

        return redirect(url_for("proposal_detail", proposal_id=proposal_id))

    c.execute(
        "SELECT vote FROM votes WHERE proposal_id = ? AND member_id = ?",
        (proposal_id, session["member_id"]),
    )
    user_vote = c.fetchone()

    conn.close()

    return render_template(
        "proposal_detail.html",
        proposal=proposal,
        votes=votes,
        approve_count=approve_count,
        reject_count=reject_count,
        member_count=member_count,
        min_backers=min_backers,
        current_budget=current_budget,
        user_vote=user_vote["vote"] if user_vote else None,
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
        flash("Approval undone, budget restored", "success")

    conn.close()
    return redirect(url_for("dashboard"))


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
            monthly = 50
            c.execute(
                "UPDATE settings SET value = ? WHERE key = 'current_budget'",
                (str(current + monthly),),
            )
            c.execute(
                "INSERT INTO budget_log (amount, description) VALUES (?, ?)",
                (monthly, "Monthly top-up"),
            )
            conn.commit()
            flash(
                f"Monthly top-up triggered! New budget: €{current + monthly}", "success"
            )

    c.execute("SELECT * FROM members ORDER BY created_at")
    members = c.fetchall()
    c.execute("SELECT * FROM budget_log ORDER BY created_at DESC LIMIT 20")
    budget_history = c.fetchall()

    conn.close()

    return render_template("admin.html", members=members, budget_history=budget_history)


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
