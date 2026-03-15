#!/usr/bin/env python3
"""Validate study-guide-conceptual outputs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from common import load_session_context, run_dir


REQUIRED_HEADINGS = [
    "## Session Focus",
    "## Context You Need Before This",
    "## Big Ideas",
    "## What Was Actually Said",
    "## Why It Matters",
    "## Intuition and Real-Life Examples",
    "## Argument or Theme Map",
    "## Difficult Terms Explained Simply",
    "## Misunderstandings to Avoid",
    "## Reflection Questions",
    "## Revision Summary",
    "## Connections to Other Topics",
]


def parse_args() -> argparse.Namespace:
    """
    Builds and parses command-line arguments for the validation script.
    
    Creates an ArgumentParser that requires the --session-context option.
    
    Returns:
        argparse.Namespace: Parsed arguments with attribute `session_context` containing the provided session context value.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-context", required=True)
    return parser.parse_args()


def section_body(final_notes: str, heading: str) -> str:
    """
    Extract the markdown text contained under a specified heading.
    
    Parameters:
    	final_notes (str): The full markdown content to search.
    	heading (str): The exact heading line to locate (e.g. "## Intuition and Real-Life Examples").
    
    Returns:
    	section_body (str): The substring between the given heading and the next top-level heading ("\n## "), or the remainder of the document if no subsequent top-level heading exists; returns an empty string if the heading is not present.
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
    Count Markdown bullet lines that start with '-' or '*' (optionally preceded by whitespace).
    
    Parameters:
    	markdown (str): Markdown text to analyze.
    
    Returns:
    	int: Count of lines that begin with '-' or '*' (ignoring leading whitespace) followed by a space.
    """
    return len(re.findall(r"(?m)^\s*[-*]\s+", markdown))


def validate_outputs(session_context) -> list[str]:
    """
    Validate the study-guide final notes and related pipeline artifacts and collect any issues found.
    
    Parameters:
        session_context: An object providing at least `stable_pipeline_dir` (path to the stable pipeline directory)
            and `final_output_path` (path to the generated final notes file).
    
    Returns:
        issues (list[str]): A list of validation issue messages; empty when no problems are detected.
    """
    issues: list[str] = []

    semantic_map_path = Path(session_context.stable_pipeline_dir) / "semantic_map.json"
    if not semantic_map_path.exists():
        issues.append(f"missing semantic map: {semantic_map_path}")
    else:
        try:
            data = json.loads(semantic_map_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as err:
            issues.append(f"semantic_map.json is not valid JSON: {err}")
            data = None
        if data is not None and not isinstance(data, dict):
            issues.append("semantic_map.json must be a JSON object")

    final_output_path = Path(session_context.final_output_path)
    if not final_output_path.exists():
        issues.append(f"missing final notes: {final_output_path}")
        return issues

    final_notes = final_output_path.read_text(encoding="utf-8")
    if not final_notes.lstrip().startswith("# 📝 "):
        issues.append("final notes must start with a top-level '# 📝 ' heading")
    for heading in REQUIRED_HEADINGS:
        if heading not in final_notes:
            issues.append(f"missing heading: {heading}")

    if final_notes.count("```mermaid") < 1:
        issues.append("expected at least 1 Mermaid diagram")
    if "<<<BEGIN_ARTIFACT:" in final_notes or "<<<END_ARTIFACT>>>" in final_notes:
        issues.append("final notes contain raw artifact markers")

    examples_body = section_body(final_notes, "## Intuition and Real-Life Examples")
    if count_bullets(examples_body) < 3:
        issues.append("Intuition and Real-Life Examples must include at least 3 examples")

    reflections_body = section_body(final_notes, "## Reflection Questions")
    if count_bullets(reflections_body) < 4:
        issues.append("Reflection Questions must include at least 4 questions")

    terms_body = section_body(final_notes, "## Difficult Terms Explained Simply")
    if count_bullets(terms_body) < 3:
        issues.append("Difficult Terms Explained Simply must include at least 3 terms")

    return issues


def write_report(report_path: Path, issues: list[str]) -> None:
    """
    Write a Markdown validation report to report_path summarizing any issues.
    
    If issues is non-empty, the report contains "status: fail" and a bullet list of each issue; otherwise it contains "status: pass" and a success line. The function ensures the target directory exists and writes the report as UTF-8 text with a trailing newline.
    
    Parameters:
        report_path (Path): Filesystem path where the Markdown report will be written.
        issues (list[str]): List of validation issue messages to include in the report.
    """
    lines = ["# Validation Report", ""]
    if issues:
        lines.extend(["status: fail", ""])
        lines.extend(f"- {issue}" for issue in issues)
    else:
        lines.extend(["status: pass", "", "- All required nontechnical study-guide outputs are present and valid."])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    """
    Run validation of a study-guide's conceptual outputs and emit validation reports.
    
    Parses the command-line session context, validates the generated final notes and related artifacts, writes a validation_report.md to both the current run directory and the stable pipeline directory, and exits with a non-zero status when validation issues are found.
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
