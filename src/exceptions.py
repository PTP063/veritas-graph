"""
Custom domain exceptions for Veritas-Graph.
"""


class VeritasError(Exception):
    """Base exception for all Veritas-Graph errors."""

    pass


class VeritasConfigurationError(VeritasError):
    """Raised when there is a configuration or environment error."""

    pass


class GraphExecutionError(VeritasError):
    """Raised when the DAG fails to execute properly."""

    pass


class ChunkingError(VeritasError):
    """Raised when the text chunker fails."""

    pass


class OOXMLInjectionError(VeritasError):
    """Raised when AST manipulation of the DOCX fails."""

    pass
