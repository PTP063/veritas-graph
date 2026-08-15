"""
Veritas-Graph: Hierarchical Legal Chunker with Silent-Failure Detection.
"""
import re
from typing import List, Tuple


class LegalChunker:
    """
    Splits legal documents along semantic headers.
    Falls back to a mechanical rolling window if chunks exceed limits or if unstructured.
    """
    
    # Hierarchical legal pattern matching
    HEADER_PATTERNS = [
        # Articles & Sections
        r'(?=(?:ARTICLE|Article)\s+[IVXLCDM\d]+)',
        r'(?=(?:SECTION|Section|Sec\.)\s+\d+(?:\.\d+)*)',
        # Subsections: (a), (1), (i)
        r'(?=\n\s*\((?:[a-zA-Z]|\d+|[ivxldcm]+)\)\s+)',
        # Recitals & Transitions
        r'(?=\b(?:WHEREAS|Whereas|NOW, THEREFORE|Now, Therefore)\b)',
        # Schedules and Exhibits
        r'(?=(?:EXHIBIT|Exhibit|SCHEDULE|Schedule)\s+[A-Z\d]+)'
    ]
    
    COMPILED_PATTERN = re.compile('|'.join(HEADER_PATTERNS))

    def __init__(self, max_chunk_chars: int = 8000, overlap_chars: int = 200):
        self.max_chunk_chars = max_chunk_chars
        self.overlap_chars = overlap_chars

    def chunk(self, text: str) -> Tuple[List[str], bool]:
        """
        Returns:
            Tuple[List[str], bool]: (chunks, is_unstructured)
            is_unstructured is True if zero semantic headers were matched.
        """
        if not text or not text.strip():
            return [], True

        # Attempt semantic regex split
        raw_chunks = [c.strip() for c in self.COMPILED_PATTERN.split(text) if c and c.strip()]
        
        is_unstructured = False
        # If no regex boundary fired, text was returned as a single block
        if len(raw_chunks) <= 1:
            is_unstructured = True

        final_chunks: List[str] = []
        for chunk in raw_chunks:
            if len(chunk) <= self.max_chunk_chars:
                final_chunks.append(chunk)
            else:
                # Mechanical rolling-window fallback
                sub_chunks = self._rolling_window_split(chunk)
                final_chunks.extend(sub_chunks)

        return final_chunks, is_unstructured

    def _rolling_window_split(self, text: str) -> List[str]:
        chunks = []
        start = 0
        text_len = len(text)
        
        while start < text_len:
            end = min(start + self.max_chunk_chars, text_len)
            chunks.append(text[start:end])
            if end == text_len:
                break
            start += (self.max_chunk_chars - self.overlap_chars)
            
        return chunks