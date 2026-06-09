import re
from typing import List

from app.config import settings


def split_text_fixed(
    text: str,
    chunk_size: int = None,
    chunk_overlap: int = None,
) -> List[str]:
    chunk_size = chunk_size if chunk_size is not None else settings.DEFAULT_CHUNK_SIZE
    chunk_overlap = chunk_overlap if chunk_overlap is not None else settings.DEFAULT_CHUNK_OVERLAP

    # Guard: overlap must be strictly less than size to guarantee forward progress
    if chunk_overlap >= chunk_size:
        chunk_overlap = chunk_size - 1

    if not text or not text.strip():
        return []

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + chunk_size
        chunk = text[start:end]

        if chunk.strip():
            chunks.append(chunk.strip())

        if end >= text_len:
            break

        start = end - chunk_overlap

    return chunks


def split_text_by_paragraph(text: str, max_chunk_size: int = None, chunk_overlap: int = None) -> List[str]:
    max_chunk_size = max_chunk_size if max_chunk_size is not None else settings.DEFAULT_CHUNK_SIZE
    chunk_overlap = chunk_overlap if chunk_overlap is not None else settings.DEFAULT_CHUNK_OVERLAP
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks = []
    current_chunk = ""
    prev_tail_paras: List[str] = []  # paragraphs from end of previous chunk for overlap

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 > max_chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            # Build overlap from trailing paragraphs of current chunk
            prev_tail_paras = []
            overlap_len = 0
            for prev_para in reversed(current_chunk.split("\n\n")):
                prev_para = prev_para.strip()
                if not prev_para:
                    continue
                if overlap_len + len(prev_para) + 2 > chunk_overlap:
                    break
                prev_tail_paras.insert(0, prev_para)
                overlap_len += len(prev_para) + 2
            current_chunk = "\n\n".join(prev_tail_paras + [para]) if prev_tail_paras else para
        else:
            current_chunk = current_chunk + "\n\n" + para if current_chunk else para

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def split_text_recursive(text: str, chunk_size: int = None, chunk_overlap: int = None) -> List[str]:
    """Split by heading > paragraph > sentence > character hierarchy."""
    chunk_size = chunk_size if chunk_size is not None else settings.DEFAULT_CHUNK_SIZE
    chunk_overlap = chunk_overlap if chunk_overlap is not None else settings.DEFAULT_CHUNK_OVERLAP
    if chunk_overlap >= chunk_size:
        chunk_overlap = chunk_size - 1
    if not text or not text.strip():
        return []

    separators = ["\n\n\n", "\n\n", "\n", "。", ".", "！", "!", "？", "?", "；", ";", " "]
    chunks = _recursive_split(text, separators, chunk_size, chunk_overlap)

    # Apply overlap exactly once at the top level
    if chunk_overlap > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tail = chunks[i - 1][-chunk_overlap:]
            overlapped.append(prev_tail + chunks[i])
        chunks = overlapped

    return chunks


def _recursive_split(text: str, separators: List[str], chunk_size: int, chunk_overlap: int, _depth: int = 0) -> List[str]:
    chunks = []
    if len(text) <= chunk_size:
        if text.strip():
            chunks.append(text.strip())
        return chunks

    # Safety: fall back to fixed split if recursion is too deep
    if _depth >= 15:
        return split_text_fixed(text, chunk_size, 0)

    sep = separators[0] if separators else ""
    remaining_seps = separators[1:] if len(separators) > 1 else [""]

    if sep:
        parts = text.split(sep)
    else:
        return split_text_fixed(text, chunk_size, 0)

    current = ""
    for part in parts:
        candidate = current + sep + part if current else part
        if len(candidate) > chunk_size and current:
            if len(current) > chunk_size and remaining_seps:
                chunks.extend(_recursive_split(current, remaining_seps, chunk_size, chunk_overlap, _depth + 1))
            elif current.strip():
                chunks.append(current.strip())
            current = part
        else:
            current = candidate

    if current:
        if len(current) > chunk_size and remaining_seps:
            chunks.extend(_recursive_split(current, remaining_seps, chunk_size, chunk_overlap, _depth + 1))
        elif current.strip():
            chunks.append(current.strip())

    return chunks


def split_text_by_heading(text: str, chunk_size: int = None, chunk_overlap: int = None) -> List[str]:
    """Split by markdown headings, keeping each section as a chunk."""
    chunk_size = chunk_size if chunk_size is not None else settings.DEFAULT_CHUNK_SIZE * 2
    chunk_overlap = chunk_overlap if chunk_overlap is not None else settings.DEFAULT_CHUNK_OVERLAP
    if not text or not text.strip():
        return []

    heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
    sections = []
    last_end = 0

    for match in heading_pattern.finditer(text):
        if match.start() > last_end:
            pre_text = text[last_end:match.start()].strip()
            if pre_text:
                sections.append(pre_text)
        last_end = match.start()

    if last_end < len(text):
        remaining = text[last_end:].strip()
        if remaining:
            sections.append(remaining)

    if not sections:
        sections = [text]

    chunks = []
    for section in sections:
        if len(section) <= chunk_size:
            if section.strip():
                chunks.append(section.strip())
        else:
            sub_chunks = split_text_fixed(section, chunk_size, chunk_overlap)
            chunks.extend(sub_chunks)

    return chunks


STRATEGY_MAP = {
    "fixed": split_text_fixed,
    "paragraph": split_text_by_paragraph,
    "recursive": split_text_recursive,
    "heading": split_text_by_heading,
}


def split_text(text: str, strategy: str = "fixed", chunk_size: int = None, chunk_overlap: int = None) -> List[str]:
    """Unified entry point for text splitting."""
    func = STRATEGY_MAP.get(strategy, split_text_fixed)
    return func(text, chunk_size, chunk_overlap)
