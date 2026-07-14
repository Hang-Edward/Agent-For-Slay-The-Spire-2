#!/usr/bin/env python3
"""Batch fixture test runner - runs all fixtures through the full decision pipeline.

Usage:
    python tests/run_all_fixtures.py                       # Run all fixtures
    python tests/run_all_fixtures.py -v                    # Verbose output
    python tests/run_all_fixtures.py --name combat         # Filter by name
"""

import argparse
import json
import os
import sys
import time

_engine_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _engine_dir)

from decisions.registry import get_default_registry
from llm.dryrun_client import DryRunClient


def load_fixture(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_single_fixture(path, llm, registry, verbose=False):
    name = os.path.basename(path)
    raw = load_fixture(path)
    screen = raw.get("screen_type", "?")
    handler = registry.get_handler_for_state(raw)

    if handler is None:
        return {"name": name, "screen": screen, "status": "SKIP", "reason": "no handler"}

    try:
        state_data = handler.extract_state(raw)
        prompt = handler.build_prompt(state_data)
        prompt_len = len(prompt)

        auto = handler.try_auto_decision(state_data)
        if auto is not None:
            return {
                "name": name, "screen": screen,
                "status": "AUTO", "auto_decision": str(auto),
                "prompt_len": prompt_len,
            }

        response, elapsed = llm.think(prompt)
        decision = handler.parse_response(response, state_data)

        result = {
            "name": name, "screen": screen,
            "status": "OK",
            "llm_response": response,
            "decision": str(decision),
            "elapsed_ms": int(elapsed * 1000),
            "prompt_len": prompt_len,
        }
        if verbose:
            result["prompt_preview"] = prompt[:200]
        return result
    except Exception as e:
        return {"name": name, "screen": screen, "status": "ERROR", "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Batch test all fixtures")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--name", default="", help="Filter fixture filenames")
    args = parser.parse_args()

    fixture_dir = os.path.join(os.path.dirname(__file__), "fixtures")
    fixtures = sorted(
        os.path.join(fixture_dir, f)
        for f in os.listdir(fixture_dir)
        if f.endswith(".json")
    )
    if args.name:
        fixtures = [f for f in fixtures if args.name in os.path.basename(f)]
    if not fixtures:
        print("No matching fixtures found")
        sys.exit(1)

    registry = get_default_registry()
    llm = DryRunClient()

    print(f"Running {len(fixtures)} fixtures...\n")

    results = []
    start_time = time.time()

    for path in fixtures:
        result = run_single_fixture(path, llm, registry, args.verbose)
        results.append(result)

        icon = {"OK": "+", "AUTO": "*", "SKIP": "-", "ERROR": "!"}.get(result["status"], "?")
        line = f"  {icon} [{result['screen']:15s}] {result['name']:30s} {result['status']:5s}"

        if result["status"] in ("OK", "AUTO") and "decision" in result:
            line += f" -> {result['decision']}"
            if "prompt_len" in result:
                line += f" ({result['prompt_len']} chars)"
        elif result["status"] == "ERROR":
            line += f" -> {result.get('error', '?')}"

        print(line)

    elapsed = time.time() - start_time
    ok = sum(1 for r in results if r["status"] in ("OK", "AUTO"))
    print(f"\nResult: {ok}/{len(results)} passed ({elapsed:.2f}s)")

    for e in results:
        if e["status"] == "ERROR":
            print(f"  Error: {e['name']}: {e.get('error', '?')}")

    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
