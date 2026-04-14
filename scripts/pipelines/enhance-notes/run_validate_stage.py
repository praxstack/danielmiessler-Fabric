#!/usr/bin/env python3
"""Validate enhance-notes outputs."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import load_session_context, run_dir


REQUIRED_HEADINGS = [
    "# ✨ Enhanced Notes",
    "## Improved Summary",
    "## Key Takeaways",
    "## Clarifications Added",
    "## Suggested Next Questions",
]

REQUIRED_EDIT_LOG_HEADINGS = [
    "# Edit Log",
    "## Structural Changes",
    "## Language Tightening",
    "## Assumptions Avoided",
]


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for the validation run.
    
    Parameters:
        None
    
    Returns:
        args (argparse.Namespace): Namespace with attribute `session_context` (str) containing the path supplied to `--session-context`.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-context", required=True)
    return parser.parse_args()


def section_body(final_notes: str, heading: str) -> str:
    """
    Extract the markdown text body for the specified heading from a final notes document.
    
    Parameters:
    	 final_notes (str): Complete markdown document to search.
    	 heading (str): Exact heading line to locate (including any leading '#' characters, e.g. "## Key Takeaways").
    
    Returns:
    	The text under the specified heading up to (but not including) the next top-level "## " heading, or an empty string if the heading is not present.
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
    Count Markdown bullet list items in the given text.
    
    Returns:
        The number of lines that start with `-` or `*` followed by whitespace (Markdown bullet items).
    """
    return len(re.findall(r"(?m)^\s*[-*]\s+", markdown))


def first_nonempty_line(markdown: str) -> str:
    """
    Return the first non-empty, non-whitespace line from the given Markdown text.
    
    Parameters:
        markdown (str): The Markdown text to search.
    
    Returns:
        first_line (str): The first line containing non-whitespace characters, stripped of surrounding whitespace; an empty string if no such line exists.
    """
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def validate_outputs(session_context) -> list[str]:
    """
    Validate enhanced notes and edit log files described by the session context and return any issues found.
    
    Performs structural and content checks on the final enhanced notes and the pipeline edit log, collecting human-readable issue messages for any validation failures.
    
    Parameters:
    	session_context: An object with at least the attributes `final_output_path` (path to the enhanced notes file) and `stable_pipeline_dir` (directory containing the stable pipeline artifacts, including `edit_log.md`).
    
    Returns:
    	issues (list[str]): A list of validation issue strings; empty if no problems were found.
    """
    issues: list[str] = []
    stable_pipeline_dir = Path(session_context.stable_pipeline_dir)

    final_output_path = Path(session_context.final_output_path)
    if not final_output_path.exists():
        issues.append(f"missing enhanced notes: {final_output_path}")
        return issues

    final_notes = final_output_path.read_text(encoding="utf-8")
    if not first_nonempty_line(final_notes).startswith(REQUIRED_HEADINGS[0]):
        issues.append(f"document must start with title heading: {REQUIRED_HEADINGS[0]}")

    for heading in REQUIRED_HEADINGS[1:]:
        if heading not in final_notes:
            issues.append(f"missing heading: {heading}")

    key_takeaways_body = section_body(final_notes, "## Key Takeaways")
    if count_bullets(key_takeaways_body) < 3:
        issues.append("Key Takeaways must include at least 3 bullet items")

    if "<<<BEGIN_ARTIFACT:" in final_notes or "<<<END_ARTIFACT>>>" in final_notes:
        issues.append("enhanced notes contain raw artifact markers")

    edit_log_path = stable_pipeline_dir / "edit_log.md"
    if not edit_log_path.exists():
        issues.append(f"missing edit log: {edit_log_path}")
        return issues

    edit_log = edit_log_path.read_text(encoding="utf-8")
    for heading in REQUIRED_EDIT_LOG_HEADINGS:
        if heading not in edit_log:
            issues.append(f"missing edit log heading: {heading}")
    if "<<<BEGIN_ARTIFACT:" in edit_log or "<<<END_ARTIFACT>>>" in edit_log:
        issues.append("edit log contains raw artifact markers")

    return issues


def write_report(report_path: Path, issues: list[str]) -> None:
    """
    Write a Markdown validation report to the given file path.
    
    If `issues` is non-empty the report records `status: fail` and lists each issue as a bullet. If `issues` is empty the report records `status: pass` and includes a success note. The function ensures the destination directory exists and overwrites any existing report file.
    
    Parameters:
        report_path (Path): Destination path for the generated Markdown report.
        issues (list[str]): Validation issue messages to include; an empty list indicates no issues.
    """
    lines = ["# Validation Report", ""]
    if issues:
        lines.extend(["status: fail", ""])
        lines.extend(f"- {issue}" for issue in issues)
    else:
        lines.extend(["status: pass", "", "- Note enhancement outputs are present and valid."])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    """
    Run validation for enhanced-notes outputs and write validation reports.
    
    Loads the session context path from command-line arguments, performs validation of the final enhanced notes and edit log, writes a validation_report.md to both the current run directory and the stable pipeline directory, and terminates with a non-zero exit when validation issues are found.
    
    Raises:
        SystemExit: With newline-separated issue messages when one or more validation failures are detected.
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
