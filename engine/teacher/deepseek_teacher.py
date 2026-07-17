"""DeepSeek 老师接口。

老师只看低频摘要并给训练建议，不参与实时动作选择。
"""

from __future__ import annotations

import json

from llm.base import LLMRequestError


class TeacherReviewService:
    def __init__(self, llm, enabled: bool = False):
        self.llm = llm
        self.enabled = enabled

    def review_run(self, summary: dict) -> dict:
        if not self.enabled:
            return {"status": "disabled", "review": ""}
        if hasattr(self.llm, "is_configured") and not self.llm.is_configured():
            return {"status": "unconfigured", "review": ""}

        prompt = self._build_prompt(summary)
        try:
            review, elapsed = self.llm.think(prompt, temperature=0.2, max_tokens=256)
        except LLMRequestError as error:
            return {"status": "failed", "review": "", "error": str(error)}
        return {"status": "reviewed", "review": review, "elapsed_ms": int(elapsed * 1000)}

    def review_stuck_state(self, summary: dict) -> dict:
        """让老师低频诊断卡点；老师只给建议，不直接接管点击。"""
        if not self.enabled:
            return {"status": "disabled", "review": ""}
        if hasattr(self.llm, "is_configured") and not self.llm.is_configured():
            return {"status": "unconfigured", "review": ""}

        prompt = self._build_stuck_prompt(summary)
        try:
            review, elapsed = self.llm.think(prompt, temperature=0.1, max_tokens=180)
        except LLMRequestError as error:
            return {"status": "failed", "review": "", "error": str(error)}
        return {"status": "reviewed", "review": review, "elapsed_ms": int(elapsed * 1000)}

    def _build_prompt(self, summary: dict) -> str:
        compact = json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(compact) > 6000:
            compact = compact[:6000] + "...[truncated]"
        return "\n".join([
            "You are a Slay the Spire 2 teacher supervising a local policy model.",
            "Do not choose the next action. Review the completed run summary and produce concise training advice.",
            "Return short bullet points about mistakes, reward-shaping changes, and reusable rules.",
            "",
            compact,
        ])

    def _build_stuck_prompt(self, summary: dict) -> str:
        compact = json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(compact) > 3000:
            compact = compact[:3000] + "...[truncated]"
        return "\n".join([
            "You are a Slay the Spire 2 automation teacher supervising a local policy model.",
            "The agent is stuck or has no executable options. Diagnose the likely missing interface or unsafe retry.",
            "Do not invent hidden buttons. Return concise engineering advice and a safe next rule to add.",
            "",
            compact,
        ])
