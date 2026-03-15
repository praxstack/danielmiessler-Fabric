#!/usr/bin/env python3
"""Materialize final notes for study-guide-conceptual."""

from __future__ import annotations

import argparse
from pathlib import Path

from artifact_blocks import require_blocks
from common import load_session_context, run_dir


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for the script.
    
    Parameters:
        --session-context (str): Path to a session context file used to configure output locations; this argument is required.
    
    Returns:
        argparse.Namespace: Namespace containing a `session_context` attribute with the provided path.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-context", required=True)
    return parser.parse_args()


def main() -> None:
    """
    Materialize the extracted "final_notes.md" block: normalize it, write it to run and stable output locations, and print it.
    
    Reads the session context path from command-line args, extracts the "final_notes.md" block from stdin, trims trailing newlines and ensures a single trailing newline, writes the resulting content to a per-run file at run_dir()/final_notes.md and to the stable path specified by session_context.final_output_path (creating parent directories as needed), then writes the content to standard output.
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
