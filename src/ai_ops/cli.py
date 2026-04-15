"""
AI Ops CLI — Run the dispatch pipeline from the command line.

Usage:
    # Stub mode (no API key needed):
    python -m ai_ops.cli "Research Python web frameworks"

    # With LLM:
    set ANTHROPIC_API_KEY=sk-...
    python -m ai_ops.cli "Build a user authentication module"

    # With explicit approval level:
    python -m ai_ops.cli --approval-level 1 "Deploy the staging build"
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src/ so ai_ops package is importable without PYTHONPATH=src
_src_path = str(Path(__file__).resolve().parents[1])   # src/ai_ops/../../ = src/
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

# Add repo root so workflows package is importable
_repo_root = str(Path(__file__).resolve().parents[2])  # src/ai_ops/../../../ = repo root
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from ai_ops.llm.client import create_client
from ai_ops.runtime.approval import AutoApprovalHandler, InteractiveApprovalHandler
from ai_ops.runtime.persistence import RunPersistence
from ai_ops.runtime.worktree import WorktreeManager


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI Ops — Run the multi-agent dispatch pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m ai_ops.cli "Research Python web frameworks"
  python -m ai_ops.cli --approval-level 1 "Build a REST API service"
  python -m ai_ops.cli --criteria "JWT support" --criteria "Password hashing" "Build auth module"
  python -m ai_ops.cli --no-interactive "Build something"
        """,
    )
    parser.add_argument("task", help="Task description")
    parser.add_argument(
        "--approval-level", type=int, default=0, choices=[0, 1, 2, 3],
        help="Approval level required (default: 0 = auto)",
    )
    parser.add_argument(
        "--criteria", action="append", default=[],
        help="Acceptance criterion (can be repeated)",
    )
    parser.add_argument(
        "--constraint", action="append", default=[],
        help="Constraint (can be repeated)",
    )
    parser.add_argument(
        "--run-id", default=None,
        help="Run ID (auto-generated if not provided)",
    )
    parser.add_argument(
        "--no-interactive", action="store_true",
        help="Use auto-approval handler instead of interactive prompts",
    )
    parser.add_argument(
        "--no-persist", action="store_true",
        help="Skip persisting results to disk",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Generate run ID
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")

    # Create components
    llm_client = create_client()
    approval_handler = (
        AutoApprovalHandler() if args.no_interactive
        else InteractiveApprovalHandler()
    )
    persistence = RunPersistence()
    # Worktree lifecycle is only meaningful when persisting run artifacts.
    # --no-persist disables both the run directory and the worktree.
    worktree_manager = WorktreeManager() if not args.no_persist else None

    print("=" * 60)
    print("  AI Ops — Dispatch Pipeline")
    print("=" * 60)
    print(f"  Run ID:    {run_id}")
    print(f"  LLM:       {llm_client.provider_name} ({llm_client.model_name})")
    print(f"  Approval:  {'auto' if args.no_interactive else 'interactive'}")
    print(f"  Persist:   {'yes' if not args.no_persist else 'no'}")
    print(f"  Worktree:  {'yes' if worktree_manager else 'no'}")
    print(f"  Task:      {args.task}")
    if args.criteria:
        print(f"  Criteria:  {len(args.criteria)} items")
    print("=" * 60)
    print()

    # Import pipeline (requires langgraph)
    try:
        from workflows.langgraph.graphs.dispatch_pipeline import create_pipeline
    except ImportError as e:
        print(f"ERROR: {e}")
        print("Install with: pip install langgraph")
        sys.exit(1)

    # Create and run pipeline
    pipeline = create_pipeline(
        llm_client=llm_client,
        approval_handler=approval_handler,
        persistence=persistence,
        persist_results=not args.no_persist,
        worktree_manager=worktree_manager,
    )

    initial_state = {
        "run_id": run_id,
        "task_description": args.task,
        "acceptance_criteria": args.criteria,
        "constraints": args.constraint,
        "approval_level": args.approval_level,
    }

    print("Running pipeline...")
    print()

    try:
        result = pipeline.invoke(initial_state)
    except KeyboardInterrupt:
        print("\nPipeline cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nPipeline failed: {e}")
        logging.getLogger(__name__).exception("Pipeline failed")
        sys.exit(1)

    # Print results
    print()
    print("=" * 60)
    print("  Pipeline Complete")
    print("=" * 60)
    print(f"  Status:    {result.get('status', 'unknown')}")
    print(f"  Stage:     {result.get('current_stage', 'unknown')}")
    print(f"  Errors:    {len(result.get('errors', []))}")

    # Dispatcher summary
    dispatcher_out = result.get("dispatcher_output", {})
    classification = dispatcher_out.get("classification", {})
    if classification:
        print(f"  Type:      {classification.get('task_type', 'unknown')}")
        print(f"  Agents:    {classification.get('required_agents', [])}")

    # Reviewer verdict
    reviewer_out = result.get("reviewer_output", {})
    if reviewer_out:
        print(f"  Verdict:   {reviewer_out.get('verdict', 'none')}")
        revision_count = result.get("revision_count", 0)
        if revision_count:
            print(f"  Revisions: {revision_count}")

    # Approval decisions
    decisions = result.get("approval_decisions", [])
    if decisions:
        print(f"  Approvals: {len(decisions)} decision(s)")
        for d in decisions:
            print(f"    - L{d.get('level', '?')}: {d.get('result', 'unknown')}")

    print("=" * 60)

    # Show errors if any
    errors = result.get("errors", [])
    if errors:
        print("\nErrors:")
        for err in errors:
            print(f"  - {err}")

    # Show persistence info
    if not args.no_persist:
        run_id = result.get("run_id", run_id)
        print(f"\nRun persisted. Check:")
        final_status = result.get("status", "completed")
        # needs_revision and completed both land in completed/ (pipeline ran fully)
        # blocked, denied, failed land in failed/
        loc = "completed" if final_status in ("completed", "needs_revision") else "failed"
        print(f"  runs/{loc}/{run_id}/")
        print(f"  memory/run-summaries/{run_id}.yaml")

    print()


if __name__ == "__main__":
    main()
