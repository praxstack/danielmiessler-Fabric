#!/usr/bin/env python3
"""Shared helpers for the Fabric-native enhance-notes pipeline."""

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


def slugify(value: str) -> str:
    """
    Convert a string into a lowercase, hyphen-separated slug suitable for filenames or identifiers.
    
    Parameters:
        value (str): Input string to convert.
    
    Returns:
        slug (str): Lowercase string where consecutive non-alphanumeric characters are replaced by single hyphens and leading/trailing hyphens are removed; returns "session" if the resulting slug is empty.
    """
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "session"


def env_path(name: str) -> Path:
    """
    Resolve the value of an environment variable to an absolute Path.
    
    Parameters:
        name (str): Name of the environment variable to read.
    
    Returns:
        Path: The environment variable's value expanded (tilde) and resolved to an absolute path.
    
    Raises:
        RuntimeError: If the environment variable is not set or is empty.
    """
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return Path(value).expanduser().resolve()


def run_dir() -> Path:
    """
    Resolve the pipeline run directory from the FABRIC_RUN_DIR environment variable.
    
    Returns:
        run_dir (Path): Expanded, resolved path for the run directory.
    
    Raises:
        RuntimeError: If the FABRIC_RUN_DIR environment variable is not set.
    """
    return env_path(FABRIC_RUN_DIR_ENV)


def invocation_dir() -> Path:
    """
    Get the configured invocation directory path from the environment.
    
    Returns:
        Path: The expanded, resolved invocation directory path obtained from the
        environment variable FABRIC_INVOCATION_DIR_ENV.
    
    Raises:
        RuntimeError: If the FABRIC_INVOCATION_DIR_ENV environment variable is not set.
    """
    return env_path(FABRIC_INVOCATION_DIR_ENV)


def source_mode() -> str:
    """
    Retrieve the configured pipeline source mode from the environment.
    
    Returns:
        str: The value of FABRIC_PIPELINE_SOURCE_MODE with surrounding whitespace removed; an empty string if the variable is unset.
    """
    return os.environ.get(FABRIC_SOURCE_MODE_ENV, "").strip()


def source_reference() -> str:
    """
    Get the pipeline source reference from the environment.
    
    Reads the FABRIC_PIPELINE_SOURCE_REFERENCE environment variable and trims surrounding whitespace.
    
    Returns:
        The source reference string with surrounding whitespace removed, or an empty string if the variable is not set.
    """
    return os.environ.get(FABRIC_SOURCE_REFERENCE_ENV, "").strip()


def read_stdin() -> str:
    """
    Read all data from standard input decoded as UTF-8.
    
    Returns:
        text (str): The complete contents of standard input as a UTF-8 string.
    """
    return os.fdopen(0, "r", encoding="utf-8").read()


