#!/usr/bin/env python3
"""Build optional context artifacts for conversation-notes."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from common import discover_context_files, load_session_context, run_dir


MAX_CONTEXT_FILES = 8
MAX_CONTEXT_CHARS_PER_FILE = 4000
MAX_TOTAL_CONTEXT_CHARS = 20000
MAX_PDF_PAGES = 12


@dataclass
class ContextEntry:
    path: str
    kind: str
    status: str
    excerpt: str
    source_chars: int
    included_chars: int
    truncated: bool
    error: str = ""


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for the script.
    
    Returns:
        argparse.Namespace: Parsed arguments with a required `session_context` attribute (string) sourced from the `--session-context` command-line option.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-context", required=True)
    return parser.parse_args()


def append_error(existing: str, new_note: str) -> str:
    """
    Append a new error note to an existing error string, separating entries with "; ".
    
    If `existing` is empty, returns `new_note` unchanged.
    
    Parameters:
        existing (str): Existing error string which may be empty.
        new_note (str): New error note to append.
    
    Returns:
        str: Combined error string with `new_note` appended; equals `new_note` if `existing` was empty.
    """
    if not existing:
        return new_note
    return f"{existing}; {new_note}"


def read_text_excerpt(path: Path, limit: int) -> tuple[str, bool]:
    """
    Return the file's text up to a character limit.
    
    Parameters:
        path (Path): Path to the text file to read.
        limit (int): Maximum number of characters to include in the returned excerpt.
    
    Returns:
        tuple[str, bool]: A tuple of (excerpt, truncated) where `excerpt` is the file content truncated to at most `limit` characters, and `truncated` is `True` if the original file content exceeded `limit`, `False` otherwise.
    """
    with path.open("r", encoding="utf-8", errors="ignore") as file:
        content = file.read(limit + 1)
    if len(content) <= limit:
        return content, False
    return content[:limit], True


def extract_pdf_text(path: Path, per_file_limit: int) -> tuple[str, str, str, int, bool]:
    """
    Extract text from a PDF file and produce a bounded excerpt and extraction metadata.
    
    Parameters:
        path (Path): Filesystem path to the PDF file.
        per_file_limit (int): Maximum number of characters to include in the returned excerpt.
    
    Returns:
        tuple[str, str, str, int, bool]: A 5-tuple containing:
            - excerpt (str): The extracted text excerpt, empty if no extractable text.
            - status (str): `"extracted"` if text was extracted, `"metadata_only"` if extraction was not performed or yielded no text.
            - error (str): An explanatory message when extraction was incomplete or failed (e.g., pypdf missing, extraction error, or truncation note); empty on successful full extraction.
            - source_chars (int): Count of characters present in the source PDF pages considered (0 when unavailable); when positive, reflects the raw source character count even if excerpt was truncated.
            - truncated (bool): `True` if the excerpt was truncated to meet `per_file_limit`, `False` otherwise.
    """
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return "", "metadata_only", "pypdf not installed; only file metadata is available", 0, False

    try:
        reader = PdfReader(str(path))
        chunks: list[str] = []
        source_chars = 0
        truncated = False
        for page in reader.pages[:MAX_PDF_PAGES]:
            page_text = (page.extract_text() or "").strip()
            if not page_text:
                continue

            delimiter = "\n\n" if chunks else ""
            source_chars += len(delimiter) + len(page_text)
            if source_chars > per_file_limit:
                truncated = True

            remaining = per_file_limit - sum(len(chunk) for chunk in chunks)
            if remaining > 0:
                chunks.append((delimiter + page_text)[:remaining])
            if truncated:
                break

        text = "".join(chunks).strip()
        if not text:
            return "", "metadata_only", "PDF contained no extractable text", 0, False

        error = ""
        if truncated:
            error = f"excerpt truncated to {per_file_limit} chars"
        return text, "extracted", error, source_chars if source_chars > 0 else len(text), truncated
    except Exception as err:
        return "", "metadata_only", f"PDF extraction failed: {err}", 0, False


def extract_context_entry(path: Path) -> ContextEntry:
    """
    Create a ContextEntry describing the extracted or metadata-only content for the given file path.
    
    For Markdown (.md) and text (.txt) files, reads an excerpt up to the per-file character limit and marks the entry as "extracted" when non-empty or "metadata_only" when empty. For PDF files (.pdf), attempts PDF text extraction and returns the extractor's status and any extraction error. For other file types, returns an "ignored" entry indicating the type is unsupported.
    
    Parameters:
        path (Path): Path to the context file to inspect and extract.
    
    Returns:
        ContextEntry: A dataclass instance populated with:
            - path: string form of the provided path.
            - kind: one of "markdown", "text", "pdf", or the file suffix (without dot) for unsupported types.
            - status: extraction status ("extracted", "metadata_only", "ignored", or PDF extractor status).
            - excerpt: extracted text excerpt (may be empty).
            - source_chars: number of source characters observed (raw count when available).
            - included_chars: number of characters included in the excerpt.
            - truncated: True if the stored excerpt was truncated due to per-file limits and the excerpt is non-empty.
            - error: human-readable error note for empty files, unsupported types, or PDF extraction failures.
    """
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        text, truncated = read_text_excerpt(path, MAX_CONTEXT_CHARS_PER_FILE)
        excerpt = text.strip()
        status = "extracted" if excerpt else "metadata_only"
        source_chars = len(excerpt) + (1 if truncated else 0)
        error = ""
        if not excerpt:
            error = "file was empty"
        elif truncated:
            error = f"excerpt truncated to {MAX_CONTEXT_CHARS_PER_FILE} chars"
        return ContextEntry(
            path=str(path),
            kind="markdown" if suffix == ".md" else "text",
            status=status,
            excerpt=excerpt,
            source_chars=source_chars,
            included_chars=len(excerpt),
            truncated=truncated and bool(excerpt),
            error=error,
        )
    if suffix == ".pdf":
        text, status, error, source_chars, truncated = extract_pdf_text(path, MAX_CONTEXT_CHARS_PER_FILE)
        return ContextEntry(
            path=str(path),
            kind="pdf",
            status=status,
            excerpt=text,
            source_chars=source_chars,
            included_chars=len(text),
            truncated=truncated and bool(text),
            error=error,
        )
    return ContextEntry(
        path=str(path),
        kind=suffix.lstrip("."),
        status="ignored",
        excerpt="",
        source_chars=0,
        included_chars=0,
        truncated=False,
        error="unsupported type",
    )


def apply_total_char_limit(entries: list[ContextEntry], total_char_limit: int) -> int:
    """
    Enforces an overall character limit across the provided context entries, trimming or omitting excerpts so the total included characters do not exceed the limit.
    
    This function mutates the supplied entries in place: it updates each entry's excerpt and included_chars, sets truncated when an excerpt is shortened or removed, and adjusts status to "metadata_only" and appends an error note when an excerpt is omitted due to the total cap. Entries with empty excerpts are skipped.
    
    Parameters:
        entries (list[ContextEntry]): Context entries to process (mutated in place).
        total_char_limit (int): Maximum allowed sum of included characters across all entries.
    
    Returns:
        int: Total number of characters included across entries after enforcing the cap.
    """
    included_total = 0
    for entry in entries:
        entry.included_chars = len(entry.excerpt)
        if not entry.excerpt:
            continue

        remaining = total_char_limit - included_total
        if remaining <= 0:
            entry.excerpt = ""
            entry.included_chars = 0
            entry.truncated = True
            if entry.status == "extracted":
                entry.status = "metadata_only"
            entry.error = append_error(
                entry.error,
                f"excerpt omitted because total context cap ({total_char_limit} chars) was reached",
            )
            continue

        if len(entry.excerpt) > remaining:
            entry.excerpt = entry.excerpt[:remaining]
            entry.included_chars = len(entry.excerpt)
            entry.truncated = True
            entry.error = append_error(
                entry.error,
                f"excerpt truncated to fit total context cap ({total_char_limit} chars)",
            )

        included_total += entry.included_chars
    return included_total


def render_context_pack(entries: list[ContextEntry], warnings: list[str]) -> str:
    """
    Render a human-readable Markdown context pack summarizing optional context entries and warnings.
    
    Parameters:
        entries (list[ContextEntry]): Ordered list of context sources to include; each entry may contain metadata (path, kind, status, included_chars), an optional text excerpt, a truncated flag, and an optional error note.
        warnings (list[str]): List of warning messages to include near the top of the pack.
    
    Returns:
        str: A Markdown-formatted string containing a header, optional warnings section, and one "Context Source" section per entry with its metadata and excerpt (if present).
    """
    lines = [
        "# Optional Therapeutic Context",
        "",
        "This context is optional and must be treated as supporting reference only.",
        "",
    ]
    if warnings:
        lines.extend(["## Context Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")

    if not entries:
        lines.extend(["- No optional context files were discovered.", ""])
        return "\n".join(lines).rstrip() + "\n"

    for idx, entry in enumerate(entries, start=1):
        lines.extend(
            [
                f"## Context Source {idx}",
                f"- path: `{entry.path}`",
                f"- kind: `{entry.kind}`",
                f"- status: `{entry.status}`",
                f"- included_chars: `{entry.included_chars}`",
            ]
        )
        if entry.truncated:
            lines.append("- truncated: `true`")
        if entry.error:
            lines.append(f"- note: {entry.error}")
        lines.append("")
        if entry.excerpt:
            lines.extend(
                [
                    "```text",
                    entry.excerpt.rstrip(),
                    "```",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    """
    Orchestrates building optional context artifacts (a context pack and manifest) for a run.
    
    Discovers context files under the session context, extracts text excerpts (including PDF handling), enforces per-file and total-character limits, collects warnings about skipped or truncated files, and writes two artifacts—context_pack.md and context_manifest.json—to both the current run directory and the session's stable pipeline directory.
    """
    args = parse_args()
    session_context = load_session_context(Path(args.session_context))

    discovered_context_files = discover_context_files(
        Path(session_context.context_root),
        Path(session_context.input_path),
    )
    selected_context_files = discovered_context_files[:MAX_CONTEXT_FILES]
    skipped_by_file_cap = len(discovered_context_files) - len(selected_context_files)

    entries = [extract_context_entry(path) for path in selected_context_files]
    included_context_chars = apply_total_char_limit(entries, MAX_TOTAL_CONTEXT_CHARS)

    truncated_entries = sum(1 for entry in entries if entry.truncated)
    total_cap_events = sum(1 for entry in entries if "total context cap" in entry.error)

    warnings: list[str] = []
    if skipped_by_file_cap > 0:
        warnings.append(
            f"processed first {MAX_CONTEXT_FILES} context files in deterministic path order; "
            f"skipped {skipped_by_file_cap} additional files"
        )
    if total_cap_events > 0:
        warnings.append(
            f"total context excerpt size capped at {MAX_TOTAL_CONTEXT_CHARS} chars; "
            f"{total_cap_events} file(s) were truncated or omitted"
        )
    if truncated_entries > total_cap_events:
        warnings.append(
            f"{truncated_entries - total_cap_events} file(s) exceeded per-file limit "
            f"of {MAX_CONTEXT_CHARS_PER_FILE} chars"
        )

    context_pack = render_context_pack(entries, warnings)
    manifest_payload = {
        "limits": {
            "max_files": MAX_CONTEXT_FILES,
            "max_chars_per_file": MAX_CONTEXT_CHARS_PER_FILE,
            "max_total_chars": MAX_TOTAL_CONTEXT_CHARS,
        },
        "summary": {
            "discovered_files": len(discovered_context_files),
            "processed_files": len(selected_context_files),
            "skipped_by_file_cap": skipped_by_file_cap,
            "included_chars": included_context_chars,
            "truncated_entries": truncated_entries,
        },
        "warnings": warnings,
        "entries": [asdict(entry) for entry in entries],
    }
    manifest_json = json.dumps(manifest_payload, ensure_ascii=True, indent=2) + "\n"

    current_run_dir = run_dir()
    current_run_dir.mkdir(parents=True, exist_ok=True)
    stable_pipeline_dir = Path(session_context.stable_pipeline_dir)
    stable_pipeline_dir.mkdir(parents=True, exist_ok=True)

    run_context_pack_path = current_run_dir / "context_pack.md"
    run_context_manifest_path = current_run_dir / "context_manifest.json"
    stable_context_pack_path = stable_pipeline_dir / "context_pack.md"
    stable_context_manifest_path = stable_pipeline_dir / "context_manifest.json"

    run_context_pack_path.write_text(context_pack, encoding="utf-8")
    run_context_manifest_path.write_text(manifest_json, encoding="utf-8")
    stable_context_pack_path.write_text(context_pack, encoding="utf-8")
    stable_context_manifest_path.write_text(manifest_json, encoding="utf-8")


if __name__ == "__main__":
    main()
