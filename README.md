# Veritas-Graph: Deterministic OOXML Redlining Engine

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An asynchronous, multi-agent contract due-diligence pipeline engineered with raw Python, `asyncio`, and `lxml`. Built to bypass brittle LLM chat wrappers and output native Microsoft Word Tracked Changes (`.docx`) with verified text provenance and zero inline formatting corruption.

---

## System Architecture
[Raw Legal PDF / Text]
│
▼
┌─────────────────────────────────────────────────────────────┐
│ 1. Hierarchical LegalChunker                                │
│    - Regex boundary detection (Articles, Sections, Recitals)│
│    - Mechanical rolling-window fallback (200-char overlap)  │
└──────────────────────────────┬──────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Asynchronous DAG Fan-Out (asyncio + Semaphore Pool)      │
│    - Reviewer Node: Structured Risk Extraction              │
│    - Verification Node: Self-consistency guardrail          │
│    - Safe state merging via return_exceptions=True          │
└──────────────────────────────┬──────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────┐
│ 3. PDF-to-DOCX Alignment Bridge (Sequence Matching)        │
│    - Preceding-context weighting for disambiguation         │
│    - Identical boilerplate resolution                       │
└──────────────────────────────┬──────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Low-Level OOXML AST Engine (lxml DOM manipulation)       │
│    - Surgical run splitting with copy.deepcopy(rPr)         │
│    - Global w:id counter enforcement                        │
│    - Native <w:del> and <w:ins> node injection              │
└──────────────────────────────┬──────────────────────────────┘
│
▼
[Production-Ready Redlined .docx + Telemetry Audit]


---

## Core Engineering Decisions

* **Surgical OOXML Run-Splitting:** Standard string replacement destroys inline run formatting (`w:rPr`). Because `lxml` enforces single-parent DOM constraints, naive element insertion detaches formatting tags from the source run. Veritas-Graph uses `copy.deepcopy()` to clone run properties into injected `<w:del>` and `<w:ins>` nodes, maintaining exact styling across untouched text.
* **Global AST ID Counter:** Word requires unique `w:id` values across all revision nodes in the document tree. The AST engine dynamically discovers the highest existing `w:id` across paragraph definitions and increments sequentially.
* **Fail-Loudly Immutability:** Eliminates silent drops. Ambiguous alignment results or sub-threshold LLM confidence scores trip an explicit `requires_global_human_review` flag, record detailed failure metadata into `failed_chunks`, and inject an audit banner at the document root.
* **Context-Weighted Alignment:** Disambiguates repeated standard boilerplate clauses across multi-page agreements by passing preceding chunk context (`chunks[idx - 1]`) into the fuzzy sequence matcher.

---

## Known Architecture Limitations & Roadmap

* **Multi-Run Span Accumulation:** Clauses spanning across multiple fragmented `<w:r>` runs currently escalate to manual review with an explicit error. *Roadmap:* Implement a character-offset run accumulator.
* **Aligner Candidate Pre-Filtering:** Paragraph alignment runs at $O(n^2)$ complexity. *Roadmap:* Integrate TF-IDF token pre-filtering to bound sequence matching to top-5 candidate paragraphs.
* **Table Cell Traversal:** `doc.paragraphs` is blind to `<w:tbl>` containers. *Roadmap:* Add explicit XML traversal for table grids and fee schedules.

---

## Quickstart

**1. Environment Setup**
```bash
git clone https://github.com/PTP063/veritas-graph.git
cd veritas-graph
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**2. Configuration**
Create a `.env` file in the root directory and add your Google Gemini API key:
```env
GEMINI_API_KEY=your_api_key_here
```

**3. Run the Pipeline**
Execute the orchestration pipeline demo:
```bash
python main.py
```