def resolve_input_path(path: Path) -> Path:
    """
    Resolve an input path to a single Markdown or text file to use as the enhance-notes source.
    
    If `path` is a file, validates that its extension is `.md` or `.txt` and returns it.
    If `path` is a directory, searches for a preferred filename (in priority order) and returns the first match. If no preferred file is found, returns the single `.md` or `.txt` file in the directory when exactly one exists; otherwise raises an error.
    If `path` does not exist or a suitable file cannot be determined, raises FileNotFoundError.
    
    Parameters:
        path (Path): File or directory path to resolve.
    
    Returns:
        Path: Resolved path to the chosen `.md` or `.txt` file.
    
    Raises:
        FileNotFoundError: If the path does not exist, if a file has an unsupported extension, or if a unique input file cannot be determined in a directory.
    """
    resolved = path.expanduser().resolve()
    if resolved.is_file():
        if resolved.suffix.lower() not in {".md", ".txt"}:
            raise FileNotFoundError(f"Unsupported source file type: {resolved}")
        return resolved

    if resolved.is_dir():
        preferred = [
            "final_notes.md",
            "enhanced_notes.md",
            "notes.md",
            "transcript.md",
            "transcript.txt",
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
        raise FileNotFoundError(f"Could not resolve unique enhance-notes input in directory: {resolved}")

    raise FileNotFoundError(f"Input path not found: {resolved}")


def _ephemeral_session_identity(current_source_mode: str, current_source_reference: str) -> tuple[str, str]:
    """
    Create a synthetic session name and session id for ephemeral inputs (stdin or scraped URLs) or derive a default name from the provided source mode.
    
    Parameters:
    	current_source_mode (str): The source mode value (e.g., "stdin", "scrape_url", "source"); may be empty.
    	current_source_reference (str): An optional source reference such as a URL; used when mode is "scrape_url".
    
    Returns:
    	tuple[str, str]: (session_name, session_id). For mode "scrape_url" with a reference, returns the slugified reference for both values. For "stdin", returns "stdin-enhance-notes" for both. Otherwise returns "<mode>-enhance-notes" (uses "session" when mode is empty).
    """
    if current_source_mode == "scrape_url" and current_source_reference:
        value = slugify(current_source_reference)
        return value, value
    if current_source_mode == "stdin":
        return "stdin-enhance-notes", "stdin-enhance-notes"
    mode = current_source_mode or "session"
    return f"{mode}-enhance-notes", f"{mode}-enhance-notes"


def resolve_session_context(stdin_text: str) -> tuple[SessionContext, str]:
    """
    Resolve and return the session context and the raw notes text for the current invocation.
    
    Parameters:
        stdin_text (str): Text read from standard input; used when the source mode is "stdin" or "scrape_url".
    
    Returns:
        tuple[SessionContext, str]: A tuple containing the resolved SessionContext and the raw notes text.
    
    Behavior:
        - When the source mode is "source" and a source reference is provided, the function resolves that path (file or directory), reads the referenced input file into memory, and derives session directories, names, and identifiers from the input location.
        - When the source mode is "stdin" or "scrape_url", the function uses the invocation/run directories for session storage, writes `stdin_text` to run_dir()/source_input.md, and generates an ephemeral session name and id.
        - The returned SessionContext fields containing paths are stringified Path values.
    
    Raises:
        RuntimeError: If the current source mode is not "source", "stdin", or "scrape_url".
    """
    current_invocation_dir = invocation_dir()
    current_source_mode = source_mode()
    current_source_reference = source_reference()

    if current_source_mode == "source" and current_source_reference:
        resolved_input = resolve_input_path(Path(current_source_reference))
        session_dir = resolved_input.parent
        stable_pipeline_dir = session_dir / ".pipeline"
        final_output_path = session_dir / "enhanced_notes.md"
        session_name = session_dir.name
        session_id = slugify(session_name)
        raw_text = resolved_input.read_text(encoding="utf-8")
    elif current_source_mode in {"stdin", "scrape_url"}:
        session_dir = current_invocation_dir
        stable_pipeline_dir = run_dir()
        final_output_path = run_dir() / "enhanced_notes.md"
        resolved_input = run_dir() / "source_input.md"
        raw_text = stdin_text
        resolved_input.parent.mkdir(parents=True, exist_ok=True)
        resolved_input.write_text(raw_text, encoding="utf-8")
        session_name, session_id = _ephemeral_session_identity(current_source_mode, current_source_reference)
    else:
        raise RuntimeError(
            "enhance-notes supports source files/directories, stdin, or scrape_url input; "
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
    )
    return context, raw_text


def save_session_context(path: Path, context: SessionContext) -> None:
    """
    Write the SessionContext as a pretty-printed JSON file to the given path, creating parent directories if needed.
    
    Parameters:
    	path (Path): Destination file path for the JSON session context.
    	context (SessionContext): Dataclass instance to serialize.
    
    Notes:
    	The JSON is written with ASCII-safe characters, an indentation of 2 spaces, and ends with a single trailing newline.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(context), ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def load_session_context(path: Path) -> SessionContext:
    """
    Load a SessionContext from a JSON file stored at the given path.
    
    Parameters:
        path (Path): Filesystem path to a UTF-8 encoded JSON file that contains a serialized SessionContext.
    
    Returns:
        SessionContext: The SessionContext reconstructed from the file's JSON contents.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    return SessionContext(**data)


def enhancement_input_text(context: SessionContext, raw_text: str) -> str:
    """
    Builds a Markdown document embedding session metadata, an enhancement contract, and the provided raw notes.
    
    Parameters:
        context (SessionContext): Session metadata (session_id, session_name, source_mode, source_reference) included in the document header.
        raw_text (str): The original notes text; placed verbatim inside a fenced code block with trailing whitespace removed.
    
    Returns:
        markdown (str): A Markdown-formatted string suitable as input for the enhancement pipeline.
    """
    return (
        "# Note Enhancement Source\n\n"
        f"- session_id: `{context.session_id}`\n"
        f"- session_name: `{context.session_name}`\n"
        f"- source_mode: `{context.source_mode}`\n"
        f"- source_reference: `{context.source_reference or '(none)'}`\n\n"
        "## Enhancement Contract\n\n"
        "- Preserve core meaning and factual content.\n"
        "- Improve clarity, structure, and flow.\n"
        "- Avoid adding unsupported claims.\n\n"
        "## Raw Notes\n\n"
        "```text\n"
        f"{raw_text.rstrip()}\n"
        "```\n"
    )

