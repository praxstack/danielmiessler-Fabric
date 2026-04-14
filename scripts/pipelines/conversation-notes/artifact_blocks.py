#!/usr/bin/env python3
"""Deterministic parser for conversation-notes artifact blocks."""

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
    Parse artifact blocks embedded in the given text and return them keyed by their paths.
    
    Parameters:
        text (str): Input text that may contain one or more artifact blocks delimited by the module's BEGIN_PREFIX header lines and the END_MARKER footer lines.
    
    Returns:
        dict[str, ArtifactBlock]: Mapping from artifact path to its parsed ArtifactBlock (content always ends with a single trailing newline).
    
    Raises:
        ValueError: If an artifact block is not terminated with END_MARKER (unterminated block) or if the same artifact path appears more than once (duplicate block).
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

        if path in blocks:
            raise ValueError(f"duplicate artifact block: {path}")

        content = "\n".join(content_lines).rstrip("\n") + "\n"
        blocks[path] = ArtifactBlock(path=path, content=content)
        idx += 1

    return blocks


def require_blocks(text: str, required_paths: list[str]) -> dict[str, ArtifactBlock]:
    """
    Ensure the given text contains all specified artifact blocks and return the parsed blocks.
    
    Parameters:
        text (str): The text to scan for artifact blocks.
        required_paths (list[str]): Artifact paths that must be present in the text.
    
    Returns:
        dict[str, ArtifactBlock]: Mapping from artifact path to its parsed ArtifactBlock.
    
    Raises:
        ValueError: If any required artifact paths are missing; the exception message lists the missing paths.
    """
    blocks = parse_artifact_blocks(text)
    missing = [path for path in required_paths if path not in blocks]
    if missing:
        raise ValueError(f"missing artifact blocks: {', '.join(missing)}")
    return blocks
