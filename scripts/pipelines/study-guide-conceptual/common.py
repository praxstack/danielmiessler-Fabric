#!/usr/bin/env python3
"""Shared helpers for the Fabric-native study-guide-conceptual pipeline."""

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
    Convert a string into a lowercase slug suitable for filenames or identifiers.
    
    Parameters:
        value (str): Input string to convert.
    
    Returns:
        slug (str): Lowercase string with sequences of non-alphanumeric characters replaced by single hyphens and with leading/trailing hyphens removed; returns "session" if the resulting slug is empty.
    """
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "session"


def env_path(name: str) -> Path:
    """
    Resolve a required environment variable value into an absolute Path.
    
    Parameters:
    	name (str): Name of the environment variable to read.
    
    Returns:
    	path (Path): The environment variable's value expanded (tilde) and resolved to an absolute path.
    
    Raises:
    	RuntimeError: If the environment variable is not set or is empty.
    """
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return Path(value).expanduser().resolve()


def run_dir() -> Path:
    """
    Return the pipeline run directory path configured by FABRIC_PIPELINE_RUN_DIR.
    
    Returns:
        run_dir (Path): Expanded and resolved Path for the pipeline run directory.
    
    Raises:
        RuntimeError: If the FABRIC_PIPELINE_RUN_DIR environment variable is not set.
    """
    return env_path(FABRIC_RUN_DIR_ENV)


def invocation_dir() -> Path:
    """
    Get the pipeline invocation directory from the FABRIC_PIPELINE_INVOCATION_DIR environment variable.
    
    Returns:
        invocation_dir (Path): Resolved filesystem path specified by FABRIC_PIPELINE_INVOCATION_DIR.
    """
    return env_path(FABRIC_INVOCATION_DIR_ENV)


def source_mode() -> str:
    """
    Read the FABRIC_PIPELINE_SOURCE_MODE environment variable and return its trimmed value.
    
    Returns:
        str: The environment variable's value with leading and trailing whitespace removed; an empty string if the variable is not set.
    """
    return os.environ.get(FABRIC_SOURCE_MODE_ENV, "").strip()


def source_reference() -> str:
    """
    Retrieve the FABRIC_PIPELINE_SOURCE_REFERENCE environment variable value.
    
    Whitespace at both ends is removed before returning; if the variable is unset, an empty string is returned.
    
    Returns:
        str: The trimmed environment variable value, or an empty string if not set.
    """
    return os.environ.get(FABRIC_SOURCE_REFERENCE_ENV, "").strip()


def read_stdin() -> str:
    """
    Read the entire standard input and return it decoded as UTF-8.
    
    Returns:
        The full contents of stdin as a string.
    """
    return os.fdopen(0, "r", encoding="utf-8").read()


def resolve_input_path(path: Path) -> Path:
    """
    Resolve a filesystem path to a single input file suitable for the study-guide-conceptual pipeline.
    
    Parameters:
        path (Path): A file or directory path to resolve. If a file is provided, it must have a `.md` or `.txt` suffix.
    
    Returns:
        resolved (Path): The resolved path to an input file (a `.md` or `.txt` file).
    
    Raises:
        FileNotFoundError: If the provided path does not exist, if a provided file has an unsupported suffix, or if a directory cannot be resolved to a unique input file. The directory resolution prefers, in order: `transcript.md`, `transcript.txt`, `notes.md`, `notes.txt`, `meeting_saved_closed_caption.txt`; if none of those exist and the directory contains exactly one `.md` or `.txt` file, that file is returned.
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
        raise FileNotFoundError(f"Could not resolve unique study-guide-conceptual input in directory: {resolved}")

    raise FileNotFoundError(f"Input path not found: {resolved}")


def _ephemeral_session_identity(current_source_mode: str, current_source_reference: str) -> tuple[str, str]:
    """
    Produce an ephemeral session identifier and name derived from the provided source mode and reference.
    
    Parameters:
        current_source_mode (str): The input source mode (e.g., "scrape_url", "stdin", or other modes).
        current_source_reference (str): The source reference used when the mode is "scrape_url" (e.g., a URL).
    
    Returns:
        tuple[str, str]: A (session_id, session_name) pair. If mode is "scrape_url" and a reference is provided, both values are the slugified reference; if mode is "stdin", both are "stdin-session"; otherwise both are "<mode>-session" (or "session-session" when mode is empty).
    """
    if current_source_mode == "scrape_url" and current_source_reference:
        return slugify(current_source_reference), slugify(current_source_reference)
    if current_source_mode == "stdin":
        return "stdin-session", "stdin-session"
    return f"{current_source_mode or 'session'}-session", f"{current_source_mode or 'session'}-session"


