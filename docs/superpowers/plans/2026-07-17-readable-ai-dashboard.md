# Readable AI Dashboard Implementation Plan

> **For agentic workers:** Implement inline in the current task. Steps use checkbox syntax for tracking.

**Goal:** Replace raw JSON on the live dashboard with concise game, decision, and event summaries while preserving raw data in Debug.

**Architecture:** Keep the existing HTTP/SSE backend unchanged. Split browser rendering into small pure formatting helpers and DOM renderers inside `app.js`; update HTML containers and CSS to support semantic summaries.

**Tech Stack:** Native HTML, CSS, JavaScript; pytest; Headless Chrome.

## Global Constraints

- No new frontend dependencies.
- Use `textContent` for all model and game data.
- Preserve full JSON exclusively in Debug.
- Keep the three-column desktop and one-column narrow layout.

### Task 1: Semantic live dashboard

**Files:**
- Modify: `engine/tests/test_dashboard_e2e.py`
- Modify: `engine/dashboard/static/index.html`
- Modify: `engine/dashboard/static/app.js`
- Modify: `engine/dashboard/static/styles.css`

- [x] Add failing DOM assertions for player, enemy, hand, decision summary, candidates, and readable timeline containers.
- [x] Replace live-page `<pre>` JSON containers with semantic sections and empty states.
- [x] Add formatting helpers for actions, intents, cards, candidates, phases, and telemetry events.
- [x] Render history as compact run rows and keep raw snapshot JSON in Debug.
- [x] Run focused and complete pytest suites.
- [x] Capture and inspect a 1440x900 screenshot with representative fixture data.
