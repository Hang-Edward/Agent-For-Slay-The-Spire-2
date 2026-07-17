# AI Decision Dashboard and Experience Learning Design

Date: 2026-07-17
Status: Approved design

## 1. Goal

Add a local, read-only web dashboard that shows the Agent's real-time decisions and explainable decision evidence without screen capture. Persist complete run histories locally and use those histories as auditable experience that can influence later decisions.

The dashboard must not control the game. It must not expose secrets, block the Agent, or pretend to reveal a model's hidden chain of thought.

## 2. Scope

### Included

- Browser dashboard at `http://127.0.0.1:18889`.
- Real-time game state, decision phase, candidate scores, explanation summary, final action, latency, fallback, and error display.
- Summary and Debug modes.
- Complete local run and decision history.
- Historical run browsing and decision replay.
- Structured rewards and train-ready transition records.
- Similar-experience retrieval and confidence-bounded historical score adjustment.
- Training export compatibility for a future local policy model.

### Excluded

- Any dashboard endpoint that pauses, resumes, configures, or controls the Agent.
- Changes to the Mod control contract on port `18888`.
- Training or fine-tuning DeepSeek's hosted model weights.
- A local neural-network training pipeline in this phase.
- Fabricated hidden reasoning or chain-of-thought text.

## 3. System Boundaries

Port `18888` remains owned by the Godot/C# Mod:

- `GET /state`
- `GET /status`
- `POST /decision`

Port `18889` is owned by the Python Agent's read-only dashboard:

- Static dashboard assets
- Read-only REST resources
- Server-Sent Events for live telemetry

Dashboard failure must never affect the Mod protocol or the Agent's ability to make decisions.

## 4. Components

### 4.1 DashboardServer

`DashboardServer` runs in a dedicated daemon thread inside the Python Agent and binds only to `127.0.0.1:18889`. It serves static files, REST responses, and SSE clients.

The first implementation uses Python's standard HTTP server facilities so the project does not gain a Node.js build chain or a web-framework runtime dependency.

### 4.2 DecisionEventBus

`DecisionEventBus` accepts typed telemetry events from the Agent. It maintains:

- The current immutable dashboard snapshot.
- A bounded in-memory event ring for reconnecting clients.
- A bounded asynchronous persistence queue.
- Monotonic event sequence numbers.

Producers never wait for a browser. If the persistence queue is full, repeated state-refresh events may be coalesced or dropped. Decision, fallback, error, run-boundary, and terminal events must be retained.

### 4.3 RunHistoryStore

`RunHistoryStore` persists append-only JSONL archives and maintains a SQLite experience index. Writes occur on a dedicated worker.

Storage layout:

```text
data/
  runs/
    <run-id>/
      manifest.json
      events.jsonl
      decisions.jsonl
  experience.sqlite3
```

The entire `data/` directory is local runtime data and must be ignored by Git.

### 4.4 ExperienceRetriever

`ExperienceRetriever` queries indexed historical transitions by character, Act, room type, screen type, enemy set, HP band, deck features, and route context. It returns compact evidence summaries rather than raw histories.

Historical evidence is advisory. Existing deterministic rules remain the baseline when evidence is sparse or low confidence.

### 4.5 Dashboard UI

Static frontend files live under:

```text
engine/dashboard/static/
```

The interface uses semantic HTML, CSS, and plain JavaScript. It requires no package manager or compile step.

## 5. Event Model

Every event contains:

- `schema_version`
- `event_id`
- `sequence`
- `timestamp_utc`
- `run_id`
- `battle_id`, when applicable
- `state_revision`
- `event_type`
- `payload`

Required lifecycle events:

```text
agent_started
mod_connected
mod_disconnected
run_started
run_resumed
state_received
candidates_scored
experience_retrieved
llm_started
llm_finished
decision_parsed
fallback_selected
action_sent
action_accepted
action_rejected
waiting_for_game
waiting_for_team
decision_error
room_completed
run_completed
run_aborted
agent_stopped
```

`llm_started` records the request start and sanitized Prompt. `llm_finished` records latency and sanitized raw response. The API key and authorization headers are never event fields.

## 6. Decision Records

Each decision record stores:

- Complete pre-action state snapshot.
- Complete post-action state snapshot when a new revision arrives.
- Legal actions.
- Candidate sequences, component scores, and rejection reasons.
- Explainable summary and key tradeoffs.
- Sanitized Prompt and raw model response.
- Parsed final action.
- Decision source: `llm`, `auto`, or `fallback`.
- Submission result and resulting state revision.
- LLM latency and total decision latency.
- Teammate state, observed teammate actions, and wait reason.
- Code commit when available, policy version, reward version, and configuration digest.

Snapshots are data, not executable content. The frontend renders every string as text.

## 7. Read-Only Dashboard API

### `GET /api/snapshot`

Returns the current connection state, game state summary, active decision, recent events, and stale-state timing.

### `GET /api/events`

SSE stream. Supports `Last-Event-ID`. On reconnect, the server replays available ring-buffer events; if the gap is too old, the client reloads `/api/snapshot`.

### `GET /api/runs`

Returns paginated run summaries with date, character, ascension, result, highest floor, decision count, fallback count, and policy version.

### `GET /api/runs/<run-id>`

Returns a run manifest and paginated decision summaries.

### `GET /api/runs/<run-id>/decisions/<decision-id>`

Returns one complete historical decision, including Debug fields.

All unsupported methods return `405`. The server exposes no write endpoint.

## 8. User Interface

### 8.1 Global Header

The header shows:

- Agent, Mod, and DeepSeek status.
- Character, Act, floor, room, and run duration.
- Last event timestamp.
- A stale warning after three seconds without telemetry during an active run.

### 8.2 Live Command-Center Layout

