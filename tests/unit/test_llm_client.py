from app.integrations.llm_client import LLMClient


class Response:
    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"role": "assistant", "content": "hi"}}]}


def test_openai_compatible_client_sends_model_messages_and_tools():
    captured = {}

    class Session:
        def post(self, url, **kwargs):
            captured.update(url=url, **kwargs)
            return Response()

    client = LLMClient("http://llm/v1/", "secret", "test-model", session=Session())
    result = client.complete([{"role": "user", "content": "hello"}], [{"type": "function"}])
    assert result["content"] == "hi"
    assert captured["url"] == "http://llm/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["json"]["model"] == "test-model"
    assert captured["json"]["tool_choice"] == "auto"
