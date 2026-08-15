"""
Veritas-Graph: Main Execution Entry Point
Runs the end-to-end pipeline and outputs clean telemetry for demo.
"""

import asyncio
import logging
import os
import sys

from docx import Document
from docx.document import Document as DocumentType
from dotenv import load_dotenv
from google import genai

from src.config import DEFAULT_MODEL_NAME, MAX_CONCURRENCY
from src.graph import VeritasGraphOrchestrator
from src.pipeline import VeritasPipeline

# Configure global application logging
logging.basicConfig(
    level=logging.WARNING,  # Suppress INFO logs to keep the demo output clean, but allow warnings/errors
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Entry point for the Veritas-Graph CLI demo.

    Generates a mock contract, initializes the Gemini orchestrator,
    and runs the DAG to produce native OOXML redlines.
    """
    print("\n" + "=" * 60)
    print("🚀 INITIALIZING VERITAS-GRAPH PIPELINE 🚀")
    print("=" * 60 + "\n")

    load_dotenv()
    api_key: str | None = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ ERROR: GEMINI_API_KEY not found.")
        logger.critical("GEMINI_API_KEY environment variable is missing.")
        sys.exit(1)

    print("📄 Preparing mock corporate contract (mock_contract.docx)...")
    doc: DocumentType = Document()

    # Single paragraph and single run to match the AST engine's target
    raw_clause: str = "The client agrees to unconditionally indemnify and hold harmless the provider for any and all damages, without any financial cap or limitation of liability."

    p = doc.add_paragraph()
    run = p.add_run(raw_clause)
    run.bold = True
    doc.save("mock_contract.docx")

    print(f"🤖 Booting {DEFAULT_MODEL_NAME} Orchestrator...")
    client = genai.Client(api_key=api_key)
    orchestrator = VeritasGraphOrchestrator(client, max_concurrency=MAX_CONCURRENCY)
    pipeline = VeritasPipeline(orchestrator)

    print("⚡ Executing Asynchronous DAG Fan-Out...")
    final_state = await pipeline.process_contract(
        document_text=raw_clause, docx_path="mock_contract.docx"
    )

    print("\n" + "=" * 60)
    print("✅ PIPELINE EXECUTION COMPLETE ✅")
    print("=" * 60)

    print("\n📊 TELEMETRY:")
    print(f"  - Node Latency: {final_state.node_latency_ms.get('full_dag_fanout', 0):.2f} ms")
    print(f"  - Total Tokens (Estimated): {final_state.token_telemetry.total_tokens}")

    print("\n🔍 AUDIT LOG:")
    if final_state.failed_chunks:
        print(f"  - ⚠️ Failed Injections: {len(final_state.failed_chunks)}")
        for f in final_state.failed_chunks:
            print(f"    * {f.get('error')}")
    else:
        print("  - 🟢 Failed Injections: 0")

    print(f"  - 🟢 Successful Redlines: {len(final_state.redlines)}")
    for r in final_state.redlines:
        print(f"    * Original: '{r.original_text[:40]}...'")
        print(f"    * Replacement: '{r.replacement_text[:40]}...'")

    print(f"\n📂 OUTPUT: redlined_{final_state.document_id}.docx\n")


if __name__ == "__main__":
    asyncio.run(main())
