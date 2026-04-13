#!/usr/bin/env python3
"""Golden eval runner for Phase 0 agents.

Usage:
    python scripts/run_evals.py [--agent AGENT_NAME] [--verbose]

Runs golden fixtures from tests/evals/fixtures/ against each agent
and reports pass/fail with timestamps.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.stubs import StubLLMProvider
from labelforge.agents.intake_classifier import IntakeClassifierAgent
from labelforge.agents.po_parser import POParserAgent
from labelforge.agents.pi_parser import PIParserAgent
from labelforge.agents.fusion import FusionAgent
from labelforge.agents.protocol_analyzer import ProtocolAnalyzerAgent
from labelforge.agents.warning_label_parser import WarningLabelParserAgent
from labelforge.agents.checklist_extractor import ChecklistExtractorAgent

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "evals" / "fixtures"

AGENT_MAP = {
    "intake_classifier": (IntakeClassifierAgent, "intake_classifier.json"),
    "po_parser": (POParserAgent, "po_parser.json"),
    "pi_parser": (PIParserAgent, "pi_parser.json"),
    "fusion": (FusionAgent, "fusion.json"),
    "protocol_analyzer": (ProtocolAnalyzerAgent, "protocol_analyzer.json"),
    "warning_label_parser": (WarningLabelParserAgent, "warning_label_parser.json"),
    "checklist_extractor": (ChecklistExtractorAgent, "checklist_extractor.json"),
}


def check_expectation(result, expected: dict) -> tuple[bool, str]:
    """Check if an agent result matches expected outcomes."""
    issues = []
    if "needs_hitl" in expected:
        if result.needs_hitl != expected["needs_hitl"]:
            issues.append(f"needs_hitl: got {result.needs_hitl}, expected {expected['needs_hitl']}")
    if "min_confidence" in expected:
        if result.confidence < expected["min_confidence"]:
            issues.append(f"confidence {result.confidence:.2f} < {expected['min_confidence']}")
    if "confidence" in expected and "min_confidence" not in expected:
        if abs(result.confidence - expected["confidence"]) > 0.01:
            issues.append(f"confidence {result.confidence:.2f} != {expected['confidence']}")
    if "doc_class" in expected:
        got = result.data.get("doc_class", "")
        if got != expected["doc_class"]:
            issues.append(f"doc_class: got '{got}', expected '{expected['doc_class']}'")
    if "item_count" in expected:
        items = result.data.get("items", result.data.get("fused_items", []))
        if len(items) != expected["item_count"]:
            issues.append(f"item_count: got {len(items)}, expected {expected['item_count']}")
    if "fused_count" in expected:
        fused = result.data.get("fused_items", [])
        if len(fused) != expected["fused_count"]:
            issues.append(f"fused_count: got {len(fused)}, expected {expected['fused_count']}")

    if issues:
        return False, "; ".join(issues)
    return True, "OK"


async def run_agent_evals(agent_name: str, verbose: bool = False) -> tuple[int, int]:
    agent_cls, fixture_file = AGENT_MAP[agent_name]
    fixture_path = FIXTURES_DIR / fixture_file
    if not fixture_path.exists():
        print(f"  ⚠ No fixtures found: {fixture_path}")
        return 0, 0

    fixtures = json.loads(fixture_path.read_text())
    llm = StubLLMProvider()
    # Some agents (e.g. PIParserAgent) are deterministic and don't accept llm_provider
    try:
        agent = agent_cls(llm_provider=llm)
    except TypeError:
        agent = agent_cls()

    passed = 0
    failed = 0

    for fixture in fixtures:
        fid = fixture["id"]
        desc = fixture.get("description", "")
        try:
            result = await agent.execute(fixture["input"])
            ok, msg = check_expectation(result, fixture["expected"])
            if ok:
                passed += 1
                if verbose:
                    print(f"    ✓ {fid}: {desc}")
            else:
                failed += 1
                print(f"    ✗ {fid}: {desc} — {msg}")
        except Exception as e:
            failed += 1
            print(f"    ✗ {fid}: {desc} — ERROR: {e}")

    return passed, failed


async def main():
    parser = argparse.ArgumentParser(description="Run golden eval fixtures")
    parser.add_argument("--agent", type=str, help="Run only this agent's evals")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show passing tests too")
    args = parser.parse_args()

    timestamp = datetime.now(tz=timezone.utc).isoformat()
    print(f"=== Golden Eval Run — {timestamp} ===\n")

    agents = [args.agent] if args.agent else list(AGENT_MAP.keys())
    total_passed = 0
    total_failed = 0

    for agent_name in agents:
        if agent_name not in AGENT_MAP:
            print(f"Unknown agent: {agent_name}")
            continue
        print(f"  {agent_name}:")
        p, f = await run_agent_evals(agent_name, verbose=args.verbose)
        total_passed += p
        total_failed += f
        status = "✓ PASS" if f == 0 else "✗ FAIL"
        print(f"    {status} ({p} passed, {f} failed)\n")

    print(f"Total: {total_passed} passed, {total_failed} failed")
    print(f"Completed: {datetime.now(tz=timezone.utc).isoformat()}")
    return 1 if total_failed > 0 else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
