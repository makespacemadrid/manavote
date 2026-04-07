from __future__ import annotations


def calculate_min_backers(member_count: int, amount: float, basic_supplies: int, thresholds):
    threshold_percent = (
        thresholds["basic"]
        if basic_supplies
        else thresholds["over50"]
        if amount > 50
        else thresholds["default"]
    )
    return max(1, int(member_count * (threshold_percent / 100)))


def summarize_votes(votes):
    approve_count = sum(1 for vote in votes if vote == "in_favor")
    reject_count = sum(1 for vote in votes if vote == "against")
    return approve_count, reject_count, approve_count - reject_count
