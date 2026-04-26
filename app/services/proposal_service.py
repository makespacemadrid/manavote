from datetime import datetime

from app.repositories.budget_repo import BudgetRepository
from app.repositories.member_repo import MemberRepository
from app.repositories.proposal_repo import ProposalRepository
from app.repositories.settings_repo import SettingsRepository
from app.repositories.vote_repo import VoteRepository
from app.services.budget_service import calculate_min_backers


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
        proposal = self.proposals.get_by_id(proposal_id)
        member_count = self.members.count()
        current_budget = self.budget.current_budget()
        thresholds = self.settings.get_thresholds()
        min_backers = calculate_min_backers(member_count, proposal["amount"], proposal["basic_supplies"], thresholds)
        approve_count, reject_count = self.votes.get_counts(proposal_id)
        net_votes = approve_count - reject_count

        if net_votes >= min_backers and proposal["amount"] <= current_budget:
            self.proposals.mark_approved(proposal_id, datetime.now().isoformat())
            new_budget = current_budget - proposal["amount"]
            self.settings.set_value("current_budget", str(new_budget))
            self.budget.add_log(-proposal["amount"], f"Approved: {proposal['title']}", self.created_by, proposal_id)
            self.conn.commit()
            self.telegram_client.send_message(
                f"💰 *Budget Approved!*\n\n*Proposal:* {proposal['title']}\n*Amount:* €{proposal['amount']}\n*Net votes:* {approve_count} favor - {reject_count} against = {net_votes}\n*Remaining budget:* €{new_budget}\n\n👉 {self.base_url_getter()}proposal/{proposal_id}"
            )
            return True

        if net_votes >= min_backers and proposal["amount"] > current_budget:
            self.proposals.mark_over_budget(proposal_id, datetime.now().isoformat())
            self.conn.commit()
            return "over_budget"

        return None

    def check_over_budget_proposals(self):
        current_budget = self.budget.current_budget()
        thresholds = self.settings.get_thresholds()
        for proposal in self.proposals.list_over_budget():
            if proposal["amount"] > current_budget:
                continue
            member_count = self.members.count()
            min_backers = calculate_min_backers(member_count, proposal["amount"], proposal["basic_supplies"], thresholds)
            approve_count, reject_count = self.votes.get_counts(proposal["id"])
            net_votes = approve_count - reject_count
            if net_votes >= min_backers:
                self.proposals.mark_approved(proposal["id"], datetime.now().isoformat())
                new_budget = current_budget - proposal["amount"]
                self.settings.set_value("current_budget", str(new_budget))
                self.budget.add_log(-proposal["amount"], f"Approved: {proposal['title']}", self.created_by, proposal["id"])
                self.conn.commit()
                self.telegram_client.send_message(
                    f"💰 *Budget Approved!*\n\n*Proposal:* {proposal['title']}\n*Amount:* €{proposal['amount']}\n*Now has enough budget!*\n*Remaining budget:* €{new_budget}\n\n👉 {self.base_url_getter()}proposal/{proposal['id']}"
                )
                current_budget = new_budget
