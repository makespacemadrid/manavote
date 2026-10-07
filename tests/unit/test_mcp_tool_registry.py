from app.services.mcp_tool_registry import TelegramPolicy, telegram_policy, telegram_tool_definitions


def _definition(name, properties=None):
    properties = properties or {}
    return {
        "name": name,
        "description": name,
        "inputSchema": {"type": "object", "properties": properties, "required": list(properties)},
    }


def test_unclassified_tools_are_denied_by_default():
    tools = telegram_tool_definitions(
        [_definition("list_proposals"), _definition("new_unclassified_tool")], is_admin=True
    )
    assert [tool["name"] for tool in tools] == ["list_proposals"]
    assert telegram_policy("new_unclassified_tool") is None


def test_member_and_admin_policies_are_distinct():
    definitions = [_definition("list_proposals"), _definition("list_user_statistics")]
    member_names = {tool["name"] for tool in telegram_tool_definitions(definitions, is_admin=False)}
    admin_names = {tool["name"] for tool in telegram_tool_definitions(definitions, is_admin=True)}
    assert member_names == {"list_proposals"}
    assert admin_names == {"list_proposals", "list_user_statistics"}
    assert telegram_policy("list_user_statistics") == TelegramPolicy.ADMIN_READ


def test_actor_attribution_is_removed_from_model_schema():
    tools = telegram_tool_definitions(
        [_definition("create_feedback", {"member_id": {"type": "integer"}, "message": {"type": "string"}})],
        is_admin=False,
        actor_member_id=9,
    )
    schema = tools[0]["inputSchema"]
    assert "member_id" not in schema["properties"]
    assert "member_id" not in schema["required"]
    assert tools[0]["telegram_policy"] == TelegramPolicy.MEMBER_WRITE.value


def test_admin_coin_tools_keep_target_in_schema_and_are_hidden_from_members():
    definitions = [_definition(name, {"member_id": {"type": "integer"}})
                   for name in ("admin_consume_coin_item", "admin_replenish_coin_item")]
    assert telegram_tool_definitions(definitions, is_admin=False, actor_member_id=1) == []
    tools = telegram_tool_definitions(definitions, is_admin=True, actor_member_id=1)
    assert len(tools) == 2
    for tool in tools:
        assert "member_id" in tool["inputSchema"]["required"]
        assert tool["telegram_policy"] == TelegramPolicy.CONFIRMED_ADMIN_WRITE.value
