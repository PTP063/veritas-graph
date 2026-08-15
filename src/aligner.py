"""
Veritas-Graph: PDF-to-DOCX Text Alignment & Disambiguation Bridge.
"""

import difflib
import re

from docx.document import Document as DocumentType


class DocumentAligner:
    """Bridges extracted PDF text (Phase 1) with Word paragraph indices (Phase 2)."""

    @staticmethod
    def normalize_text(text: str) -> str:
        """Strips whitespace, hyphenations, and non-printable characters.

        Args:
            text: The raw string text.

        Returns:
            The normalized string.
        """
        text = re.sub(r"[\r\n\t]+", " ", text)
        text = re.sub(r"-\s+", "", text)  # Resolve soft line-break hyphens
        return re.sub(r"\s+", " ", text).strip().lower()

    @classmethod
    def find_best_paragraph_match(
        cls,
        doc: DocumentType,
        target_text: str,
        context_before: str = "",
        similarity_threshold: float = 0.85,
    ) -> tuple[int | None, float, bool]:
        """Locates matching paragraph index in a .docx file.

        Args:
            doc: The python-docx Document object.
            target_text: The string we are looking for.
            context_before: The preceding string text for disambiguation.
            similarity_threshold: Minimum match ratio required (0.0 to 1.0).

        Returns:
            A tuple of (paragraph_index, confidence_score, is_ambiguous).
        """
        norm_target: str = cls.normalize_text(target_text)
        norm_context: str = cls.normalize_text(context_before)

        matches: list[tuple[int, float]] = []

        for idx, p in enumerate(doc.paragraphs):
            norm_p: str = cls.normalize_text(p.text)
            if not norm_p:
                continue

            # Exact substring match
            if norm_target in norm_p:
                matches.append((idx, 1.0))
                continue

            # Fuzzy sequence matcher
            matcher = difflib.SequenceMatcher(None, norm_target, norm_p)
            ratio: float = matcher.ratio()
            if ratio >= similarity_threshold:
                matches.append((idx, ratio))

        if not matches:
            return None, 0.0, False

        # If multiple candidates found (boilerplate repetition), disambiguate via context
        if len(matches) > 1:
            best_idx: int | None = None
            best_score: float = -1.0
            for idx, base_score in matches:
                # Check preceding paragraph for context
                preceding_text: str = (
                    cls.normalize_text(doc.paragraphs[idx - 1].text) if idx > 0 else ""
                )
                context_match: float = difflib.SequenceMatcher(
                    None, norm_context, preceding_text
                ).ratio()
                combined_score: float = (base_score * 0.6) + (context_match * 0.4)

                if combined_score > best_score:
                    best_score = combined_score
                    best_idx = idx

            # If top candidates are indistinguishable, flag as ambiguous
            is_ambiguous: bool = best_score < 0.75
            return best_idx, best_score, is_ambiguous

        return matches[0][0], matches[0][1], False
