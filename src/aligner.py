"""
Veritas-Graph: PDF-to-DOCX Text Alignment & Disambiguation Bridge.
"""
import re
import difflib
from typing import List, Optional, Tuple
from docx import Document


class DocumentAligner:
    """
    Bridges extracted PDF text (Phase 1) with Word paragraph indices (Phase 2).
    """

    @staticmethod
    def normalize_text(text: str) -> str:
        """Strips whitespace, hyphenations, and non-printable characters."""
        text = re.sub(r'[\r\n\t]+', ' ', text)
        text = re.sub(r'-\s+', '', text)  # Resolve soft line-break hyphens
        return re.sub(r'\s+', ' ', text).strip().lower()

    @classmethod
    def find_best_paragraph_match(
        cls, 
        doc: Document, 
        target_text: str, 
        context_before: str = "", 
        similarity_threshold: float = 0.85
    ) -> Tuple[Optional[int], float, bool]:
        """
        Locates matching paragraph index in a .docx file.
        
        Returns:
            Tuple[paragraph_index, confidence, is_ambiguous]
        """
        norm_target = cls.normalize_text(target_text)
        norm_context = cls.normalize_text(context_before)
        
        matches: List[Tuple[int, float]] = []

        for idx, p in enumerate(doc.paragraphs):
            norm_p = cls.normalize_text(p.text)
            if not norm_p:
                continue

            # Exact substring match
            if norm_target in norm_p:
                matches.append((idx, 1.0))
                continue

            # Fuzzy sequence matcher
            matcher = difflib.SequenceMatcher(None, norm_target, norm_p)
            ratio = matcher.ratio()
            if ratio >= similarity_threshold:
                matches.append((idx, ratio))

        if not matches:
            return None, 0.0, False

        # If multiple candidates found (boilerplate repetition), disambiguate via context
        if len(matches) > 1:
            best_idx = None
            best_score = -1.0
            for idx, base_score in matches:
                # Check preceding paragraph for context
                preceding_text = cls.normalize_text(doc.paragraphs[idx - 1].text) if idx > 0 else ""
                context_match = difflib.SequenceMatcher(None, norm_context, preceding_text).ratio()
                combined_score = (base_score * 0.6) + (context_match * 0.4)
                
                if combined_score > best_score:
                    best_score = combined_score
                    best_idx = idx

            # If top candidates are indistinguishable, flag as ambiguous
            is_ambiguous = best_score < 0.75
            return best_idx, best_score, is_ambiguous

        return matches[0][0], matches[0][1], False