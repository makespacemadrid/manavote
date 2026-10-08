from datetime import datetime
import logging

from app.db.transactions import write_transaction

from app.repositories.budget_repo import BudgetRepository
from app.repositories.member_repo import MemberRepository
from app.repositories.proposal_repo import ProposalRepository
from app.repositories.settings_repo import SettingsRepository
from app.repositories.vote_repo import VoteRepository
from app.services.budget_service import calculate_min_backers

logger = logging.getLogger(__name__)


class ProposalService:
    def __init__(self, conn, telegram_client, base_url_getter, created_by=None):
        self.conn = conn
        self.proposals = ProposalRepository(conn)
        self.members = MemberRepository(conn)
        self.settings = SettingsRepository(conn)
        self.votes = VoteRepository(conn)
        self.budget = BudgetRepository(conn)
        self.telegram_client = telegram_client
        self.base_url_getter = base_url_getter
        self.created_by = created_by

    def process_proposal(self, proposal_id):
        return self._process_transition(proposal_id)

    def _process_transition(self, proposal_id, *, over_budget_only=False):
        with write_transaction(self.conn):
            proposal = self.proposals.get_by_id(proposal_id)
            allowed = {"over_budget"} if over_budget_only else {"active", "over_budget"}
            if proposal is None or proposal["status"] not in allowed:
                return None
            current_budget = self.budget.current_budget()
            thresholds = self.settings.get_thresholds()
            min_backers = calculate_min_backers(self.members.count(), proposal["amount"], proposal["basic_supplies"], thresholds)
            approve_count, reject_count = self.votes.get_counts(proposal_id)
            if approve_count - reject_count < min_backers:
                return None
            if proposal["amount"] > current_budget:
                if proposal["status"] == "active":
                    self.proposals.mark_over_budget(proposal_id, datetime.now().isoformat())
                return "over_budget"
            self.proposals.mark_approved(proposal_id, datetime.now().isoformat())
            new_budget = current_budget - proposal["amount"]
            self.settings.set_value("current_budget", str(new_budget))
            self.budget.add_log(-proposal["amount"], f"Approved: {proposal['title']}", self.created_by, proposal_id)
        logger.info("event=proposal_approved actor_id=%s proposal_id=%s reason_code=ok", self.created_by, proposal_id)
        if over_budget_only:
            detail = "*Now has enough budget!*"
        else:
            detail = f"*Net votes:* {approve_count} favor - {reject_count} against = {approve_count - reject_count}"
        try:
            self.telegram_client.send_message(
                f"💰 *Budget Approved!*\n\n*Proposal:* {proposal['title']}\n*Amount:* €{proposal['amount']:.2f}\n{detail}\n*Remaining budget:* €{new_budget:.2f}\n\n👉 {self.base_url_getter()}/proposal/{proposal_id}"
            )
        except (OSError, ValueError, RuntimeError):
            logger.error("event=proposal_approval_notification_failed actor_id=%s proposal_id=%s reason_code=delivery_failed", self.created_by, proposal_id)
            raise
        return True

    def check_over_budget_proposals(self):
        for proposal in self.proposals.list_over_budget():
            self._process_transition(proposal["id"], over_budget_only=True)
