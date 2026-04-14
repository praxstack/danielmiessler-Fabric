#!/usr/bin/env python3
"""Materialize final notes for study-guide-technical."""

from __future__ import annotations

import argparse
from pathlib import Path

from artifact_blocks import require_blocks
from common import load_session_context, run_dir


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for the script.
    
    Parses a required --session-context option that provides the path to the session context file used by the script.
    
    Returns:
        argparse.Namespace: Parsed arguments with attribute `session_context` (str) containing the path supplied to --session-context.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-context", required=True)
    return parser.parse_args()


def main() -> None:
    """
    Materializes final notes read from stdin into per-run and stable output files and prints them to stdout.
    
    Reads an input document from stdin, extracts the block named "final_notes.md", normalizes its trailing newlines to a single newline, writes the result to a per-run path (run_dir()/final_notes.md) and to the session context's final_output_path (creating parent directories as needed), then prints the final notes to stdout.
    """
    args = parse_args()
    session_context = load_session_context(Path(args.session_context))
    blocks = require_blocks(Path("/dev/stdin").read_text(encoding="utf-8"), ["final_notes.md"])
    final_notes = blocks["final_notes.md"].content.rstrip("\n") + "\n"

    current_run_dir = run_dir()
    current_run_dir.mkdir(parents=True, exist_ok=True)
    run_final_output_path = current_run_dir / "final_notes.md"
    run_final_output_path.write_text(final_notes, encoding="utf-8")

    stable_final_output_path = Path(session_context.final_output_path)
    stable_final_output_path.parent.mkdir(parents=True, exist_ok=True)
    stable_final_output_path.write_text(final_notes, encoding="utf-8")

    print(final_notes, end="")


if __name__ == "__main__":
    main()
