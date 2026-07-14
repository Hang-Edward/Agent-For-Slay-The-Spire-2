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
