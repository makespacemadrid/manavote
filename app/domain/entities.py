from dataclasses import dataclass


@dataclass
class ProposalDecision:
    status: str
    new_budget: float | None = None
