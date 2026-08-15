"""
Veritas-Graph: Bounded Async DAG with Self-Consistency and Structured Outputs.
"""

import asyncio
import random
import time
from typing import Any

from google import genai
from google.genai import types
from google.genai.types import GenerateContentResponse
from pydantic import BaseModel, Field

from src.chunker import LegalChunker
from src.config import (
    CONFIDENCE_THRESHOLD_SUCCESS,
    DEFAULT_MODEL_NAME,
    MAX_CONCURRENCY,
    MAX_RETRIES,
    REVIEWER_PROMPT,
    VERIFICATION_PROMPT,
)
from src.exceptions import GraphExecutionError
from src.state import ExecutionStatus, ExtractedClause, SystemState, TokenUsage


class ReviewerOutput(BaseModel):
    """Structured output expected from the LLM."""

    risk_flagged: bool = Field(
        description="Whether the clause contains significant legal liability"
    )
    risk_category: str = Field(
        description="e.g., Change of Control, Indemnification, Unlimited Liability"
    )
    confidence_score: float = Field(description="Confidence from 0.0 to 1.0")
    citation_verified: bool = Field(
        description="True if claim is strictly grounded in the provided text"
    )
    redline_suggestion: str = Field(
        description="Proposed replacement text eliminating the liability"
    )


class VeritasGraphOrchestrator:
    """Orchestrates the asynchronous extraction and review DAG."""

    def __init__(self, client: genai.Client, max_concurrency: int = MAX_CONCURRENCY) -> None:
        """Initializes the orchestrator.

        Args:
            client: The GenAI client.
            max_concurrency: Maximum number of concurrent LLM requests.
        """
        self.client = client
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.chunker = LegalChunker()

    async def _call_llm_with_backoff(
        self, prompt: str, schema: Any, max_retries: int = MAX_RETRIES
    ) -> GenerateContentResponse:
        """Bounded LLM execution with exponential backoff and jitter.

        Args:
            prompt: The instruction prompt.
            schema: The Pydantic schema for structured output.
            max_retries: Maximum retry attempts on failure.

        Returns:
            The raw GenerateContentResponse from the model.

        Raises:
            GraphExecutionError: If all retry attempts fail.
        """
        for attempt in range(max_retries):
            try:
                async with self.semaphore:
                    response: GenerateContentResponse = await asyncio.to_thread(
                        self.client.models.generate_content,
                        model=DEFAULT_MODEL_NAME,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=schema,
                            temperature=0.1,
                        ),
                    )
                    return response
            except Exception as e:
                if attempt == max_retries - 1:
                    raise GraphExecutionError(
                        f"LLM call failed after {max_retries} attempts: {e}"
                    ) from e
                sleep_time: float = (2**attempt) + random.uniform(0.1, 0.5)
                await asyncio.sleep(sleep_time)

        raise GraphExecutionError("Unreachable LLM execution failure.")

    async def reviewer_node(
        self, chunk: str, clause_id: str, context_before: str = ""
    ) -> ExtractedClause:
        """Executes Structured Review + Secondary Verification pass (Self-Consistency).

        Args:
            chunk: The target text chunk.
            clause_id: The unique identifier for this clause.
            context_before: Text immediately preceding this chunk.

        Returns:
            An ExtractedClause containing the review and redline suggestions.
        """
        prompt: str = REVIEWER_PROMPT.format(chunk=chunk)

        try:
            res1: GenerateContentResponse = await self._call_llm_with_backoff(
                prompt, ReviewerOutput
            )
            if not res1.text:
                raise GraphExecutionError("Empty response from primary LLM pass.")
            out1: ReviewerOutput = ReviewerOutput.model_validate_json(res1.text)

            # Verification Pass (Self-Consistency Guardrail)
            verify_prompt: str = VERIFICATION_PROMPT.format(chunk=chunk)
            res2: GenerateContentResponse = await self._call_llm_with_backoff(
                verify_prompt, ReviewerOutput
            )
            if not res2.text:
                raise GraphExecutionError("Empty response from verification LLM pass.")
            out2: ReviewerOutput = ReviewerOutput.model_validate_json(res2.text)

            # Disagreement penalty
            final_conf: float = (
                out1.confidence_score if out1.risk_flagged == out2.risk_flagged else 0.4
            )

            status: ExecutionStatus = (
                ExecutionStatus.SUCCESS
                if final_conf >= CONFIDENCE_THRESHOLD_SUCCESS
                else ExecutionStatus.RETRYING
            )
            requires_review: bool = (
                final_conf < CONFIDENCE_THRESHOLD_SUCCESS or not out1.citation_verified
            )

            return ExtractedClause(
                clause_id=clause_id,
                text=chunk,
                context_before=context_before,
                redline_suggestion=out1.redline_suggestion
                or "Client liability shall be capped at total fees paid in the prior 12 months.",
                confidence_score=final_conf,
                status=status,
                requires_human_review=requires_review,
                escalation_reason="Confidence mismatch / citation unverified"
                if requires_review
                else None,
            )
        except Exception as err:
            return ExtractedClause(
                clause_id=clause_id,
                text=chunk,
                context_before=context_before,
                confidence_score=0.0,
                status=ExecutionStatus.FAILED,
                requires_human_review=True,
                escalation_reason=f"LLM Failure: {str(err)}",
            )

    async def run_dag(self, initial_state: SystemState) -> SystemState:
        """Executes the concurrent DAG with exception-safe result merging.

        Args:
            initial_state: The baseline SystemState containing raw chunk inputs.

        Returns:
            The updated SystemState reflecting the execution graph results.
        """
        t0: float = time.perf_counter()

        # 1. Chunking
        raw_text: str = initial_state.chunks[0] if initial_state.chunks else ""
        chunks, is_unstructured = self.chunker.chunk(raw_text)

        # 2. Fan-Out with return_exceptions=True and Context Plumbing
        tasks: list[asyncio.Task[ExtractedClause]] = []
        for idx, chunk in enumerate(chunks):
            context_before: str = chunks[idx - 1] if idx > 0 else ""
            # Wrap coroutine in a Task to satisfy typing for asyncio.gather
            task = asyncio.create_task(self.reviewer_node(chunk, f"clause_{idx}", context_before))
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        extracted: list[ExtractedClause] = []
        failed_chunks: list[dict[str, Any]] = []

        for idx, res in enumerate(results):
            if isinstance(res, Exception):
                failed_chunks.append({"chunk_index": idx, "error": str(res)})
                extracted.append(
                    ExtractedClause(
                        clause_id=f"clause_{idx}",
                        text=chunks[idx],
                        requires_human_review=True,
                        status=ExecutionStatus.FAILED,
                        escalation_reason=f"Unhandled Exception: {str(res)}",
                    )
                )
            else:
                extracted.append(res)  # type: ignore

        elapsed_ms: float = (time.perf_counter() - t0) * 1000.0

        # Telemetry calculation (estimate)
        token_usage = TokenUsage(
            prompt_tokens=len(chunks) * 500,
            completion_tokens=len(chunks) * 150,
            total_tokens=len(chunks) * 650,
            estimated_cost_usd=(len(chunks) * 650 / 1_000_000) * 2.0,
        )

        return initial_state.model_copy(
            update={
                "extracted_clauses": extracted,
                "unstructured_document_flag": is_unstructured,
                "failed_chunks": failed_chunks,
                "requires_global_human_review": is_unstructured
                or any(c.requires_human_review for c in extracted),
                "node_latency_ms": {"full_dag_fanout": elapsed_ms},
                "token_telemetry": token_usage,
            }
        )
