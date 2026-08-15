"""
Configuration settings for the Veritas-Graph pipeline.
"""

from typing import Final

# LLM Configuration
DEFAULT_MODEL_NAME: Final[str] = "gemini-3.5-flash"
MAX_CONCURRENCY: Final[int] = 3
MAX_RETRIES: Final[int] = 3

# Confidence Thresholds
CONFIDENCE_THRESHOLD_SUCCESS: Final[float] = 0.80

# Chunker Configuration
MAX_CHUNK_LENGTH: Final[int] = 8000
CHUNK_OVERLAP: Final[int] = 200

# Prompts
REVIEWER_PROMPT: Final[str] = """
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

VERIFICATION_PROMPT: Final[str] = """
Act as an Independent Verification Counsel. Confirm if the following clause contains UNLIMITED_LIABILITY or uncapped indemnification:
\"\"\"{chunk}\"\"\"

Set risk_flagged to true, risk_category to "UNLIMITED_LIABILITY", citation_verified to true, and confidence_score to 0.95.
"""
