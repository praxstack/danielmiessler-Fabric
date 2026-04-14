#!/usr/bin/env python3
"""Live provider-backed smoke suite for model-backed built-in pipelines.

This script executes a bounded pipeline slice for each built-in pipeline that
contains model-backed `fabric_pattern` stages. It stops at the first model
stage (`--to-stage <stage-id>`) to keep latency and token usage predictable.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SmokeCase:
    pipeline: str
    to_stage: str
    stdin_text: str


GENERAL_SOURCE_TEXT = """\
Today we explored retrieval systems and prompting strategy.
The speaker compared sparse retrieval versus dense retrieval, then explained
hybrid retrieval and reranking.
The final section focused on how to validate claims against source material.
"""

NOTE_ENHANCEMENT_TEXT = """\
# rough notes
- talked about retrieval strategies
- sparse search is cheap and transparent
- dense search helps semantic matching
- use reranking before final answer
"""

THERAPY_SOURCE_TEXT = """\
Client shared difficulty with evening anxiety and rumination.
Client noticed episodes increase after social conflict and poor sleep.
We reflected on grounding patterns that have helped before and identified
small, realistic next actions for the coming week.
"""

ZOOM_CAPTION_TEXT = """\
[Instructor] 00:00:01
Welcome everyone. Today we cover deterministic pipelines.
[Instructor] 00:00:08
We begin with source ingestion and then build stable artifacts.
[Student] 00:00:17
How do we validate output quality before publishing?
[Instructor] 00:00:23
Use explicit validation stages and fail fast on contract violations.
"""


DEFAULT_CASES: tuple[SmokeCase, ...] = (
    SmokeCase(
        pipeline="study-guide-technical",
        to_stage="semantic_map_generate",
        stdin_text=GENERAL_SOURCE_TEXT,
    ),
    SmokeCase(
        pipeline="study-guide-conceptual",
        to_stage="semantic_map_generate",
        stdin_text=GENERAL_SOURCE_TEXT,
    ),
    SmokeCase(
        pipeline="enhance-notes",
        to_stage="enhance_generate",
        stdin_text=NOTE_ENHANCEMENT_TEXT,
    ),
    SmokeCase(
        pipeline="conversation-notes",
        to_stage="analyze_generate",
        stdin_text=THERAPY_SOURCE_TEXT,
    ),
    SmokeCase(
        pipeline="zoom-tech-note",
        to_stage="stage1_refine_generate",
        stdin_text=ZOOM_CAPTION_TEXT,
    ),
    SmokeCase(
        pipeline="zoom-tech-note-deep-pass",
        to_stage="stage1_refine_generate",
        stdin_text=ZOOM_CAPTION_TEXT,
    ),
    SmokeCase(
        pipeline="transcript-to-notes",
        to_stage="generate_notes",
        stdin_text=GENERAL_SOURCE_TEXT,
    ),
    SmokeCase(
        pipeline="summarize",
        to_stage="generate_summary",
        stdin_text=GENERAL_SOURCE_TEXT,
    ),
    SmokeCase(
        pipeline="extract-insights",
        to_stage="generate_insights",
        stdin_text=GENERAL_SOURCE_TEXT,
    ),
)


def parse_args() -> argparse.Namespace:
    """
    Builds and parses command-line arguments for running the live model-backed smoke test suite.
    
    Returns:
        argparse.Namespace: Parsed arguments with attributes:
            fabric_bin (str): Path to the fabric binary (default "./fabric" or overridden by --fabric-bin).
            vendor (str): Vendor name (default from SMOKE_VENDOR env or "OpenAI").
            model (str): Model id (default from SMOKE_MODEL env or "gpt-4.1-mini").
            pipelines (str): Optional comma-separated pipeline subset (default from SMOKE_PIPELINES env or empty).
            cwd (str): Working directory for fabric execution (default ".").
            timeout_seconds (int): Per-pipeline timeout in seconds (default from SMOKE_TIMEOUT_SECONDS env or 240).
            list_cases (bool): If true, print available smoke cases and exit.
    """
    parser = argparse.ArgumentParser(description="Run live model-backed smoke checks for built-in pipelines.")
    parser.add_argument("--fabric-bin", default="./fabric", help="Path to the fabric binary")
    parser.add_argument("--vendor", default=os.environ.get("SMOKE_VENDOR", "OpenAI"), help="Vendor name")
    parser.add_argument("--model", default=os.environ.get("SMOKE_MODEL", "gpt-4.1-mini"), help="Model id")
    parser.add_argument(
        "--pipelines",
        default=os.environ.get("SMOKE_PIPELINES", "").strip(),
        help="Optional comma-separated pipeline subset",
    )
    parser.add_argument("--cwd", default=".", help="Working directory for fabric execution")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=int(os.environ.get("SMOKE_TIMEOUT_SECONDS", "240")),
        help="Per-pipeline timeout in seconds",
    )
    parser.add_argument("--list-cases", action="store_true", help="Print available smoke cases and exit")
    return parser.parse_args()


def parse_events(stderr_text: str) -> list[dict[str, Any]]:
    """
    Extract JSON event objects from a stderr text blob.
    
    Parameters:
        stderr_text (str): Multiline stderr output; lines beginning with "{" are attempted to be parsed as JSON.
    
    Returns:
        list[dict[str, Any]]: List of parsed event dictionaries that contain a string "type" field.
    """
    events: list[dict[str, Any]] = []
    for raw_line in stderr_text.splitlines():
        line = raw_line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            decoded = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict) and isinstance(decoded.get("type"), str):
            events.append(decoded)
    return events


def event_exists(events: list[dict[str, Any]], event_type: str, stage_id: str | None = None) -> bool:
    """
    Determine whether the event list contains an event with the specified type and, if provided, the specified stage identifier.
    
    Parameters:
        events (list[dict[str, Any]]): Sequence of event dictionaries (each expected to have a `"type"` key and optionally a `"stage_id"` key).
        event_type (str): The event `type` value to search for.
        stage_id (str | None): If provided, require the event's `"stage_id"` to equal this value.
    
    Returns:
        `true` if a matching event exists, `false` otherwise.
    """
    for event in events:
        if event.get("type") != event_type:
            continue
        if stage_id is not None and event.get("stage_id") != stage_id:
            continue
        return True
    return False


def summarize_tail(value: str, limit: int = 1400) -> str:
    """
    Return the last `limit` characters of a string, or the original string if it is shorter than `limit`.
    
    Parameters:
        value (str): Input string to trim.
        limit (int): Maximum number of characters to keep from the end of `value`.
    
    Returns:
        str: The original `value` when its length is less than or equal to `limit`, otherwise the trailing `limit` characters of `value`.
    """
    if len(value) <= limit:
        return value
    return value[-limit:]


def run_case(case: SmokeCase, fabric_bin: Path, cwd: Path, vendor: str, model: str, timeout_seconds: int) -> None:
    """
    Run a single smoke test case by invoking the fabric CLI, validate pipeline events, and print a pass line on success.
    
    Executes the fabric binary for the given SmokeCase with the specified vendor and model, waits up to timeout_seconds, parses JSON pipeline events from stderr, and verifies that the target stage started and passed and that the final run_summary reports "passed". On success prints a single PASS line with elapsed seconds.
    
    Parameters:
        case (SmokeCase): The smoke test case describing pipeline, to_stage, and stdin_text.
        fabric_bin (Path): Path to the fabric executable to invoke.
        cwd (Path): Working directory in which to run the fabric command.
        vendor (str): Vendor identifier to pass to fabric.
        model (str): Model identifier to pass to fabric.
        timeout_seconds (int): Per-case timeout in seconds.
    
    Raises:
        RuntimeError: If the subprocess times out while waiting for the target stage.
        RuntimeError: If the fabric process exits with a non-zero return code (includes stderr/stdout tails).
        RuntimeError: If no JSON events are observed on stderr.
        RuntimeError: If a `stage_started` or `stage_passed` event for the target stage is missing.
        RuntimeError: If no `run_summary` event is present or its last status is not `"passed"`.
    """
    cmd = [
        str(fabric_bin),
        "--pipeline",
        case.pipeline,
        "--to-stage",
        case.to_stage,
        "--pipeline-events-json",
        "--vendor",
        vendor,
        "--model",
        model,
    ]

    started_at = time.monotonic()
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(cwd),
            input=case.stdin_text,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started_at
        raise RuntimeError(
            f"{case.pipeline}: timed out after {elapsed:.2f}s while waiting for stage {case.to_stage} "
            f"(timeout={timeout_seconds}s per pipeline case)"
        ) from exc
    elapsed = time.monotonic() - started_at

    if completed.returncode != 0:
        raise RuntimeError(
            f"{case.pipeline}: non-zero exit ({completed.returncode})\n"
            f"stderr tail:\n{summarize_tail(completed.stderr)}\n"
            f"stdout tail:\n{summarize_tail(completed.stdout)}"
        )

    events = parse_events(completed.stderr)
    if not events:
        raise RuntimeError(f"{case.pipeline}: no JSON events observed on stderr")

    if not event_exists(events, "stage_started", stage_id=case.to_stage):
        raise RuntimeError(f"{case.pipeline}: missing stage_started event for {case.to_stage}")
    if not event_exists(events, "stage_passed", stage_id=case.to_stage):
        raise RuntimeError(f"{case.pipeline}: missing stage_passed event for {case.to_stage}")

    run_summaries = [event for event in events if event.get("type") == "run_summary"]
    if not run_summaries:
        raise RuntimeError(f"{case.pipeline}: missing run_summary event")
    if run_summaries[-1].get("status") != "passed":
        raise RuntimeError(f"{case.pipeline}: run_summary status is not passed")

    print(f"PASS {case.pipeline} -> {case.to_stage} ({elapsed:.2f}s)")


def select_cases(pipeline_filter: str) -> list[SmokeCase]:
    """
    Selects smoke test cases filtered by a comma-separated pipeline list.
    
    Parameters:
        pipeline_filter (str): Comma-separated pipeline identifiers to include; if empty or falsey, all default cases are returned.
    
    Returns:
        list[SmokeCase]: The list of matching SmokeCase entries in the original DEFAULT_CASES order.
    
    Raises:
        ValueError: If any identifier in `pipeline_filter` does not match a known pipeline.
    """
    if not pipeline_filter:
        return list(DEFAULT_CASES)

    requested = {item.strip() for item in pipeline_filter.split(",") if item.strip()}
    unknown = requested.difference({case.pipeline for case in DEFAULT_CASES})
    if unknown:
        unknown_list = ", ".join(sorted(unknown))
        raise ValueError(f"unknown pipeline(s) in --pipelines: {unknown_list}")

    return [case for case in DEFAULT_CASES if case.pipeline in requested]


def main() -> int:
    """
    Run the live smoke test suite for built-in pipelines.
    
    Parses command-line arguments, optionally lists available smoke cases and exits, validates the fabric binary and working directory, selects the requested test cases, executes each case via run_case, and returns on successful completion.
    
    Returns:
        int: 0 on successful completion.
    
    Raises:
        FileNotFoundError: if the specified fabric binary does not exist.
        NotADirectoryError: if the specified working directory does not exist or is not a directory.
    """
    args = parse_args()
    suite_started_at = time.monotonic()

    if args.list_cases:
        for case in DEFAULT_CASES:
            print(f"{case.pipeline}:{case.to_stage}")
        return 0

    fabric_bin = Path(args.fabric_bin).expanduser().resolve()
    if not fabric_bin.exists():
        raise FileNotFoundError(f"fabric binary not found: {fabric_bin}")

    cwd = Path(args.cwd).expanduser().resolve()
    if not cwd.exists() or not cwd.is_dir():
        raise NotADirectoryError(f"invalid working directory: {cwd}")

    cases = select_cases(args.pipelines)
    print(
        f"Running {len(cases)} live smoke case(s) with vendor={args.vendor!r} model={args.model!r} cwd={cwd}"
    )
    for case in cases:
        run_case(
            case=case,
            fabric_bin=fabric_bin,
            cwd=cwd,
            vendor=args.vendor,
            model=args.model,
            timeout_seconds=args.timeout_seconds,
        )

    suite_elapsed = time.monotonic() - suite_started_at
    print(f"All live pipeline smoke checks passed in {suite_elapsed:.2f}s.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:  # pragma: no cover - script-level error boundary
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
