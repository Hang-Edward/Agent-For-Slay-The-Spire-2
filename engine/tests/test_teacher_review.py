from teacher.deepseek_teacher import TeacherReviewService


class _FakeLLM:
    name = "FakeTeacher"

    def __init__(self, configured=True):
        self.configured = configured
        self.prompts = []

    def is_configured(self):
        return self.configured

    def think(self, prompt, temperature=0.2, max_tokens=256):
        self.prompts.append((prompt, temperature, max_tokens))
        return "Avoid low-value damage when lethal is impossible.", 0.01


def test_teacher_review_skips_when_disabled_or_unconfigured():
    assert TeacherReviewService(_FakeLLM(), enabled=False).review_run({})["status"] == "disabled"
    assert TeacherReviewService(_FakeLLM(configured=False), enabled=True).review_run({})["status"] == "unconfigured"


def test_teacher_review_uses_compact_run_summary():
    llm = _FakeLLM()
    result = TeacherReviewService(llm, enabled=True).review_run({
        "result": "loss",
        "floor": 12,
        "recent_events": [{"event_type": "decision_parsed", "payload": {"command": "PLAY 0 0"}}],
    })

    assert result["status"] == "reviewed"
    assert result["review"] == "Avoid low-value damage when lethal is impossible."
    prompt, temperature, max_tokens = llm.prompts[0]
    assert "You are a Slay the Spire 2 teacher" in prompt
    assert "PLAY 0 0" in prompt
    assert temperature == 0.2
    assert max_tokens == 256
