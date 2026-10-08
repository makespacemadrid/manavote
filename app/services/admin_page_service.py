"""Administrator page read model, with repository-owned queries."""
import os
import sqlite3
from datetime import datetime
from app.repositories.member_repo import MemberRepository
from app.repositories.budget_repo import BudgetRepository
from app.repositories.proposal_repo import ProposalRepository
from app.repositories.poll_repo import PollRepository
from app.repositories.group_purchase_repo import GroupPurchaseRepository
from app.repositories.coin_repo import CoinRepository
from app.repositories.settings_repo import SettingsRepository
from app.services import feedback_service


def build_admin_page(conn, *, db_path, get_thresholds, is_registration_enabled, get_current_budget, logger):
    DB_PATH = db_path
    members = MemberRepository(conn).list_for_admin()

    budget_history_asc = [dict(row) for row in BudgetRepository(conn).history()]

    running = 0
    for log in budget_history_asc:
        running += log["amount"]
        log["balance"] = running

    budget_history = list(reversed(budget_history_asc))

    proposal_history_rows = ProposalRepository(conn).history_events()

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

    member_stats = MemberRepository(conn).proposal_statistics()

    member_poll_stats = MemberRepository(conn).poll_statistics()

    thresholds = get_thresholds()
    registration_enabled = is_registration_enabled()
    current_budget = get_current_budget()

    from app.services.backup_service import BACKUP_ROOT

    backup_dir = BACKUP_ROOT
    os.makedirs(backup_dir, exist_ok=True)
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

    image_backup_dir = backup_dir
    image_backups = []
    if os.path.isdir(image_backup_dir):
        for filename in os.listdir(image_backup_dir):
            if filename.startswith("uploads_") and filename.endswith(".zip"):
                backup_path = os.path.join(image_backup_dir, filename)
                image_backups.append(
                    {
                        "name": filename,
                        "size": os.path.getsize(backup_path),
                        "modified": datetime.fromtimestamp(os.path.getmtime(backup_path)).strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )
    image_backups.sort(key=lambda item: item["modified"], reverse=True)

    try:
        polls = [dict(row) for row in PollRepository(conn).list_for_admin()]
    except sqlite3.Error as exc:
        polls = []
        logger.warning(
            "admin_page_failure reason_code=poll_list_failed error=%s", exc
        )

    group_purchases = [dict(row) for row in GroupPurchaseRepository(conn).list_for_admin()]

    feedback_items = feedback_service.list_feedback(conn, limit=100)

    coin_items = [dict(row) for row in CoinRepository(conn).list_for_admin()]
    coin_movements = [dict(row) for row in CoinRepository(conn).movements_for_admin()]

    tz_row = SettingsRepository(conn).get_value("timezone", "Europe/Madrid")
    current_timezone = tz_row

    return {
        "members": members,
        "member_stats": member_stats,
        "member_poll_stats": member_poll_stats,
        "budget_history": budget_history,
        "proposal_history": proposal_history,
        "current_budget": current_budget,
        "thresholds": thresholds,
        "registration_enabled": registration_enabled,
        "current_timezone": current_timezone,
        "backups": backups,
        "image_backups": image_backups,
        "polls": polls,
        "group_purchases": group_purchases,
        "feedback_items": feedback_items,
        "coin_items": coin_items,
        "coin_movements": coin_movements,
    }
