"""
Veritas-Graph: End-to-End Orchestration Pipeline.
"""
import uuid
from typing import Optional
from docx import Document
from src.state import SystemState, RedlineAction
from src.graph import VeritasGraphOrchestrator
from src.aligner import DocumentAligner
from src.redliner import OOXMLRedliner

class VeritasPipeline:
    def __init__(self, orchestrator: VeritasGraphOrchestrator):
        self.orchestrator = orchestrator

    async def process_contract(
        self, 
        document_text: str, 
        docx_path: Optional[str] = None
    ) -> SystemState:
        """
        Executes end-to-end extraction, verification DAG, and native OOXML redlining.
        """
        # Dynamic ID Generation
        doc_id = str(uuid.uuid4())

        initial_state = SystemState(
            document_id=doc_id,
            raw_docx_path=docx_path,
            is_pdf_only=(docx_path is None),
            chunks=[document_text]
        )

        # 1. Execute Graph (The Brain)
        final_state = await self.orchestrator.run_dag(initial_state)

        # 2. PDF-Only Fallback
        if final_state.is_pdf_only:
            return final_state

        # 3. Align and Redline DOCX (The Hands)
        doc = Document(docx_path)
        
        # Initialize local mutable structures for strict DAG immutability
        redlines = []
        current_failed_chunks = list(final_state.failed_chunks) 
        requires_global_review = final_state.requires_global_human_review

        # Iterate through the extracted clauses and bridge the PDF->DOCX gap
        for clause in final_state.extracted_clauses:
            p_idx, score, is_ambiguous = DocumentAligner.find_best_paragraph_match(
                doc, clause.text, context_before=clause.context_before
            )
            
            if p_idx is not None and not is_ambiguous:
                # Plumb the actual LLM output instead of hardcoded strings
                replacement = clause.redline_suggestion or "[REVIEWER OMITTED REPLACEMENT]"
                
                if clause.requires_human_review:
                    OOXMLRedliner.inject_warning_comment(doc, p_idx, f"Veritas-AI: {clause.escalation_reason}")
                else:
                    # Unpack the new boolean and string tuple
                    success, err_msg = OOXMLRedliner.apply_tracked_change(doc, p_idx, clause.text, replacement)
                    if not success:
                        current_failed_chunks.append({"clause_id": clause.clause_id, "error": f"AST Injection failed: {err_msg}"})
                    else:
                        redlines.append(RedlineAction(
                            clause_id=clause.clause_id,
                            target_paragraph_index=p_idx,
                            original_text=clause.text,
                            replacement_text=replacement
                        ))
            else:
                if p_idx is not None:
                    OOXMLRedliner.inject_warning_comment(doc, p_idx, "Veritas-AI: Ambiguous clause match detected.")
                else:
                    # Eliminate the silent drop
                    current_failed_chunks.append({
                        "clause_id": clause.clause_id,
                        "error": "Alignment Failed: Could not locate PDF text in DOCX AST."
                    })
                    requires_global_review = True

        # Apply all state changes via a single immutable model_copy
        final_state = final_state.model_copy(update={
            "failed_chunks": current_failed_chunks,
            "requires_global_human_review": requires_global_review,
            "redlines": redlines
        })

        # 4. Final Validation Roundtrip
        if not OOXMLRedliner.validate_document(doc):
            raise RuntimeError("Generated OOXML failed schema validation.")

        # Dynamic Output Path & Document-Level Audit Stamp
        output_filename = f"redlined_{doc_id}.docx"
        
        if current_failed_chunks:
            p = doc.paragraphs[0]
            p.insert_paragraph_before(f"⚠️ VERITAS-AI AUDIT: {len(current_failed_chunks)} clauses failed injection and require manual review.")
            
        doc.save(output_filename)
        
        return final_state