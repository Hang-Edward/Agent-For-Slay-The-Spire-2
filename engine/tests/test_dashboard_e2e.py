from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "dashboard" / "static"


def test_dashboard_assets_have_required_regions_and_no_inline_model_html():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert all(
        marker in html
        for marker in (
            'id="connection-status"',
            'id="run-summary"',
            'id="player-summary"',
            'id="enemy-list"',
            'id="hand-list"',
            'id="decision-action"',
            'id="decision-reason"',
            'id="candidate-list"',
            'id="event-stream"',
            'id="history-view"',
            'id="debug-view"',
            'id="debug-content"',
        )
    )
    assert "textContent" in js
    assert "innerHTML = event" not in js
    assert 'JSON.stringify(s.game_state||{},null,2)' not in js
    assert 'JSON.stringify(s.current_decision||{},null,2)' not in js
    assert 'JSON.stringify(value||state.snapshot||{},null,2)' in js
