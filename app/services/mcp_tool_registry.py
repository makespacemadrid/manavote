"""Public MCP tool policy registry shared by transports and adapters.

Tools are denied to Telegram by default. Adding a tool to the MCP schema does not make
it model-accessible until it is explicitly classified here.
"""

from copy import deepcopy
from enum import StrEnum


class TelegramPolicy(StrEnum):
    MEMBER_READ = "member_read"
    ADMIN_READ = "admin_read"
    MEMBER_WRITE = "member_write"
    CONFIRMED_ADMIN_WRITE = "confirmed_admin_write"


TELEGRAM_POLICIES = {
    "list_proposals": TelegramPolicy.MEMBER_READ,
    "list_polls": TelegramPolicy.MEMBER_READ,
    "list_group_purchases": TelegramPolicy.MEMBER_READ,
    "current_budget": TelegramPolicy.MEMBER_READ,
    "get_voting_settings": TelegramPolicy.MEMBER_READ,
    "list_member_telegram_links": TelegramPolicy.ADMIN_READ,
    "list_user_statistics": TelegramPolicy.ADMIN_READ,
    "create_feedback": TelegramPolicy.MEMBER_WRITE,
    "create_proposal": TelegramPolicy.CONFIRMED_ADMIN_WRITE,
    "create_poll": TelegramPolicy.CONFIRMED_ADMIN_WRITE,
    "update_voting_settings": TelegramPolicy.CONFIRMED_ADMIN_WRITE,
}


def telegram_policy(tool_name):
    """Return explicit policy, or None when the tool is denied by default."""
    return TELEGRAM_POLICIES.get(tool_name)


def telegram_tool_definitions(definitions, *, is_admin, actor_member_id=None):
    allowed = {TelegramPolicy.MEMBER_READ, TelegramPolicy.MEMBER_WRITE}
    if is_admin:
        allowed |= {TelegramPolicy.ADMIN_READ, TelegramPolicy.CONFIRMED_ADMIN_WRITE}
    result = []
    for original in definitions:
        policy = telegram_policy(original["name"])
        if policy not in allowed:
            continue
        item = deepcopy(original)
        item["telegram_policy"] = policy.value
        if actor_member_id is not None and item["name"] in {"create_proposal", "create_poll", "create_feedback"}:
            field = "member_id" if item["name"] == "create_feedback" else "created_by"
            schema = item["inputSchema"]
            schema["properties"].pop(field, None)
            schema["required"] = [name for name in schema.get("required", []) if name != field]
            if item["name"] == "create_feedback":
                item["description"] += " The member is taken from the linked Telegram account."
            else:
                item["description"] += " The creator is the linked Telegram member."
        result.append(item)
    return result
