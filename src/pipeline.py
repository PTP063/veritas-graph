"""
Veritas-Graph: End-to-End Orchestration Pipeline.
"""

import logging
import uuid
from typing import Any

from docx import Document
from docx.document import Document as DocumentType

from src.aligner import DocumentAligner
from src.exceptions import OOXMLInjectionError
from src.graph import VeritasGraphOrchestrator
from src.redliner import OOXMLRedliner
from src.state import RedlineAction, SystemState

logger = logging.getLogger(__name__)


class VeritasPipeline:
    """Coordinates the execution of extraction, verification, and redlining."""

    def __init__(self, orchestrator: VeritasGraphOrchestrator) -> None:
        """Initializes the pipeline with a graph orchestrator.

        Args:
            orchestrator: The DAG execution engine for the LLM passes.
        """
        self.orchestrator = orchestrator

    async def process_contract(
        self, document_text: str, docx_path: str | None = None
    ) -> SystemState:
        """Executes end-to-end extraction, verification DAG, and native OOXML redlining.

        Args:
            document_text: The raw text of the document to process.
            docx_path: Optional path to the source DOCX for AST injection.

        Returns:
            The final SystemState after processing and (optional) redlining.

        Raises:
            RuntimeError: If the final OOXML fails schema validation.
        """
        # Dynamic ID Generation
        doc_id: str = str(uuid.uuid4())
        logger.info(f"Starting pipeline for document {doc_id}")

        initial_state = SystemState(
            document_id=doc_id,
            raw_docx_path=docx_path,
            is_pdf_only=(docx_path is None),
            chunks=[document_text],
        )

        # 1. Execute Graph (The Brain)
        logger.info("Executing async graph orchestrator...")
        final_state: SystemState = await self.orchestrator.run_dag(initial_state)

        # 2. PDF-Only Fallback
        if final_state.is_pdf_only or not docx_path:
            logger.info("PDF-only mode or no DOCX provided. Returning state early.")
            return final_state

        # 3. Align and Redline DOCX (The Hands)
        logger.info("Aligning text to DOCX AST...")
        doc: DocumentType = Document(docx_path)

        # Initialize local mutable structures for strict DAG immutability
        redlines: list[RedlineAction] = []
        current_failed_chunks: list[dict[str, Any]] = list(final_state.failed_chunks)
        requires_global_review: bool = final_state.requires_global_human_review

        # Iterate through the extracted clauses and bridge the PDF->DOCX gap
        for clause in final_state.extracted_clauses:
            p_idx, score, is_ambiguous = DocumentAligner.find_best_paragraph_match(
                doc, clause.text, context_before=clause.context_before
            )

            if p_idx is not None and not is_ambiguous:
                # Plumb the actual LLM output instead of hardcoded strings
                replacement: str = clause.redline_suggestion or "[REVIEWER OMITTED REPLACEMENT]"

                if clause.requires_human_review:
                    logger.warning(
                        f"Clause {clause.clause_id} requires human review. Injecting warning."
                    )
                    OOXMLRedliner.inject_warning_comment(
                        doc, p_idx, f"Veritas-AI: {clause.escalation_reason}"
                    )
                else:
                    try:
                        OOXMLRedliner.apply_tracked_change(doc, p_idx, clause.text, replacement)
                        redlines.append(
                            RedlineAction(
                                clause_id=clause.clause_id,
                                target_paragraph_index=p_idx,
                                original_text=clause.text,
                                replacement_text=replacement,
                            )
                        )
                        logger.info(f"Successfully injected redline for {clause.clause_id}")
                    except OOXMLInjectionError as e:
                        logger.error(f"AST Injection failed for {clause.clause_id}: {e}")
                        current_failed_chunks.append(
                            {"clause_id": clause.clause_id, "error": f"AST Injection failed: {e}"}
                        )
            else:
                if p_idx is not None:
                    logger.warning(f"Ambiguous match for {clause.clause_id}. Injecting warning.")
                    OOXMLRedliner.inject_warning_comment(
                        doc, p_idx, "Veritas-AI: Ambiguous clause match detected."
                    )
                else:
                    logger.error(f"Alignment failed for {clause.clause_id}.")
                    current_failed_chunks.append(
                        {
                            "clause_id": clause.clause_id,
                            "error": "Alignment Failed: Could not locate PDF text in DOCX AST.",
                        }
                    )
                    requires_global_review = True

        # Apply all state changes via a single immutable model_copy
        final_state = final_state.model_copy(
            update={
                "failed_chunks": current_failed_chunks,
                "requires_global_human_review": requires_global_review,
                "redlines": redlines,
            }
        )

        # 4. Final Validation Roundtrip
        logger.info("Validating generated OOXML schema...")
        if not OOXMLRedliner.validate_document(doc):
            raise RuntimeError("Generated OOXML failed schema validation.")

        # Dynamic Output Path & Document-Level Audit Stamp
        output_filename = f"redlined_{doc_id}.docx"

        if current_failed_chunks:
            p = doc.paragraphs[0]
            p.insert_paragraph_before(
                f"⚠️ VERITAS-AI AUDIT: {len(current_failed_chunks)} clauses failed injection and require manual review."
            )

        doc.save(output_filename)
        logger.info(f"Saved track-changed document to {output_filename}")

        return final_state
