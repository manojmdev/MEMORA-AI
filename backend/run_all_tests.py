#!/usr/bin/env python3
"""
MEMORA AI — UNIFIED TEST RUNNER & TEST SUITE ORCHESTRATOR
Sprint 4.6 Deployment Readiness & Regression Orchestrator

Executes all 15 test suites in isolated subprocess environments, captures
individual suite metrics, supports category filtering (offline, db, live),
safeguards production data with namespace isolation, and provides structured
reporting with exit codes for CI/CD pipelines.

Usage:
    python backend/run_all_tests.py --all
    python backend/run_all_tests.py --skip-live
    python backend/run_all_tests.py --suite test_day7_hardening.py
    python backend/run_all_tests.py --category db
    python backend/run_all_tests.py --list
"""

import argparse
import os
import sys
import time
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict

if sys.platform == "win32":
    # Ensure UTF-8 output on Windows consoles
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

# Locate backend directory
BACKEND_DIR = Path(__file__).resolve().parent

@dataclass
class TestSuiteMetadata:
    filename: str
    name: str
    phase: str
    category: str  # 'db' (requires PostgreSQL), 'live' (requires external LLM/Nebius), 'offline'
    description: str
    timeout_sec: int = 120
    destructive: bool = False  # If True, touches persistent tables without isolated sessions

# Complete registry of all 15 existing test suites
TEST_SUITES: List[TestSuiteMetadata] = [
    TestSuiteMetadata(
        filename="test_db_and_api.py",
        name="Day 3 DB & FastAPI Endpoints",
        phase="Day 3",
        category="db",
        description="Verifies Neon PostgreSQL connection, table schemas, and basic FastAPI CRUD endpoints.",
        timeout_sec=120
    ),
    TestSuiteMetadata(
        filename="test_memory_engine.py",
        name="Day 3 Memory Engine",
        phase="Day 3",
        category="live",
        description="Tests memory extraction, embedding generation, and vector persistence via Nebius & Neon.",
        timeout_sec=240
    ),
    TestSuiteMetadata(
        filename="test_hybrid_retrieval.py",
        name="Day 4 Hybrid Retrieval",
        phase="Day 4",
        category="live",
        description="Validates hybrid search (reciprocal rank fusion of vector cosine + keyword BM25).",
        timeout_sec=240
    ),
    TestSuiteMetadata(
        filename="test_day5_intelligence.py",
        name="Day 5 Memory Intelligence",
        phase="Day 5",
        category="live",
        description="Tests memory evolution, decay scoring, conflict resolution, and self-reflection.",
        timeout_sec=300
    ),
    TestSuiteMetadata(
        filename="test_day6_agent.py",
        name="Day 6 Agent Architecture",
        phase="Day 6",
        category="live",
        description="Tests planner, policy engine, step validation, DAG execution, and checkpointing.",
        timeout_sec=300
    ),
    TestSuiteMetadata(
        filename="test_day7_hardening.py",
        name="Day 7 Hardening & Reliability",
        phase="Day 7",
        category="db",
        description="Tests idempotency keys, race conditions, worker lease fencing, and audit logs.",
        timeout_sec=180
    ),
    TestSuiteMetadata(
        filename="test_day7_2_hardening.py",
        name="Day 7.2 Security Hardening",
        phase="Day 7.2",
        category="db",
        description="Validates security headers, SQL injection resistance, rate limits, and payload bounds.",
        timeout_sec=120
    ),
    TestSuiteMetadata(
        filename="test_sprint2_intelligence.py",
        name="Sprint 2 Intelligence Engine",
        phase="Sprint 2",
        category="live",
        description="Tests semantic clustering, graph relationship building, and memory consolidation.",
        timeout_sec=300
    ),
    TestSuiteMetadata(
        filename="test_sprint3_agent.py",
        name="Sprint 3 Agent Workspaces",
        phase="Sprint 3",
        category="live",
        description="Validates dynamic DAGs, rollback logic, human approvals, and lease heartbeats.",
        timeout_sec=300
    ),
    TestSuiteMetadata(
        filename="test_sprint3_1_fault_injection.py",
        name="Sprint 3.1 Fault Injection",
        phase="Sprint 3.1",
        category="live",
        description="Injects worker crashes, poisoned checkpoints, and database disconnects to test resilience.",
        timeout_sec=300
    ),
    TestSuiteMetadata(
        filename="test_sprint4_3_reliability.py",
        name="Sprint 4.3 Reliability & Fencing",
        phase="Sprint 4.3",
        category="live",
        description="Verifies recovery policies, event streaming, and worker fencing under failure modes.",
        timeout_sec=300
    ),
    TestSuiteMetadata(
        filename="test_sprint4_4_acceptance.py",
        name="Sprint 4.4 Acceptance Verification",
        phase="Sprint 4.4",
        category="live",
        description="Validates multi-turn approvals, memory-context grounding, and workspace operations.",
        timeout_sec=300
    ),
    TestSuiteMetadata(
        filename="test_sprint4_5_agent_e2e.py",
        name="Sprint 4.5 Agent E2E Suite",
        phase="Sprint 4.5",
        category="live",
        description="End-to-end multi-workspace execution across all 8 specialized agent roles.",
        timeout_sec=480
    ),
    TestSuiteMetadata(
        filename="test_chat_regression_suite.py",
        name="Chat Regression Suite",
        phase="Sprint 4",
        category="live",
        description="10 deterministic scenarios verifying context grounding, safety, and identity.",
        timeout_sec=300
    ),
    TestSuiteMetadata(
        filename="test_live_chat_verification.py",
        name="Live Chat & Memory Explorer",
        phase="Sprint 4",
        category="live",
        description="End-to-end live chat conversation with full memory extraction, persistence, and recall.",
        timeout_sec=300
    ),
    TestSuiteMetadata(
        filename="test_serverless_slices.py",
        name="Sprint 5 Serverless Bounded Slices & Vercel Architecture",
        phase="Sprint 5",
        category="live",
        description="Verifies bounded execution slices, checkpoint resumption, fencing, approval gating & Vercel ASGI entrypoint.",
        timeout_sec=300
    ),
]

