#!/usr/bin/env python3
"""Deterministic parser for study-guide-technical artifact blocks."""

from __future__ import annotations

from dataclasses import dataclass


BEGIN_PREFIX = "<<<BEGIN_ARTIFACT:"
END_MARKER = "<<<END_ARTIFACT>>>"


@dataclass
class ArtifactBlock:
    path: str
    content: str


def parse_artifact_blocks(text: str) -> dict[str, ArtifactBlock]:
    """
    Parse artifact blocks from the given text and return a mapping from artifact path to ArtifactBlock.
    
    Scans the input for artifact blocks delimited by the module's BEGIN_PREFIX and END_MARKER markers, extracts each block's content (preserving original line formatting and ensuring exactly one trailing newline), and returns a dict keyed by the artifact path.
    
    Parameters:
        text (str): Input text that may contain zero or more artifact blocks.
    
    Returns:
        dict[str, ArtifactBlock]: Mapping of artifact path to the corresponding ArtifactBlock.
    
    Raises:
        ValueError: If a block start is found without a matching END_MARKER; the exception message includes the unterminated block's path.
    """
    lines = text.splitlines()
    idx = 0
    blocks: dict[str, ArtifactBlock] = {}

    while idx < len(lines):
        line = lines[idx].strip()
        if not line.startswith(BEGIN_PREFIX) or not line.endswith(">>>"):
            idx += 1
            continue

        path = line[len(BEGIN_PREFIX) : -3].strip()
        idx += 1
        content_lines: list[str] = []

        while idx < len(lines) and lines[idx].strip() != END_MARKER:
            content_lines.append(lines[idx])
            idx += 1

        if idx >= len(lines):
            raise ValueError(f"unterminated artifact block for {path}")

        content = "\n".join(content_lines).rstrip("\n") + "\n"
        blocks[path] = ArtifactBlock(path=path, content=content)
        idx += 1

    return blocks


def require_blocks(text: str, required_paths: list[str]) -> dict[str, ArtifactBlock]:
    """
    Ensure the specified artifact paths are present in the provided text and return all parsed artifact blocks.
    
    Parameters:
        text (str): Input text containing zero or more artifact blocks.
        required_paths (list[str]): Artifact paths that must be present in the parsed blocks.
    
    Returns:
        dict[str, ArtifactBlock]: Mapping from artifact path to its parsed ArtifactBlock for all blocks found.
    
    Raises:
        ValueError: If any required paths are missing; the exception message lists the missing paths.
    """
    blocks = parse_artifact_blocks(text)
    missing = [path for path in required_paths if path not in blocks]
    if missing:
        raise ValueError(f"missing artifact blocks: {', '.join(missing)}")
    return blocks
