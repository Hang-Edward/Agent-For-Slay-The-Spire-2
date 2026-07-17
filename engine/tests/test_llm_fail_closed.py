"""验证模型后端失败时不会生成任何默认游戏动作。"""

import pytest
import requests

from llm.base import LLMRequestError
from llm.deepseek_client import DeepSeekClient


def test_deepseek_network_error_is_raised(monkeypatch):
    def fail_request(*args, **kwargs):
        raise requests.Timeout("simulated timeout")

    monkeypatch.setattr(requests, "post", fail_request)
    client = DeepSeekClient(api_key="test-key")

    with pytest.raises(LLMRequestError, match="DeepSeek request failed"):
        client.think("state")


def test_deepseek_disables_thinking_for_realtime_actions(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [{
                    "message": {"content": "END"},
                    "finish_reason": "stop",
                }],
            }

    def fake_request(*_args, **kwargs):
        captured.update(kwargs["json"])
        return Response()

    monkeypatch.setattr(requests, "post", fake_request)
    client = DeepSeekClient(api_key="test-key")

    content, _elapsed = client.think("state")

    assert content == "END"
    assert captured["thinking"] == {"type": "disabled"}


def test_deepseek_empty_content_is_an_error(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [{
                    "message": {"content": ""},
                    "finish_reason": "length",
                }],
            }

    monkeypatch.setattr(requests, "post", lambda *_args, **_kwargs: Response())
    client = DeepSeekClient(api_key="test-key")

    with pytest.raises(LLMRequestError, match="empty model content"):
        client.think("state")
