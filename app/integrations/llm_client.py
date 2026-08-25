"""OpenAI-compatible chat client for the Telegram MCP agent."""

import requests


class LLMClientError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, base_url, api_key, model, timeout=30, session=None):
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.timeout = timeout
        self.session = session or requests.Session()

    @property
    def configured(self):
        return bool(self.api_key and self.model)

    def complete(self, messages, tools=None):
        if not self.configured:
            raise LLMClientError("The Telegram assistant is not configured")
        payload = {"model": self.model, "messages": messages}
        if tools:
            payload.update({"tools": tools, "tool_choice": "auto"})
        try:
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
            return body["choices"][0]["message"]
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMClientError(f"LLM request failed: {exc}") from exc
