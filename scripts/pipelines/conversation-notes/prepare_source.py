#!/usr/bin/env python3
"""Prepare conversation-notes source artifacts."""

from __future__ import annotations

from pathlib import Path

from common import conversation_input_text, read_stdin, resolve_session_context, run_dir, save_session_context


def main() -> None:
    """
    Prepare and persist conversation-notes source artifacts from standard input.
    
    Reads text from stdin, resolves a session context, ensures the run directory exists, writes a `session_context.json` and a `conversation_input.md` inside the run directory, and prints the session's input path.
    """
    stdin_text = read_stdin()
    context, raw_text = resolve_session_context(stdin_text)

    current_run_dir = run_dir()
    current_run_dir.mkdir(parents=True, exist_ok=True)

    session_context_path = current_run_dir / "session_context.json"
    conversation_input_path = current_run_dir / "conversation_input.md"

    save_session_context(session_context_path, context)
    conversation_input_path.write_text(conversation_input_text(context, raw_text), encoding="utf-8")

    print(str(Path(context.input_path)))


if __name__ == "__main__":
    main()