def resolve_session_context(stdin_text: str) -> tuple[SessionContext, str]:
    """
    Builds a SessionContext for the current environment and returns it together with the resolved source text.
    
    Parameters:
        stdin_text (str): Content read from standard input; used when the source mode is "stdin" or "scrape_url".
    
    Returns:
        tuple(SessionContext, str): A tuple where the first element is a SessionContext populated with session metadata, resolved paths, and identifiers, and the second element is the raw source text chosen or written for the session.
    
    Raises:
        RuntimeError: If the detected source mode is not "source", "stdin", or "scrape_url".
    """
    current_invocation_dir = invocation_dir()
    current_source_mode = source_mode()
    current_source_reference = source_reference()

    if current_source_mode == "source" and current_source_reference:
        resolved_input = resolve_input_path(Path(current_source_reference))
        session_dir = resolved_input.parent
        stable_pipeline_dir = session_dir / ".pipeline"
        final_output_path = session_dir / "final_notes.md"
        session_name = session_dir.name
        session_id = slugify(session_name)
        raw_text = resolved_input.read_text(encoding="utf-8")
    elif current_source_mode in {"stdin", "scrape_url"}:
        session_dir = current_invocation_dir
        stable_pipeline_dir = run_dir()
        final_output_path = run_dir() / "final_notes.md"
        resolved_input = run_dir() / "source_input.md"
        raw_text = stdin_text
        resolved_input.parent.mkdir(parents=True, exist_ok=True)
        resolved_input.write_text(raw_text, encoding="utf-8")
        session_name, session_id = _ephemeral_session_identity(current_source_mode, current_source_reference)
    else:
        raise RuntimeError(
            "study-guide-conceptual supports source files/directories, stdin, or scrape_url input; "
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
    Persist a SessionContext to disk as an ASCII-safe, indented JSON file.
    
    The function ensures the target file's parent directory exists, serializes the given SessionContext to JSON using ASCII-safe encoding with two-space indentation, writes the content with a trailing newline, and encodes the file as UTF-8.
    
    Parameters:
        path (Path): Filesystem path where the JSON representation will be written. Parent directories will be created if missing.
        context (SessionContext): The session context to serialize and save.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(context), ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def load_session_context(path: Path) -> SessionContext:
    """
    Load a SessionContext from a JSON file.
    
    Parameters:
        path (Path): Path to the JSON file containing a serialized SessionContext.
    
    Returns:
        SessionContext: Instance reconstructed from the file's JSON content.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    return SessionContext(**data)


def semantic_map_input_text(context: SessionContext, raw_text: str) -> str:
    """
    Create a Markdown prompt that requests a semantic mapping of the provided source material.
    
    Parameters:
        context (SessionContext): Session metadata used to populate header fields (session_id, session_name, source_mode, source_reference).
        raw_text (str): The source material to embed in the prompt; it will be placed in a fenced `text` code block.
    
    Returns:
        str: A Markdown-formatted prompt containing session metadata, concise instructions for semantic mapping, and the source material.
    """
    return (
        "# Nontechnical Study Guide Source\n\n"
        f"- session_id: `{context.session_id}`\n"
        f"- session_name: `{context.session_name}`\n"
        f"- source_mode: `{context.source_mode}`\n"
        f"- source_reference: `{context.source_reference or '(none)'}`\n\n"
        "## Instructions for semantic mapping\n\n"
        "- Preserve fidelity to the source.\n"
        "- Focus on context, themes, arguments, and examples.\n"
        "- Keep language accessible and avoid technical assumptions.\n\n"
        "## Source Material\n\n"
        "```text\n"
        f"{raw_text.rstrip()}\n"
        "```\n"
    )


def render_input_text(context: SessionContext, semantic_map_json: dict, source_text: str) -> str:
    """
    Create a Markdown rendering brief that combines session metadata, a semantic map, and the source text.
    
    Parameters:
        context (SessionContext): Session metadata used for session_id, session_name, and source_mode fields.
        semantic_map_json (dict): Semantic mapping structured data to include as a JSON code block.
        source_text (str): Original source material to include as a plain-text code block.
    
    Returns:
        render_md (str): A Markdown-formatted brief containing session metadata, the semantic map as JSON, and the source reminder as a text code block.
    """
    return (
        "# Nontechnical Study Guide Rendering Brief\n\n"
        f"- session_id: `{context.session_id}`\n"
        f"- session_name: `{context.session_name}`\n"
        f"- source_mode: `{context.source_mode}`\n\n"
        "## Semantic Map\n\n"
        "```json\n"
        f"{json.dumps(semantic_map_json, ensure_ascii=True, indent=2)}\n"
        "```\n\n"
        "## Source Reminder\n\n"
        "```text\n"
        f"{source_text.rstrip()}\n"
        "```\n"
    )
