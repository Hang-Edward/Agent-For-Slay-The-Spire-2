import json
import urllib.error
import urllib.request

import pytest

from dashboard.server import DashboardServer
from telemetry.event_bus import DecisionEventBus


@pytest.fixture
def server():
    bus = DecisionEventBus()
    history = type(
        "History",
        (),
        {
            "list_runs": lambda self, **_: [],
            "get_run": lambda self, *_args, **_kwargs: None,
            "get_decision": lambda self, *_args, **_kwargs: None,
        },
    )()
    instance = DashboardServer(bus, history, host="127.0.0.1", port=0)
    instance.start()
    yield instance, bus
    instance.stop()


def test_snapshot_and_get_only_contract(server):
    instance, bus = server
    bus.publish("llm_started", {"phase": "waiting_for_deepseek"}, state_revision=7)
    with urllib.request.urlopen(instance.url + "/api/snapshot") as response:
        body = json.load(response)
    assert body["phase"] == "waiting_for_deepseek"

    request = urllib.request.Request(instance.url + "/api/snapshot", method="POST", data=b"{}")
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request)
    assert error.value.code == 405


def test_path_traversal_is_rejected(server):
    instance, _ = server
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(instance.url + "/api/runs/..%2F..%2Fconfig")
    assert error.value.code in {400, 404}


def test_sse_reconnect_starts_after_last_event_id(server):
    instance, bus = server
    bus.publish("state_received", {}, run_id="run-1", state_revision=8)
    bus.publish("state_received", {}, run_id="run-1", state_revision=9)
    request = urllib.request.Request(instance.url + "/api/events", headers={"Last-Event-ID": "1"})
    with urllib.request.urlopen(request, timeout=2) as response:
        lines = []
        while True:
            line = response.readline().decode("utf-8").rstrip("\r\n")
            if not line:
                break
            lines.append(line)
    assert lines[0] == "retry: 1500"
    assert lines[1] == "id: 2"
    assert lines[2] == "event: telemetry"
    event = json.loads(lines[3].removeprefix("data: "))
    assert event["sequence"] == 2
    assert event["event_type"] == "state_received"
    assert event["run_id"] == "run-1"
    assert event["state_revision"] == 9
