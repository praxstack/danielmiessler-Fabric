#!/usr/bin/env python3
"""Validate conversation-notes outputs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from common import load_session_context, run_dir


REQUIRED_HEADINGS = [
    "# 🧠 Therapy Conversation Notes",
    "## Conversation Summary",
    "## Emotional Signals",
    "## Thought Patterns",
    "## Actionable Reflection",
    "## Safety and Boundaries",
]

REQUIRED_SNAPSHOT_KEYS = [
    "summary_points",
    "emotions_observed",
    "patterns_observed",
    "actions",
    "safety_flags",
]


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments and require a session context path.
    
    Returns:
        argparse.Namespace: Parsed arguments with a required attribute `session_context`
        (string) corresponding to the provided `--session-context` option.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-context", required=True)
    return parser.parse_args()


def section_body(final_notes: str, heading: str) -> str:
    """
    Extract the markdown content under a specific heading from a notes document.
    
    Parameters:
        final_notes (str): Full markdown document to search.
        heading (str): Exact heading line to locate (for example "## Actionable Reflection").
    
    Returns:
        str: The text between the specified heading and the next level-2 heading ("## "), or an empty string if the heading is not present.
    """
    marker = "\n" + heading + "\n"
    start = final_notes.find(marker)
    if start < 0:
        if final_notes.startswith(heading + "\n"):
            start = 0
            offset = len(heading) + 1
        else:
            return ""
    else:
        start += 1
        offset = len(heading) + 1

    body_start = start + offset
    next_heading = final_notes.find("\n## ", body_start)
    if next_heading < 0:
        return final_notes[body_start:]
    return final_notes[body_start:next_heading]


def count_bullets(markdown: str) -> int:
    """
    Count the number of markdown bullet lines in the given text.
    
    Parameters:
        markdown (str): Markdown content to scan for bullet lines starting with optional whitespace followed by '-' or '*'.
    
    Returns:
        int: Number of lines that are markdown bullets.
    """
    return len(re.findall(r"(?m)^\s*[-*]\s+", markdown))


def first_nonempty_line(markdown: str) -> str:
    """
    Return the first non-empty line from the given markdown, trimmed of surrounding whitespace.
    
    Returns:
        The first non-empty line as a string with leading and trailing whitespace removed, or an empty string if no non-empty lines are present.
    """
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def validate_outputs(session_context) -> list[str]:
    """
    Validate generated conversation notes and the analysis snapshot for required structure and content.
    
    Checks performed:
    - existence and JSON validity of analysis_snapshot.json in session_context.stable_pipeline_dir and presence of REQUIRED_SNAPSHOT_KEYS as arrays of strings
    - existence of the final conversation notes at session_context.final_output_path
    - document starts with the required main title heading and contains all REQUIRED_HEADINGS
    - "## Actionable Reflection" contains at least 3 bullet items
    - "## Safety and Boundaries" contains the phrase "not a substitute for professional care"
    - final notes do not contain raw artifact markers like <<<BEGIN_ARTIFACT: or <<<END_ARTIFACT>>>
    
    Parameters:
        session_context: An object with at least the attributes `stable_pipeline_dir` (path to the stable pipeline directory)
                         and `final_output_path` (path to the final conversation notes file).
    
    Returns:
        list[str]: A list of human-readable issue messages found during validation. Returns an empty list when no issues are detected.
    """
    issues: list[str] = []

    stable_pipeline_dir = Path(session_context.stable_pipeline_dir)
    snapshot_path = stable_pipeline_dir / "analysis_snapshot.json"
    if not snapshot_path.exists():
        issues.append(f"missing analysis snapshot: {snapshot_path}")
    else:
        try:
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as err:
            issues.append(f"analysis_snapshot.json is not valid JSON: {err}")
        else:
            if not isinstance(snapshot, dict):
                issues.append("analysis_snapshot.json must be a JSON object")
            else:
                for key in REQUIRED_SNAPSHOT_KEYS:
                    if key not in snapshot:
                        issues.append(f"analysis_snapshot.json missing key: {key}")
                        continue
                    value = snapshot[key]
                    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                        issues.append(f"analysis_snapshot.json key '{key}' must be an array of strings")

    final_output_path = Path(session_context.final_output_path)
    if not final_output_path.exists():
        issues.append(f"missing conversation notes: {final_output_path}")
        return issues

    final_notes = final_output_path.read_text(encoding="utf-8")
    if not first_nonempty_line(final_notes).startswith(REQUIRED_HEADINGS[0]):
        issues.append(f"document must start with title heading: {REQUIRED_HEADINGS[0]}")

    for heading in REQUIRED_HEADINGS[1:]:
        if heading not in final_notes:
            issues.append(f"missing heading: {heading}")

    reflection_body = section_body(final_notes, "## Actionable Reflection")
    if count_bullets(reflection_body) < 3:
        issues.append("Actionable Reflection must include at least 3 bullet items")

    boundaries_body = section_body(final_notes, "## Safety and Boundaries").lower()
    if "not a substitute for professional care" not in boundaries_body:
        issues.append("Safety and Boundaries must include professional-care disclaimer language")

    if "<<<BEGIN_ARTIFACT:" in final_notes or "<<<END_ARTIFACT>>>" in final_notes:
        issues.append("final notes contain raw artifact markers")

    return issues


def write_report(report_path: Path, issues: list[str]) -> None:
    """
    Write a Markdown validation report to the given path.
    
    When issues are present the report contains "status: fail" and a bulleted list of each issue.
    When no issues are present the report contains "status: pass" and a short success message.
    The target directory is created if it does not exist and the file is written using UTF-8.
    
    Parameters:
        report_path (Path): Filesystem path where the report will be written.
        issues (list[str]): List of validation issue messages; an empty list indicates no issues.
    """
    lines = ["# Validation Report", ""]
    if issues:
        lines.extend(["status: fail", ""])
        lines.extend(f"- {issue}" for issue in issues)
    else:
        lines.extend(["status: pass", "", "- Therapy conversation notes outputs are present and valid."])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    """
    Orchestrates validation of conversation-note outputs and writes pass/fail reports.
    
    Runs the validation pipeline: parses CLI args to load the session context, validates outputs to collect issue messages, writes a validation report to both the current run directory and the stable pipeline directory, and exits with a non-zero status when any issues are found.
    
    Raises:
        SystemExit: If validation issues are present; the exception message contains each issue on a separate line.
    """
    args = parse_args()
    session_context = load_session_context(Path(args.session_context))
    issues = validate_outputs(session_context)

    current_run_dir = run_dir()
    run_report_path = current_run_dir / "validation_report.md"
    stable_report_path = Path(session_context.stable_pipeline_dir) / "validation_report.md"
    write_report(run_report_path, issues)
    write_report(stable_report_path, issues)

    if issues:
        raise SystemExit("\n".join(issues))


if __name__ == "__main__":
    main()