The approved layout has three columns:

1. Left: player, combat, enemy, hand, potion, gold, and risk state.
2. Center: current phase, explanation summary, candidate scores, tradeoffs, final action, and latency.
3. Right: timestamped event stream with distinct treatment for LLM, automatic policy, fallback, success, rejection, waiting, and errors.

A recent-decision strip appears below the columns. Selecting an item opens its details without changing Agent behavior.

### 8.3 Views

- **Live**: current command center.
- **History**: run filtering, summaries, and ordered decision replay.
- **Debug**: Prompt, raw response, state JSON, parser result, and event metadata.

The interface explicitly distinguishes:

- Reading game state.
- Scoring candidates.
- Waiting for DeepSeek.
- Submitting an action.
- Waiting for game animation.
- Waiting for teammates.
- Using a safe fallback.
- Agent or Mod disconnection.

## 9. Reward Model

Rewards are versioned and decomposed into transparent components.

### 9.1 Immediate Reward

Examples include:

- Enemy HP reduction and kills.
- Player HP loss.
- Block that prevented incoming damage.
- Wasted block, energy, or consumables.
- Potion value and lethal prevention.

### 9.2 Room Reward

Examples include:

- Combat victory or defeat.
- Remaining HP and resource use.
- Card, relic, potion, and shop value.
- Route risk relative to health and gold.

### 9.3 Run Reward

Examples include:

- Highest floor.
- Act and Boss completion.
- Final victory or death.

Run outcome has the greatest weight. Shaped immediate rewards provide learning signal but must not override survival and progression. Each stored reward includes its component breakdown and `reward_version`.

## 10. Experience Learning

At decision time, the Agent computes a feature fingerprint and retrieves top similar experiences. A compact evidence block may include:

- Sample count.
- Outcome distribution.
- Successful and failed action patterns.
- Mean HP delta and progression value.
- Policy versions represented.
- Similarity and confidence.

Historical score adjustment follows these constraints:

- No adjustment below a configured minimum sample count.
- Bayesian or equivalent shrinkage toward the existing baseline.
- A hard cap on historical score influence.
- Newer policy versions receive greater relevance, without deleting older evidence.
- The dashboard displays baseline score, historical adjustment, final score, sample count, and confidence.

Only the compact evidence block enters the LLM Prompt. Raw past Prompts and full state snapshots do not accumulate in model context.

## 11. Run Identity and Recovery

A run ID is created when a new in-progress game is first observed. The active run identity is checkpointed locally.

After Agent restart:

- If the Mod reports the same in-progress run fingerprint, logging resumes under the existing run ID and emits `run_resumed`.
- If the prior run has no terminal event and no matching game exists, it is marked `run_aborted` with an interruption reason.
- A terminal game state closes the run exactly once.

JSONL readers skip and report a malformed final line, allowing recovery after abrupt process termination.

## 12. Safety and Privacy

- Bind only to `127.0.0.1`.
- Expose only GET and SSE resources.
- Redact API keys, bearer tokens, authorization headers, and configured secret values before publishing or persistence.
- Never return `config/api_key.yaml` or arbitrary files.
- Validate run and decision IDs before resolving filesystem paths.
- Escape all frontend text, including model output and Prompt content.
- Apply response size limits and history pagination.

## 13. Failure Behavior

- Dashboard port conflict: report a visible warning, continue running the Agent without the dashboard.
- Slow or disconnected browser: drop that SSE client without affecting other clients or the Agent.
- Persistence queue pressure: coalesce state-refresh events while retaining critical events.
- Read-only disk or SQLite error: emit an in-memory telemetry error and continue playing.
- Corrupt history: isolate the affected file or record and keep other runs readable.
- Agent failure during LLM request: persisted `llm_started` plus missing completion makes the stalled phase visible after restart.

## 14. Verification

### 14.1 Unit Tests

- Event serialization and schema validation.
- Secret redaction.
- Reward calculation and versioning.
- Run identity and recovery.
- JSONL malformed-tail recovery.
- Similarity retrieval, minimum sample threshold, shrinkage, and influence cap.
- Queue coalescing and critical-event retention.

### 14.2 API Tests

- Snapshot shape.
- SSE ordering, heartbeat, disconnect, and `Last-Event-ID` reconnect.
- Historical pagination and detail lookup.
- Method rejection and path traversal prevention.
- Static asset content types and missing resources.

### 14.3 Fault Tests

- Port `18889` already occupied.
- Read-only data directory.
- Slow SSE consumer.
- Agent termination mid-decision.
- Mod disconnect and reconnect.

### 14.4 Browser Tests

- Desktop and narrow-window screenshots.
- No overlap or overflow with long card names, Prompts, responses, and JSON.
- Clear stale, disconnected, waiting, fallback, and error states.
- Live reconnection without losing the current snapshot.

### 14.5 End-to-End Acceptance

Run at least one real game and verify:

1. Every decision appears live with phase, evidence, action, and latency.
2. Dashboard event latency is normally below 500 ms.
3. Telemetry does not materially increase decision latency.
4. The terminal run is saved and remains browsable after Agent restart.
5. A later run visibly retrieves historical evidence and shows the resulting score adjustment.
6. The Agent completes or loses the run without dashboard intervention.

## 15. Implementation Constraints

- Preserve the existing Mod API and deployment path.
- Keep dashboard telemetry optional and fail-open for gameplay.
- Reuse existing `DecisionStep`, handlers, strategy scoring, and TUI update points where practical.
- Replace duplicated ad hoc trace state with one typed event source rather than maintaining divergent TUI, file, and dashboard records.
- Add Chinese comments only where non-obvious concurrency, recovery, or reward logic needs explanation.
- Do not commit runtime histories, secrets, generated visual-companion files, or the experience database.

