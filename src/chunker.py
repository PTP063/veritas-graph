"""
Veritas-Graph: Hierarchical Legal Chunker with Silent-Failure Detection.
"""

import re

from src.config import CHUNK_OVERLAP, MAX_CHUNK_LENGTH


class LegalChunker:
    """Splits legal documents along semantic headers.

    Falls back to a mechanical rolling window if chunks exceed limits or if unstructured.
    """

    # Hierarchical legal pattern matching
    HEADER_PATTERNS: list[str] = [
        # Articles & Sections
        r"(?=(?:ARTICLE|Article)\s+[IVXLCDM\d]+)",
        r"(?=(?:SECTION|Section|Sec\.)\s+\d+(?:\.\d+)*)",
        # Subsections: (a), (1), (i)
        r"(?=\n\s*\((?:[a-zA-Z]|\d+|[ivxldcm]+)\)\s+)",
        # Recitals & Transitions
        r"(?=\b(?:WHEREAS|Whereas|NOW, THEREFORE|Now, Therefore)\b)",
        # Schedules and Exhibits
        r"(?=(?:EXHIBIT|Exhibit|SCHEDULE|Schedule)\s+[A-Z\d]+)",
    ]

    COMPILED_PATTERN: re.Pattern[str] = re.compile("|".join(HEADER_PATTERNS))

    def __init__(
        self, max_chunk_chars: int = MAX_CHUNK_LENGTH, overlap_chars: int = CHUNK_OVERLAP
    ) -> None:
        """Initializes the LegalChunker.

        Args:
            max_chunk_chars: Maximum characters per chunk before falling back to rolling window.
            overlap_chars: Number of overlapping characters in mechanical splits.
        """
        self.max_chunk_chars = max_chunk_chars
        self.overlap_chars = overlap_chars

    def chunk(self, text: str) -> tuple[list[str], bool]:
        """Splits a document text into semantic or mechanical chunks.

        Args:
            text: The raw legal document string.

        Returns:
            A tuple containing a list of string chunks and a boolean indicating
            if the document was unstructured (zero semantic headers matched).
        """
        if not text or not text.strip():
            return [], True

        # Attempt semantic regex split
        raw_chunks: list[str] = [
            c.strip() for c in self.COMPILED_PATTERN.split(text) if c and c.strip()
        ]

        is_unstructured: bool = False
        # If no regex boundary fired, text was returned as a single block
        if len(raw_chunks) <= 1:
            is_unstructured = True

        final_chunks: list[str] = []
        for chunk_text in raw_chunks:
            if len(chunk_text) <= self.max_chunk_chars:
                final_chunks.append(chunk_text)
            else:
                # Mechanical rolling-window fallback
                sub_chunks = self._rolling_window_split(chunk_text)
                final_chunks.extend(sub_chunks)

        return final_chunks, is_unstructured

    def _rolling_window_split(self, text: str) -> list[str]:
        """Splits a single oversized chunk into a rolling window list.

        Args:
            text: The oversized string chunk.

        Returns:
            A list of strings split mechanically.
        """
        chunks: list[str] = []
        start: int = 0
        text_len: int = len(text)

        while start < text_len:
            end: int = min(start + self.max_chunk_chars, text_len)
            chunks.append(text[start:end])
            if end == text_len:
                break
            start += self.max_chunk_chars - self.overlap_chars

        return chunks
