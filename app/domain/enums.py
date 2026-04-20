from enum import Enum


class ProposalStatus(str, Enum):
    ACTIVE = "active"
    APPROVED = "approved"
    OVER_BUDGET = "over_budget"
    REJECTED = "rejected"
