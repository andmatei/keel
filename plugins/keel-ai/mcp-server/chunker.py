"""Type-specific document chunking for vector search indexing.

Splits design documents into chunks suitable for embedding. Each chunk is
a dict with: content, section_heading, parent_heading, chunk_index.
"""

from __future__ import annotations

import hashlib
import re

import tomllib


# Approximate token count: ~4 chars per token for English text.
_CHARS_PER_TOKEN = 4
_MAX_CHUNK_TOKENS = 800
_MAX_CHUNK_CHARS = _MAX_CHUNK_TOKENS * _CHARS_PER_TOKEN
_OVERLAP_SENTENCES = 2


def _estimate_tokens(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            return text[end + 3:].lstrip("\n")
    return text


def _extract_overlap(text: str, max_sentences: int = _OVERLAP_SENTENCES) -> str:
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    overlap = sentences[:max_sentences]
    return " ".join(overlap) if overlap else ""


def _split_long_text(text: str, max_chars: int = _MAX_CHUNK_CHARS) -> list[str]:
    chunks: list[str] = []
    for i in range(0, len(text), max_chars):
        chunks.append(text[i:i + max_chars])
    return chunks


def _split_paragraphs(text: str, max_chars: int = _MAX_CHUNK_CHARS) -> list[str]:
    paragraphs = re.split(r'\n\n+', text.strip())
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for para in paragraphs:
        if len(para) > max_chars:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0
            chunks.extend(_split_long_text(para, max_chars))
            continue
        if current_len + len(para) > max_chars and current:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0
        current.append(para)
        current_len += len(para) + 2
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def chunk_markdown(text: str) -> list[dict]:
    text = _strip_frontmatter(text)
    if not text.strip():
        return []

    # Split into sections by ## headings
    h2_pattern = re.compile(r'^(## .+)$', re.MULTILINE)
    parts = h2_pattern.split(text)

    # parts alternates: [preamble, heading1, body1, heading2, body2, ...]
    sections: list[tuple[str | None, str]] = []

    # Handle preamble (text before first ##)
    if parts[0].strip():
        sections.append((None, parts[0].strip()))

    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        sections.append((heading, body))

    chunks: list[dict] = []
    chunk_index = 0

    for sec_idx, (heading, body) in enumerate(sections):
        if not body:
            continue

        # Add trailing overlap from next section
        overlap = ""
        if sec_idx + 1 < len(sections):
            next_body = sections[sec_idx + 1][1]
            if next_body:
                overlap = _extract_overlap(next_body)

        content_with_overlap = body
        if overlap:
            content_with_overlap = body + "\n\n" + overlap

        if _estimate_tokens(body) <= _MAX_CHUNK_TOKENS:
            chunks.append({
                "section_heading": heading,
                "parent_heading": None,
                "content": content_with_overlap,
                "chunk_index": chunk_index,
            })
            chunk_index += 1
        else:
            # Try sub-splitting on ### headings
            sub_chunks = _subsplit_h3(heading, body, overlap)
            if sub_chunks:
                for sc in sub_chunks:
                    sc["chunk_index"] = chunk_index
                    chunk_index += 1
                chunks.extend(sub_chunks)
            else:
                # Fall back to paragraph splitting
                for part in _split_paragraphs(content_with_overlap):
                    chunks.append({
                        "section_heading": heading,
                        "parent_heading": None,
                        "content": part,
                        "chunk_index": chunk_index,
                    })
                    chunk_index += 1

    return chunks


def _subsplit_h3(parent_heading: str | None, body: str, overlap: str) -> list[dict] | None:
    h3_pattern = re.compile(r'^(### .+)$', re.MULTILINE)
    parts = h3_pattern.split(body)
    if len(parts) < 3:
        return None

    sub_chunks: list[dict] = []
    # Preamble before first ###
    if parts[0].strip():
        sub_chunks.append({
            "section_heading": parent_heading,
            "parent_heading": parent_heading,
            "content": parts[0].strip(),
        })

    for i in range(1, len(parts), 2):
        h3_heading = parts[i].strip()
        h3_body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if not h3_body:
            continue
        content = f"{h3_heading}\n\n{h3_body}"
        is_last = i + 2 >= len(parts)
        if is_last and overlap:
            content = content + "\n\n" + overlap
        if _estimate_tokens(content) > _MAX_CHUNK_TOKENS:
            for part in _split_paragraphs(content):
                sub_chunks.append({
                    "section_heading": h3_heading,
                    "parent_heading": parent_heading,
                    "content": part,
                })
        else:
            sub_chunks.append({
                "section_heading": h3_heading,
                "parent_heading": parent_heading,
                "content": content,
            })

    return sub_chunks if sub_chunks else None


def chunk_decision(content: str, *, file_path: str) -> list[dict]:
    text = _strip_frontmatter(content)
    if not text.strip():
        return []
    return [{
        "section_heading": None,
        "parent_heading": None,
        "content": text.strip(),
        "chunk_index": 0,
    }]


def chunk_milestones_toml(content: str) -> list[dict]:
    if not content.strip():
        return []
    try:
        data = tomllib.loads(content)
    except Exception:
        return []

    milestones = data.get("milestones", [])
    tasks = data.get("tasks", [])
    if not milestones:
        return []

    chunks: list[dict] = []
    for idx, ms in enumerate(milestones):
        ms_id = ms.get("id", "?")
        ms_tasks = [t for t in tasks if t.get("milestone") == ms_id]
        done_count = sum(1 for t in ms_tasks if t.get("status") == "done")
        total = len(ms_tasks)

        parts = [
            f"Milestone: {ms.get('title', ms_id)}",
            f"Status: {ms.get('status', 'unknown')}",
        ]
        if total > 0:
            parts.append(f"Tasks: {done_count}/{total} done")
        if ms.get("description"):
            parts.append(f"Description: {ms['description']}")

        chunks.append({
            "section_heading": None,
            "parent_heading": None,
            "content": " | ".join(parts),
            "chunk_index": idx,
        })

    return chunks


def chunk_document(content: str, *, file_path: str, doc_type: str) -> list[dict]:
    if not content.strip():
        return []

    if doc_type == "decision":
        return chunk_decision(content, file_path=file_path)
    if doc_type == "milestones" or file_path.endswith(".toml"):
        return chunk_milestones_toml(content)
    return chunk_markdown(content)


def content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()[:12]


def prepend_metadata(text: str, *, project: str, doc_type: str) -> str:
    return f"[project: {project}] [type: {doc_type}] {text}"
