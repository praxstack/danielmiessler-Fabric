#!/usr/bin/env python3
"""Prepare enhance-notes source artifacts."""

from __future__ import annotations

from pathlib import Path

from common import enhancement_input_text, read_stdin, resolve_session_context, run_dir, save_session_context


def main() -> None:
    """
    Prepare and persist enhance-notes source artifacts from standard input and print the resolved input path.
    
    Reads all data from stdin, resolves and saves a session context to a run directory as `session_context.json`, writes generated enhancement input to `enhancement_input.md` in the same directory, and prints the session's input path.
    """
    stdin_text = read_stdin()
    context, raw_text = resolve_session_context(stdin_text)

    current_run_dir = run_dir()
    current_run_dir.mkdir(parents=True, exist_ok=True)

    session_context_path = current_run_dir / "session_context.json"
    enhancement_input_path = current_run_dir / "enhancement_input.md"

    save_session_context(session_context_path, context)
    enhancement_input_path.write_text(enhancement_input_text(context, raw_text), encoding="utf-8")

    print(str(Path(context.input_path)))


if __name__ == "__main__":
    main()
