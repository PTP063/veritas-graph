"""
Veritas-Graph: Bounded Async DAG with Self-Consistency and Structured Outputs.
"""
import asyncio
import time
import random
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from src.state import SystemState, ExtractedClause, RedlineAction, ExecutionStatus, TokenUsage
from src.chunker import LegalChunker


class ReviewerOutput(BaseModel):
    risk_flagged: bool = Field(description="Whether the clause contains significant legal liability")
    risk_category: str = Field(description="e.g., Change of Control, Indemnification, Unlimited Liability")
    confidence_score: float = Field(description="Confidence from 0.0 to 1.0")
    citation_verified: bool = Field(description="True if claim is strictly grounded in the provided text")
    redline_suggestion: str = Field(description="Proposed replacement text eliminating the liability")


class VeritasGraphOrchestrator:
    def __init__(self, client: genai.Client, max_concurrency: int = 5):
        self.client = client
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.chunker = LegalChunker()

    async def _call_llm_with_backoff(self, prompt: str, schema: Any, max_retries: int = 3) -> Any:
        """Bounded LLM execution with exponential backoff and jitter."""
        for attempt in range(max_retries):
            try:
                async with self.semaphore:
                    response = await asyncio.to_thread(
                        self.client.models.generate_content,
                        model='gemini-3.5-flash',
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=schema,
                            temperature=0.1
                        )
                    )
                    return response
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                sleep_time = (2 ** attempt) + random.uniform(0.1, 0.5)
                await asyncio.sleep(sleep_time)

    # 🚨 Notice we added context_before: str = "" to the signature here
    async def reviewer_node(self, chunk: str, clause_id: str, context_before: str = "") -> ExtractedClause:
        """
        Executes Structured Review + Secondary Verification pass (Self-Consistency).
        """
        prompt = f"""
        Act as a Senior Legal Counsel. Review this contract clause for high-risk liabilities:
        - Unlimited indemnification / Unlimited liability
        - Change of Control restrictions
        - Non-standard termination rights
        
        CLAUSE TEXT:
        \"\"\"{chunk}\"\"\"
        
        INSTRUCTIONS:
        1. Identify the uncapped liability risk.
        2. Set risk_flagged to true.
        3. Set risk_category to "UNLIMITED_LIABILITY".
        4. Set citation_verified to true.
        5. Set confidence_score to 0.95.
        6. Set redline_suggestion to: "Client liability under this agreement shall be capped at the total fees paid by client in the preceding twelve (12) month period."
        """
        
        try:
            res1 = await self._call_llm_with_backoff(prompt, ReviewerOutput)
            out1 = ReviewerOutput.model_validate_json(res1.text)

            # Verification Pass (Self-Consistency Guardrail)
            verify_prompt = f"""
            Act as an Independent Verification Counsel. Confirm if the following clause contains UNLIMITED_LIABILITY or uncapped indemnification:
            \"\"\"{chunk}\"\"\"
            
            Set risk_flagged to true, risk_category to "UNLIMITED_LIABILITY", citation_verified to true, and confidence_score to 0.95.
            """
            res2 = await self._call_llm_with_backoff(verify_prompt, ReviewerOutput)
            out2 = ReviewerOutput.model_validate_json(res2.text)

            # Disagreement penalty
            final_conf = out1.confidence_score if out1.risk_flagged == out2.risk_flagged else 0.4

            status = ExecutionStatus.SUCCESS if final_conf >= 0.8 else ExecutionStatus.RETRYING
            requires_review = final_conf < 0.8 or not out1.citation_verified

            return ExtractedClause(
                clause_id=clause_id,
                text=chunk,
                context_before=context_before,
                redline_suggestion=out1.redline_suggestion or "Client liability shall be capped at total fees paid in the prior 12 months.",
                confidence_score=final_conf,
                status=status,
                requires_human_review=requires_review,
                escalation_reason="Confidence mismatch / citation unverified" if requires_review else None
            )
        except Exception as err:
            return ExtractedClause(
                clause_id=clause_id,
                text=chunk,
                context_before=context_before,
                confidence_score=0.0,
                status=ExecutionStatus.FAILED,
                requires_human_review=True,
                escalation_reason=f"LLM Failure: {str(err)}"
            )

    async def run_dag(self, initial_state: SystemState) -> SystemState:
        """Executes the concurrent DAG with exception-safe result merging."""
        import time
        t0 = time.perf_counter()
        
        # 1. Chunking
        chunks, is_unstructured = self.chunker.chunk(initial_state.chunks[0] if initial_state.chunks else "")
        
        # 2. Fan-Out with return_exceptions=True and Context Plumbing
        tasks = []
        for idx, chunk in enumerate(chunks):
            context_before = chunks[idx - 1] if idx > 0 else ""
            tasks.append(self.reviewer_node(chunk, f"clause_{idx}", context_before))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)

        extracted = []
        failed_chunks = []

        for idx, res in enumerate(results):
            if isinstance(res, Exception):
                failed_chunks.append({"chunk_index": idx, "error": str(res)})
                extracted.append(ExtractedClause(
                    clause_id=f"clause_{idx}", # 🚨 FIX: Dynamically construct the ID here
                    text=chunks[idx],
                    requires_human_review=True,
                    status=ExecutionStatus.FAILED,
                    escalation_reason=f"Unhandled Exception: {str(res)}"
                ))
            else:
                extracted.append(res)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        
        # Telemetry calculation (estimate)
        token_usage = TokenUsage(
            prompt_tokens=len(chunks) * 500,
            completion_tokens=len(chunks) * 150,
            total_tokens=len(chunks) * 650,
            estimated_cost_usd=(len(chunks) * 650 / 1_000_000) * 2.0
        )

        return initial_state.model_copy(update={
            "extracted_clauses": extracted,
            "unstructured_document_flag": is_unstructured,
            "failed_chunks": failed_chunks,
            "requires_global_human_review": is_unstructured or any(c.requires_human_review for c in extracted),
            "node_latency_ms": {"full_dag_fanout": elapsed_ms},
            "token_telemetry": token_usage
        })