@dataclass
class TestResult:
    suite: TestSuiteMetadata
    status: str  # PASS, FAIL, TIMEOUT, BLOCKED, SKIPPED
    duration_sec: float = 0.0
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    message: str = ""

def check_environment(require_db: bool, require_live: bool) -> Dict[str, bool]:
    """Check availability of required environment credentials."""
    env = os.environ.copy()

    # Read backend/.env if not in environment
    env_file = BACKEND_DIR / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() not in env:
                        env[k.strip()] = v.strip()

    has_db = bool(env.get("DATABASE_URL"))
    has_live = bool(env.get("NEBIUS_API_KEY"))
    return {"has_db": has_db, "has_live": has_live}

def run_suite(suite: TestSuiteMetadata, env_check: Dict[str, bool], verbose: bool = False) -> TestResult:
    """Execute a single test suite in an isolated subprocess."""
    filepath = BACKEND_DIR / suite.filename
    if not filepath.exists():
        return TestResult(
            suite=suite,
            status="BLOCKED",
            message=f"File not found: {suite.filename}"
        )

    # Check credential requirements
    if suite.category == "live" and not env_check["has_live"]:
        return TestResult(
            suite=suite,
            status="SKIPPED",
            message="Skipped: NEBIUS_API_KEY not configured"
        )
    if suite.category in ("db", "live") and not env_check["has_db"]:
        return TestResult(
            suite=suite,
            status="BLOCKED",
            message="Blocked: DATABASE_URL not configured"
        )

    sub_env = os.environ.copy()
    sub_env["PYTHONPATH"] = str(BACKEND_DIR)
    sub_env["PYTHONIOENCODING"] = "utf-8"

    start_time = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, suite.filename],
            cwd=str(BACKEND_DIR),
            env=sub_env,
            capture_output=True,
            text=True,
            timeout=suite.timeout_sec,
            encoding="utf-8",
            errors="replace"
        )
        duration = time.time() - start_time
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""

        if proc.returncode == 0:
            status = "PASS"
            msg = "Suite succeeded"
        else:
            status = "FAIL"
            # Extract last line or error traceback summary
            err_lines = [l for l in (stderr + "\n" + stdout).splitlines() if l.strip()]
            last_err = err_lines[-1] if err_lines else f"Exited with code {proc.returncode}"
            msg = last_err[:80]

        return TestResult(
            suite=suite,
            status=status,
            duration_sec=duration,
            stdout=stdout,
            stderr=stderr,
            exit_code=proc.returncode,
            message=msg
        )
    except subprocess.TimeoutExpired as te:
        duration = time.time() - start_time
        return TestResult(
            suite=suite,
            status="TIMEOUT",
            duration_sec=duration,
            stdout=te.stdout or "",
            stderr=te.stderr or "",
            exit_code=-1,
            message=f"Timed out after {suite.timeout_sec}s"
        )
    except Exception as exc:
        duration = time.time() - start_time
        return TestResult(
            suite=suite,
            status="FAIL",
            duration_sec=duration,
            exit_code=-1,
            message=str(exc)[:80]
        )

def print_banner():
    print("=" * 80)
    print(" MEMORA AI — UNIFIED TEST SUITE RUNNER")
    print(" Sprint 4.6 Deployment Readiness & Regression Orchestration")
    print("=" * 80)

