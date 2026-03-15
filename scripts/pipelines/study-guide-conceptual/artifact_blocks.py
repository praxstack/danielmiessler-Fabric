#!/usr/bin/env python3
"""Deterministic parser for study-guide-conceptual artifact blocks."""

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
    Parse artifact blocks embedded in a text blob and return a mapping from block path to ArtifactBlock.
    
    Parameters:
        text (str): Input text that may contain zero or more artifact blocks delimited by the module's BEGIN_PREFIX headers and END_MARKER footers.
    
    Returns:
        dict[str, ArtifactBlock]: A dictionary mapping each discovered artifact path to its ArtifactBlock (content always ends with a single trailing newline).
    
    Raises:
        ValueError: If a block is not terminated before the end of input or if two blocks share the same path.
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
    Ensure the specified artifact block paths exist in the provided text and return all parsed blocks.
    
    Parameters:
        text (str): Input text that may contain one or more artifact blocks.
        required_paths (list[str]): Paths identifying artifact blocks that must be present in the text.
    
    Returns:
        dict[str, ArtifactBlock]: Mapping from artifact path to its parsed ArtifactBlock for all blocks found.
    
    Raises:
        ValueError: If any paths from `required_paths` are missing; the exception message lists the missing paths separated by commas.
    """
    blocks = parse_artifact_blocks(text)
    missing = [path for path in required_paths if path not in blocks]
    if missing:
        raise ValueError(f"missing artifact blocks: {', '.join(missing)}")
    return blocks
