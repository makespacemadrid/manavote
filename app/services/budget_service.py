def calculate_min_backers(member_count, amount, basic_supplies, thresholds):
    votes = (
        thresholds["basic"]
        if basic_supplies
        else thresholds["over50"]
        if amount > 50
        else thresholds["default"]
    )
    return max(1, int(votes))