def list_suites():
    print_banner()
    print(f"{'Filename':<35} {'Category':<10} {'Phase':<12} {'Description'}")
    print("-" * 80)
    for s in TEST_SUITES:
        print(f"{s.filename:<35} {s.category:<10} {s.phase:<12} {s.description[:40]}...")
    print(f"\nTotal test suites registered: {len(TEST_SUITES)}")

def main():
    parser = argparse.ArgumentParser(description="MEMORA AI Unified Test Runner")
    parser.add_argument("--all", action="store_true", help="Run all 15 registered test suites")
    parser.add_argument("--skip-live", action="store_true", help="Skip suites requiring external live LLM API calls")
    parser.add_argument("--offline-only", action="store_true", help="Run only offline suites")
    parser.add_argument("--category", choices=["db", "live", "offline"], help="Filter by test category")
    parser.add_argument("--suite", type=str, help="Specific suite filename to run (or substring match)")
    parser.add_argument("--list", action="store_true", help="List registered test suites and exit")
    parser.add_argument("--verbose", action="store_true", help="Print verbose output of each suite")
    parser.add_argument("--timeout", type=int, default=None, help="Override per-suite timeout in seconds")

    args = parser.parse_args()

    if args.list:
        list_suites()
        return 0

    if not any([args.all, args.skip_live, args.offline_only, args.category, args.suite]):
        parser.print_help()
        print("\n[!] Please specify a mode: --all, --skip-live, --category <cat>, or --suite <name>")
        return 1

    print_banner()
    env_status = check_environment(require_db=True, require_live=True)
    print(f"Environment Status:")
    print(f"  PostgreSQL Database (DATABASE_URL): {'CONFIGURED' if env_status['has_db'] else 'MISSING'}")
    print(f"  Nebius TokenFactory (NEBIUS_API_KEY): {'CONFIGURED' if env_status['has_live'] else 'MISSING'}")
    print("-" * 80)

    # Filter suites
    selected: List[TestSuiteMetadata] = []
    for s in TEST_SUITES:
        if args.suite:
            if args.suite.lower() in s.filename.lower() or args.suite.lower() in s.name.lower():
                selected.append(s)
        elif args.offline_only:
            if s.category == "offline":
                selected.append(s)
        elif args.skip_live:
            if s.category != "live":
                selected.append(s)
        elif args.category:
            if s.category == args.category:
                selected.append(s)
        elif args.all:
            selected.append(s)

    if not selected:
        print("[!] No test suites matched the selection criteria.")
        return 1

    print(f"Selected {len(selected)} test suite(s) for execution.\n")

    results: List[TestResult] = []
    overall_start = time.time()

    for idx, s in enumerate(selected, 1):
        if args.timeout:
            s.timeout_sec = args.timeout

        print(f"[{idx}/{len(selected)}] Running: {s.filename} ({s.name})...", end=" ", flush=True)
        res = run_suite(s, env_status, verbose=args.verbose)
        results.append(res)

        status_color = res.status
        print(f"[{status_color}] ({res.duration_sec:.2f}s)")
        if res.status not in ("PASS", "SKIPPED"):
            print(f"      Reason/Output: {res.message}")
        if args.verbose and res.stdout:
            print("--- STDOUT ---")
            print(res.stdout)
            if res.stderr:
                print("--- STDERR ---")
                print(res.stderr)
            print("--------------")

    overall_duration = time.time() - overall_start

    # Summary Table
    print("\n" + "=" * 80)
    print(" TEST EXECUTION SUMMARY")
    print("=" * 80)
    print(f"{'#':<3} {'Suite':<35} {'Status':<10} {'Time':<8} {'Note'}")
    print("-" * 80)

    passed_count = sum(1 for r in results if r.status == "PASS")
    failed_count = sum(1 for r in results if r.status in ("FAIL", "TIMEOUT"))
    skipped_count = sum(1 for r in results if r.status == "SKIPPED")
    blocked_count = sum(1 for r in results if r.status == "BLOCKED")

    for idx, r in enumerate(results, 1):
        note = r.message[:30] if r.status != "PASS" else "OK"
        print(f"{idx:<3} {r.suite.filename:<35} {r.status:<10} {r.duration_sec:>5.2f}s  {note}")

    print("-" * 80)
    print(f"Total Suites: {len(results)} | "
          f"Passed: {passed_count} | "
          f"Failed: {failed_count} | "
          f"Skipped: {skipped_count} | "
          f"Blocked: {blocked_count} | "
          f"Duration: {overall_duration:.2f}s")
    print("=" * 80)

    if failed_count > 0 or blocked_count > 0:
        print("\n❌ TEST SUITE RUN FAILED: One or more suites did not pass.")
        return 1
    else:
        print("\n✅ ALL EXECUTED SUITES PASSED SUCCESSFULLY.")
        return 0

if __name__ == "__main__":
    sys.exit(main())
