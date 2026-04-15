"""
context_lite_db – RAG (Retrieval-Augmented Generation) module.

Provides helpers for:
1. Ingesting text documents as overlapping chunks into the vector store.
2. Retrieving the most relevant chunks for a query.
3. Assembling a ready-to-use context string (prompt prefix) for an LLM.
4. Optionally calling a user-supplied LLM function to produce an answer.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 64,
) -> List[str]:
    """Split *text* into overlapping character-level chunks.

    Parameters
    ----------
    text:
        The source text to split.
    chunk_size:
        Approximate character length of each chunk.
    overlap:
        Number of characters shared between consecutive chunks.

    Returns
    -------
    list[str]
        Non-empty chunks.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be less than chunk_size")

    chunks: List[str] = []
    step = chunk_size - overlap
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks


class RAGEngine:
    """High-level RAG interface built on top of :class:`~context_lite_db.db.ContextLiteDB`.

    Parameters
    ----------
    db:
        A :class:`~context_lite_db.db.ContextLiteDB` instance with an embedding
        provider configured.
    chunk_size:
        Default character length for document chunks.
    overlap:
        Default overlap between consecutive chunks.
    """

    def __init__(
        self,
        db: Any,
        chunk_size: int = 512,
        overlap: int = 64,
    ) -> None:
        self._db = db
        self.chunk_size = chunk_size
        self.overlap = overlap

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest(
        self,
        doc_id: str,
        text: str,
        collection: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
        chunk_size: Optional[int] = None,
        overlap: Optional[int] = None,
    ) -> List[int]:
        """Chunk *text* and store every chunk with its embedding.

        Parameters
        ----------
        doc_id:
            Stable application-level identifier for this document.
        text:
            Full document text to ingest.
        collection:
            Vector-store collection to write into.
        metadata:
            Arbitrary key-value metadata attached to every chunk.
        chunk_size / overlap:
            Override instance defaults for this call.

        Returns
        -------
        list[int]
            The row IDs of the inserted vector-store rows.
        """
        cs = chunk_size if chunk_size is not None else self.chunk_size
        ov = overlap if overlap is not None else self.overlap
        chunks = chunk_text(text, chunk_size=cs, overlap=ov)

        row_ids: List[int] = []
        for i, chunk in enumerate(chunks):
            chunk_meta = dict(metadata or {})
            chunk_meta["chunk_index"] = i
            chunk_meta["total_chunks"] = len(chunks)
            row_id = self._db.add_document(
                doc_id=f"{doc_id}__chunk_{i}",
                text=chunk,
                collection=collection,
                metadata=chunk_meta,
            )
            row_ids.append(row_id)
        return row_ids

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        collection: Optional[str] = None,
        threshold: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Return the *top_k* most relevant chunks for *query*.

        Delegates to :meth:`~context_lite_db.db.ContextLiteDB.semantic_search`.
        """
        return self._db.semantic_search(
            query=query,
            top_k=top_k,
            collection=collection,
            threshold=threshold,
        )

    # ------------------------------------------------------------------
    # Context assembly
    # ------------------------------------------------------------------

    def build_context(
        self,
        query: str,
        top_k: int = 5,
        collection: Optional[str] = None,
        threshold: float = 0.0,
        separator: str = "\n\n---\n\n",
        preamble: str = "Relevant context:\n\n",
    ) -> str:
        """Retrieve chunks and assemble them into a single context string.

        Returns
        -------
        str
            A text block ready to prepend to an LLM prompt.
        """
        results = self.retrieve(
            query=query,
            top_k=top_k,
            collection=collection,
            threshold=threshold,
        )
        if not results:
            return ""
        passages = [r["text"] for r in results]
        return preamble + separator.join(passages)

    # ------------------------------------------------------------------
    # End-to-end RAG
    # ------------------------------------------------------------------

    def query(
        self,
        question: str,
        llm_fn: Callable[[str], str],
        top_k: int = 5,
        collection: Optional[str] = None,
        threshold: float = 0.0,
        prompt_template: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retrieve context and generate an answer with *llm_fn*.

        Parameters
        ----------
        question:
            The user's natural-language question.
        llm_fn:
            A callable that accepts a prompt string and returns the LLM
            response string.  You can wrap any LLM (OpenAI, Ollama, …) here.
        top_k:
            Number of context chunks to retrieve.
        collection:
            Restrict retrieval to this collection.
        threshold:
            Minimum similarity score for retrieved chunks.
        prompt_template:
            Optional f-string template with ``{context}`` and ``{question}``
            placeholders.  Defaults to a sensible built-in template.

        Returns
        -------
        dict with keys:
            * ``"answer"`` – the LLM response
            * ``"context"`` – the assembled context string
            * ``"sources"`` – the raw retrieval results
        """
        sources = self.retrieve(
            query=question,
            top_k=top_k,
            collection=collection,
            threshold=threshold,
        )
        context = self.build_context(
            query=question,
            top_k=top_k,
            collection=collection,
            threshold=threshold,
        )

        if prompt_template is None:
            prompt_template = (
                "Use the following context to answer the question.\n\n"
                "{context}\n\n"
                "Question: {question}\n\n"
                "Answer:"
            )

        prompt = prompt_template.format(context=context, question=question)
        answer = llm_fn(prompt)

        return {
            "answer": answer,
            "context": context,
            "sources": sources,
        }
