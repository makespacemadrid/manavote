import pytest

from app.services.mcp_application import Actor, ToolAccessDenied, execute_tool


def _executor(tool_name, arguments, *, req_id):
    return {"tool": tool_name, "arguments": arguments, "req_id": req_id}


def test_system_transport_can_execute_unclassified_tool():
    result = execute_tool(_executor, "create_member", {}, actor=Actor.system(), req_id="rpc")
    assert result == {"tool": "create_member", "arguments": {}, "req_id": "rpc"}


def test_unclassified_tool_is_denied_to_adapter_actor():
    with pytest.raises(ToolAccessDenied, match="no actor policy"):
        execute_tool(_executor, "create_member", {}, actor=Actor("admin", 1))


def test_member_cannot_execute_admin_tool():
    with pytest.raises(ToolAccessDenied, match="Administrator"):
        execute_tool(_executor, "list_user_statistics", {}, actor=Actor("member", 1))


def test_application_overwrites_model_member_attribution():
    result = execute_tool(
        _executor, "create_feedback", {"member_id": 999, "message": "Hi"},
        actor=Actor("member", 7),
    )
    assert result["arguments"]["member_id"] == 7


def test_application_binds_confirmed_write_creator_to_admin():
    result = execute_tool(
        _executor, "create_proposal", {"created_by": 999, "title": "Desk"},
        actor=Actor("admin", 7),
    )
    assert result["arguments"]["created_by"] == 7


@pytest.mark.parametrize("tool", ["admin_consume_coin_item", "admin_replenish_coin_item"])
def test_admin_coin_actions_preserve_target_and_deny_members(tool):
    arguments = {"member_id": 9, "item": "Coke", "quantity": 3}
    result = execute_tool(_executor, tool, arguments, actor=Actor("admin", 1))
    assert result["arguments"] == arguments
    with pytest.raises(ToolAccessDenied, match="Administrator"):
        execute_tool(_executor, tool, arguments, actor=Actor("member", 1))


def test_member_coin_actions_still_bind_to_caller():
    result = execute_tool(_executor, "consume_coin_item", {"member_id": 9}, actor=Actor("member", 1))
    assert result["arguments"]["member_id"] == 1
