#!/usr/bin/env python3
"""Shared helpers for the Fabric-native conversation-notes pipeline."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path


FABRIC_RUN_DIR_ENV = "FABRIC_PIPELINE_RUN_DIR"
FABRIC_SOURCE_MODE_ENV = "FABRIC_PIPELINE_SOURCE_MODE"
FABRIC_SOURCE_REFERENCE_ENV = "FABRIC_PIPELINE_SOURCE_REFERENCE"
FABRIC_INVOCATION_DIR_ENV = "FABRIC_PIPELINE_INVOCATION_DIR"


@dataclass
class SessionContext:
    source_mode: str
    source_reference: str
    invocation_dir: str
    session_dir: str
    input_path: str
    session_name: str
    session_id: str
    stable_pipeline_dir: str
    final_output_path: str
    context_root: str


def slugify(value: str) -> str:
    """
    Convert a string into a lowercase, dash-separated token suitable for identifiers.
    
    Returns:
        A slugified string containing only lowercase letters, digits, and hyphens; returns "session" if the result would be empty.
    """
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "session"


def env_path(name: str) -> Path:
    """
    Resolve and return an absolute Path from a required environment variable.
    
    Parameters:
        name (str): The environment variable name to read.
    
    Returns:
        Path: The environment variable's value expanded (tilde) and resolved to an absolute path.
    
    Raises:
        RuntimeError: If the environment variable is not set or empty.
    """
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return Path(value).expanduser().resolve()


def run_dir() -> Path:
    """
    Resolve the pipeline run directory from the FABRIC_PIPELINE_RUN_DIR environment variable.
    
    Returns:
        Path: Resolved absolute path to the pipeline run directory.
    """
    return env_path(FABRIC_RUN_DIR_ENV)


def invocation_dir() -> Path:
    """
    Return the invocation directory path configured via the FABRIC_PIPELINE_INVOCATION_DIR environment variable.
    
    Returns:
        Path: The resolved invocation directory path.
    
    Raises:
        EnvironmentError: If FABRIC_PIPELINE_INVOCATION_DIR is not set or cannot be resolved to a valid path.
    """
    return env_path(FABRIC_INVOCATION_DIR_ENV)


def source_mode() -> str:
    """
    Get the current source mode from the FABRIC_PIPELINE_SOURCE_MODE environment variable.
    
    Returns:
        str: The environment value with surrounding whitespace removed, or an empty string if the variable is unset.
    """
    return os.environ.get(FABRIC_SOURCE_MODE_ENV, "").strip()


def source_reference() -> str:
    """
    Retrieve the configured source reference for the current pipeline invocation.
    
    Returns:
        The value of the FABRIC_PIPELINE_SOURCE_REFERENCE environment variable with surrounding whitespace removed; an empty string if the variable is not set.
    """
    return os.environ.get(FABRIC_SOURCE_REFERENCE_ENV, "").strip()


def read_stdin() -> str:
    """
    Read all UTF-8 text from standard input.
    
    Returns:
        The full contents of standard input as a `str`.
    """
    return os.fdopen(0, "r", encoding="utf-8").read()


def resolve_input_path(path: Path) -> Path:
    """
    Resolve a filesystem path to a single conversation input file.
    
    If the given path points to a file, returns it only if it has a .md or .txt suffix; otherwise raises FileNotFoundError. If the path points to a directory, prefers a deterministic list of common transcript/notes filenames and returns the first match. If no preferred file is found, returns the single .md or .txt file in the directory when exactly one exists; otherwise raises FileNotFoundError.
    
    Parameters:
        path (Path): A file or directory path to resolve.
    
    Returns:
        resolved_path (Path): The resolved conversation input file.
    
    Raises:
        FileNotFoundError: If the path does not exist, points to an unsupported file type, or a directory does not contain a uniquely resolvable input file.
    """
    resolved = path.expanduser().resolve()
    if resolved.is_file():
        if resolved.suffix.lower() not in {".md", ".txt"}:
            raise FileNotFoundError(f"Unsupported source file type: {resolved}")
        return resolved

    if resolved.is_dir():
        preferred = [
            "transcript.md",
            "transcript.txt",
            "conversation.txt",
            "conversation.md",
            "conversation.txt",
            "notes.md",
            "notes.txt",
            "meeting_saved_closed_caption.txt",
        ]
        for candidate in preferred:
            candidate_path = resolved / candidate
            if candidate_path.exists():
                return candidate_path

        candidates = sorted(
            entry for entry in resolved.iterdir() if entry.is_file() and entry.suffix.lower() in {".md", ".txt"}
        )
        if len(candidates) == 1:
            return candidates[0]
        raise FileNotFoundError(
            f"Could not resolve unique conversation-notes input in directory: {resolved}"
        )

    raise FileNotFoundError(f"Input path not found: {resolved}")


def resolve_context_root(source_ref: str, input_path: Path, current_invocation_dir: Path) -> Path:
    """
    Determine the directory that should be used as the session's context root.
    
    If a non-empty `source_ref` is given and resolves to an existing directory, that directory is used as the base; if `source_ref` is given but is not a directory, the parent of `input_path` is used as the base. If `source_ref` is empty, `current_invocation_dir` is used as the base. The function always returns the path obtained by appending "context" to the chosen base, making context ingestion explicit and opt-in.
     
    Parameters:
        source_ref (str): Optional source reference path or identifier; may be empty.
        input_path (Path): Resolved input file path used when `source_ref` does not point to a directory.
        current_invocation_dir (Path): Invocation directory to use when `source_ref` is empty.
    
    Returns:
        Path: The context root directory (base/"context").
    """
    if source_ref:
        source_ref_path = Path(source_ref).expanduser().resolve()
        base = source_ref_path if source_ref_path.is_dir() else input_path.parent
    else:
        base = current_invocation_dir

    # Context ingestion is intentionally opt-in via a dedicated "context" directory.
    # Falling back to scanning the entire session/invocation tree can unintentionally
    # ingest unrelated files and create non-deterministic outputs.
    return base / "context"


def discover_context_files(context_root: Path, input_path: Path) -> list[Path]:
    """
    Collect files under a context root that can be used as contextual documents, excluding the input file.
    
    Parameters:
        context_root (Path): Directory to recursively search for context files.
        input_path (Path): Path to the primary input to exclude from the results.
    
    Returns:
        list[Path]: Sorted list of resolved file paths under `context_root` whose suffix is `.md`, `.txt`, or `.pdf` (case-insensitive). Returns an empty list if `context_root` does not exist or is not a directory.
    """
    if not context_root.exists() or not context_root.is_dir():
        return []

    allowed = {".md", ".txt", ".pdf"}
    files: list[Path] = []
    for path in sorted(context_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in allowed:
            continue
        if path.resolve() == input_path.resolve():
            continue
        files.append(path.resolve())
    return files


def _ephemeral_session_identity(current_source_mode: str, current_source_reference: str) -> tuple[str, str]:
    """
    Derive an ephemeral session name and session ID for stdin or scraped-url inputs.
    
    Parameters:
        current_source_mode (str): The input source mode (e.g., "stdin", "scrape_url", or other).
        current_source_reference (str): Optional source reference (e.g., a scraped URL).
    
    Returns:
        tuple[str, str]: A pair (session_name, session_id).
            - If mode is "scrape_url" and a reference is provided: both values are the slugified reference.
            - If mode is "stdin": both values are "stdin-conversation-session".
            - Otherwise: both values are "<mode>-conversation-session", using "session" when mode is empty.
    """
    if current_source_mode == "scrape_url" and current_source_reference:
        value = slugify(current_source_reference)
        return value, value
    if current_source_mode == "stdin":
        return "stdin-conversation-session", "stdin-conversation-session"
    mode = current_source_mode or "session"
    return f"{mode}-conversation-session", f"{mode}-conversation-session"


def resolve_session_context(stdin_text: str) -> tuple[SessionContext, str]:
    """
    Construct a SessionContext for the current invocation and return it along with the resolved raw input text.
    
    Parameters:
        stdin_text (str): Text read from standard input; used as the session input when the source mode is "stdin" or "scrape_url".
    
    Returns:
        tuple[SessionContext, str]: A tuple containing the populated SessionContext and the raw input text.
    
    Notes:
        - When the current source mode is "source" and a source reference is provided, the function resolves that reference to an input file, reads its contents, and derives persistent session paths from the input's location.
        - When the source mode is "stdin" or "scrape_url", the function uses the invocation/run directories, returns an ephemeral session identity, and writes stdin_text to a file under the run directory to serve as the resolved input.
        - Raises RuntimeError if the source mode is not one of "source", "stdin", or "scrape_url".
    """
    current_invocation_dir = invocation_dir()
    current_source_mode = source_mode()
    current_source_reference = source_reference()

    if current_source_mode == "source" and current_source_reference:
        resolved_input = resolve_input_path(Path(current_source_reference))
        session_dir = resolved_input.parent
        stable_pipeline_dir = session_dir / ".pipeline"
        final_output_path = session_dir / "conversation_notes.md"
        session_name = session_dir.name
        session_id = slugify(session_name)
        raw_text = resolved_input.read_text(encoding="utf-8")
        context_root = resolve_context_root(current_source_reference, resolved_input, current_invocation_dir)
    elif current_source_mode in {"stdin", "scrape_url"}:
        session_dir = current_invocation_dir
        stable_pipeline_dir = run_dir()
        final_output_path = run_dir() / "conversation_notes.md"
        resolved_input = run_dir() / "source_input.md"
        raw_text = stdin_text
        resolved_input.parent.mkdir(parents=True, exist_ok=True)
        resolved_input.write_text(raw_text, encoding="utf-8")
        session_name, session_id = _ephemeral_session_identity(current_source_mode, current_source_reference)
        context_root = resolve_context_root("", resolved_input, current_invocation_dir)
    else:
        raise RuntimeError(
            "conversation-notes supports source files/directories, stdin, or scrape_url input; "
            f"got source mode {current_source_mode!r}"
        )

    context = SessionContext(
        source_mode=current_source_mode,
        source_reference=current_source_reference,
        invocation_dir=str(current_invocation_dir),
        session_dir=str(session_dir),
        input_path=str(resolved_input),
        session_name=session_name,
        session_id=session_id,
        stable_pipeline_dir=str(stable_pipeline_dir),
        final_output_path=str(final_output_path),
        context_root=str(context_root),
    )
    return context, raw_text


def save_session_context(path: Path, context: SessionContext) -> None:
    """
    Persist a SessionContext as a JSON file at the given filesystem path.
    
    Parameters:
        path (Path): Destination file path where the session context will be written. Parent directories will be created if they do not exist.
        context (SessionContext): The session context to serialize.
    
    Notes:
        The context is written as pretty-printed UTF-8 JSON with a trailing newline.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(context), ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def load_session_context(path: Path) -> SessionContext:
    """
    Load a SessionContext from a JSON file at the given filesystem path.
    
    Parses the file as UTF-8 JSON and constructs a SessionContext from the parsed data.
    
    Parameters:
        path (Path): Filesystem path to a JSON file containing a serialized SessionContext.
    
    Returns:
        SessionContext: The deserialized session context.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    return SessionContext(**data)


def conversation_input_text(context: SessionContext, raw_text: str) -> str:
    """
    Create a standardized Markdown payload containing session metadata, a short Instructions section, and the conversation transcript.
    
    Parameters:
        context (SessionContext): Session metadata used to populate the header (session_id, session_name, source_mode, source_reference).
        raw_text (str): The raw conversation text to include in the Transcript section.
    
    Returns:
        str: A Markdown-formatted string with a header of session fields, an Instructions section, and a fenced code block containing the trimmed `raw_text`.
    """
    return (
        "# Therapy Conversation Source\n\n"
        f"- session_id: `{context.session_id}`\n"
        f"- session_name: `{context.session_name}`\n"
        f"- source_mode: `{context.source_mode}`\n"
        f"- source_reference: `{context.source_reference or '(none)'}`\n\n"
        "## Instructions\n\n"
        "- Preserve fidelity to the source.\n"
        "- Stay non-diagnostic and non-prescriptive.\n"
        "- Focus on reflection-oriented notes and grounding actions.\n\n"
        "## Conversation Transcript\n\n"
        "```text\n"
        f"{raw_text.rstrip()}\n"
        "```\n"
    )
