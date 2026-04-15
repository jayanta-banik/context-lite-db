"""
context_lite_db – embeddings module.

Provides a pluggable interface for generating vector embeddings.

Supported providers
-------------------
* ``"sentence-transformers"`` – uses the ``sentence-transformers`` library
  with a model downloaded on first use (requires the optional dep).
* Any Python callable ``(text: str) -> list[float]`` passed directly as
  the ``embedding_fn`` argument to :class:`EmbeddingProvider`.
"""

from __future__ import annotations

from typing import Callable, List, Optional


class EmbeddingProvider:
    """Wraps different embedding back-ends behind a single ``encode`` interface.

    Parameters
    ----------
    provider:
        ``"sentence-transformers"`` to use the sentence-transformers library,
        or ``"callable"`` when supplying a custom *embedding_fn*.
    model_name:
        Model name passed to sentence-transformers (ignored for callable).
    embedding_fn:
        A callable ``(text: str) -> list[float]`` used when *provider* is
        ``"callable"``.
    """

    def __init__(
        self,
        provider: str = "sentence-transformers",
        model_name: str = "all-MiniLM-L6-v2",
        embedding_fn: Optional[Callable[[str], List[float]]] = None,
    ) -> None:
        self.provider = provider
        self.model_name = model_name
        self.embedding_fn = embedding_fn
        self._model = None

        if provider == "callable":
            if embedding_fn is None:
                raise ValueError(
                    "embedding_fn must be provided when provider='callable'"
                )
        elif provider == "sentence-transformers":
            pass  # lazy-load on first encode call
        else:
            raise ValueError(
                f"Unknown provider '{provider}'. "
                "Choose 'sentence-transformers' or 'callable'."
            )

    def _load_model(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is required for provider='sentence-transformers'. "
                "Install it with: pip install sentence-transformers"
            ) from exc
        self._model = SentenceTransformer(self.model_name)

    def encode(self, text: str) -> List[float]:
        """Return a dense embedding vector for *text*."""
        if self.provider == "callable":
            return list(self.embedding_fn(text))  # type: ignore[misc]
        self._load_model()
        vector = self._model.encode(text, convert_to_numpy=True)
        return vector.tolist()

    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        """Return embedding vectors for a list of texts."""
        if self.provider == "callable":
            return [list(self.embedding_fn(t)) for t in texts]  # type: ignore[misc]
        self._load_model()
        vectors = self._model.encode(texts, convert_to_numpy=True)
        return [v.tolist() for v in vectors]
