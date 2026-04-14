#!/usr/bin/env python3
"""Deterministic parser for enhance-notes artifact blocks."""

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
    Parse artifact blocks from the given text and return a mapping from each artifact path to its ArtifactBlock.
    
    The parser recognizes blocks that start with the BEGIN_PREFIX header line (which must end with ">>>") and end with the END_MARKER line. The header's path portion (between BEGIN_PREFIX and trailing ">>>") is used as the dictionary key; the block's content is returned with a single trailing newline.
    
    Parameters:
        text (str): Input text potentially containing zero or more artifact blocks.
    
    Returns:
        dict[str, ArtifactBlock]: Mapping of artifact paths to their corresponding ArtifactBlock instances.
    
    Raises:
        ValueError: If an artifact block is not terminated by END_MARKER or if duplicate artifact paths are encountered.
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
    Ensure that all required artifact paths are present in the artifact blocks parsed from the given text.
    
    Parameters:
    	text (str): Input text containing zero or more artifact blocks.
    	required_paths (list[str]): List of artifact paths that must be present.
    
    Returns:
    	blocks (dict[str, ArtifactBlock]): Mapping from artifact path to its ArtifactBlock.
    
    Raises:
    	ValueError: If any required paths are missing; message lists the missing paths.
    """
    blocks = parse_artifact_blocks(text)
    missing = [path for path in required_paths if path not in blocks]
    if missing:
        raise ValueError(f"missing artifact blocks: {', '.join(missing)}")
    return blocks
