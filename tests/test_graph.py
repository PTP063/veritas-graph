import pytest
from unittest.mock import patch
import uuid
import json
from src.state import SystemState, ExecutionStatus
from src.graph import VeritasGraphOrchestrator
from google import genai

@pytest.mark.asyncio
async def test_concurrent_dag():
    doc_text = """
Section 1. Confidentiality.
This is a standard section.

Section 2. Change of Control.
[MOCK_LOW_CONFIDENCE] This section should trigger a retry but eventually pass.

Article I. Limitation of Liability.
[MOCK_FAIL_FOREVER] This section will fail 3 times and be flagged for human review.
    """
    
    initial_state = SystemState(document_id=str(uuid.uuid4()), chunks=[doc_text])
    
    client = genai.Client(api_key="mock")
    orchestrator = VeritasGraphOrchestrator(client=client, max_concurrency=2)
    
    async def mock_call_llm(prompt, schema, max_retries=3):
        class MockResponse:
            def __init__(self, text):
                self.text = text
                
        confidence = 0.9
        verified = True
        
        if "MOCK_FAIL_FOREVER" in prompt:
            raise RuntimeError("MOCK_FAIL_FOREVER Exception")
            
        if "MOCK_LOW_CONFIDENCE" in prompt:
            confidence = 0.4
            
        data = {
            "risk_flagged": False,
            "risk_category": "None",
            "confidence_score": confidence,
            "citation_verified": verified,
            "redline_suggestion": "mock suggestion"
        }
        return MockResponse(json.dumps(data))
        
    with patch.object(orchestrator, '_call_llm_with_backoff', side_effect=mock_call_llm):
        final_state = await orchestrator.run_dag(initial_state)
    
    assert len(final_state.extracted_clauses) == 3
    
    # Section 1 (normal)
    assert final_state.extracted_clauses[0].status == ExecutionStatus.SUCCESS
    
    # Section 2 (low confidence)
    assert final_state.extracted_clauses[1].status == ExecutionStatus.RETRYING
    assert final_state.extracted_clauses[1].requires_human_review is True
    
    # Section 3 (exception)
    assert final_state.extracted_clauses[2].status == ExecutionStatus.FAILED
    assert final_state.extracted_clauses[2].requires_human_review is True
    
    assert "full_dag_fanout" in final_state.node_latency_ms
