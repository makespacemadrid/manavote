"""Transport-neutral authorization boundary for MCP tool execution."""

from dataclasses import dataclass

from app.services.mcp_tool_registry import TelegramPolicy, telegram_policy


@dataclass(frozen=True)
class Actor:
    role: str
    member_id: int | None = None

    @classmethod
    def system(cls):
        return cls("system")


class ToolAccessDenied(PermissionError):
    pass


def execute_tool(executor, tool_name, arguments, *, actor, req_id=1):
    """Authorize an actor, bind identity fields, and invoke a tool executor."""
    bound_arguments = dict(arguments) if isinstance(arguments, dict) else arguments
    if actor.role != "system":
        policy = telegram_policy(tool_name)
        if policy is None:
            raise ToolAccessDenied("Tool has no actor policy")
        if policy in {TelegramPolicy.ADMIN_READ, TelegramPolicy.CONFIRMED_ADMIN_WRITE} and actor.role != "admin":
            raise ToolAccessDenied("Administrator access required")
        if policy == TelegramPolicy.MEMBER_WRITE:
            if actor.member_id is None:
                raise ToolAccessDenied("Linked member required")
            bound_arguments["member_id"] = actor.member_id
        if policy == TelegramPolicy.CONFIRMED_ADMIN_WRITE and tool_name in {"create_proposal", "create_poll"}:
            if actor.member_id is None:
                raise ToolAccessDenied("Linked administrator required")
            bound_arguments["created_by"] = actor.member_id
    return executor(tool_name, bound_arguments, req_id=req_id)
