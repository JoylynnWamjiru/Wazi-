"""Contract for the retrieval/generation pipeline.

Both the real pipeline (``ingestion.pipeline.get_response``) and the mock
pipeline return a ``PipelineResponse``-shaped dict, so the UI can depend on a
single stable shape regardless of which backend is wired in.
"""

from typing import Protocol, TypedDict


class PipelineResponse(TypedDict):
    """The shape every pipeline response must have."""

    text: str          # the answer, in the citizen's own language/register
    citation: str      # source document + page the answer is grounded in
    last_updated: str  # freshness of the underlying source ("N/A" if unknown)


class Pipeline(Protocol):
    def get_response(self, query: str) -> PipelineResponse:
        ...
