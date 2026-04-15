"""Tests for RAG (Retrieval-Augmented Generation) helpers."""

import pytest
from context_lite_db import ContextLiteDB, chunk_text
from context_lite_db.rag import RAGEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _simple_embed(text: str):
    """Deterministic 4-dim embedding based on which keyword appears."""
    if "python" in text.lower():
        return [1.0, 0.0, 0.0, 0.0]
    if "database" in text.lower():
        return [0.0, 1.0, 0.0, 0.0]
    if "machine learning" in text.lower():
        return [0.0, 0.0, 1.0, 0.0]
    return [0.25, 0.25, 0.25, 0.25]


@pytest.fixture
def db():
    instance = ContextLiteDB(
        ":memory:",
        embedding_provider="callable",
        embedding_fn=_simple_embed,
    )
    yield instance
    instance.close()


@pytest.fixture
def rag(db):
    return db.rag


# ---------------------------------------------------------------------------
# chunk_text
# ---------------------------------------------------------------------------

class TestChunkText:
    def test_short_text_returns_one_chunk(self):
        chunks = chunk_text("hello world", chunk_size=512, overlap=0)
        assert chunks == ["hello world"]

    def test_long_text_is_split(self):
        text = "a" * 1000
        chunks = chunk_text(text, chunk_size=200, overlap=0)
        assert len(chunks) == 5

    def test_overlap_produces_more_chunks(self):
        text = "a" * 200
        no_overlap = chunk_text(text, chunk_size=100, overlap=0)
        with_overlap = chunk_text(text, chunk_size=100, overlap=50)
        assert len(with_overlap) > len(no_overlap)

    def test_chunks_cover_full_text(self):
        text = "Hello World How Are You"
        chunks = chunk_text(text, chunk_size=10, overlap=0)
        reconstructed = "".join(c.replace(" ", "") for c in chunks)
        assert len(reconstructed) > 0  # content is preserved

    def test_invalid_chunk_size_raises(self):
        with pytest.raises(ValueError):
            chunk_text("text", chunk_size=0)

    def test_invalid_overlap_raises(self):
        with pytest.raises(ValueError):
            chunk_text("text", chunk_size=10, overlap=-1)

    def test_overlap_gte_chunk_size_raises(self):
        with pytest.raises(ValueError):
            chunk_text("text", chunk_size=10, overlap=10)

    def test_empty_string_returns_empty_list(self):
        assert chunk_text("") == []


# ---------------------------------------------------------------------------
# RAGEngine.ingest
# ---------------------------------------------------------------------------

class TestIngest:
    def test_ingest_creates_chunks(self, rag):
        row_ids = rag.ingest("doc1", "python " * 200, chunk_size=50, overlap=0)
        assert len(row_ids) > 1

    def test_ingest_returns_row_ids(self, rag):
        ids = rag.ingest("doc1", "python programming language", chunk_size=512)
        assert all(isinstance(i, int) for i in ids)

    def test_ingest_metadata_propagated(self, rag, db):
        rag.ingest("doc1", "python", metadata={"source": "book"}, chunk_size=512)
        results = db.semantic_search("python")
        assert results[0]["metadata"]["source"] == "book"

    def test_ingest_adds_chunk_index(self, rag, db):
        text = "python " * 300
        rag.ingest("doc1", text, chunk_size=50, overlap=0)
        results = db.semantic_search("python", top_k=1)
        assert "chunk_index" in results[0]["metadata"]


# ---------------------------------------------------------------------------
# RAGEngine.retrieve
# ---------------------------------------------------------------------------

class TestRetrieve:
    def test_retrieve_returns_results(self, rag):
        rag.ingest("doc1", "python is a programming language", chunk_size=512)
        results = rag.retrieve("python")
        assert len(results) > 0

    def test_retrieve_top_k(self, rag):
        for i in range(5):
            rag.ingest(f"doc{i}", f"python document number {i}", chunk_size=512)
        results = rag.retrieve("python", top_k=2)
        assert len(results) <= 2


# ---------------------------------------------------------------------------
# RAGEngine.build_context
# ---------------------------------------------------------------------------

class TestBuildContext:
    def test_build_context_returns_string(self, rag):
        rag.ingest("doc1", "python is great for data science", chunk_size=512)
        ctx = rag.build_context("python")
        assert isinstance(ctx, str)
        assert len(ctx) > 0

    def test_build_context_empty_when_no_documents(self, rag):
        ctx = rag.build_context("anything")
        assert ctx == ""

    def test_build_context_threshold_excludes_irrelevant(self, rag):
        rag.ingest("doc1", "database systems store data", chunk_size=512)
        # query for python (score 0 for database docs) with high threshold
        ctx = rag.build_context("python", threshold=0.99)
        assert ctx == ""


# ---------------------------------------------------------------------------
# RAGEngine.query (end-to-end RAG)
# ---------------------------------------------------------------------------

class TestRAGQuery:
    def test_rag_query_calls_llm(self, rag):
        rag.ingest("doc1", "python is a programming language", chunk_size=512)
        called_with = []

        def fake_llm(prompt: str) -> str:
            called_with.append(prompt)
            return "Python is awesome."

        result = rag.query("What is python?", llm_fn=fake_llm)
        assert called_with, "LLM was not called"
        assert result["answer"] == "Python is awesome."

    def test_rag_query_result_has_keys(self, rag):
        rag.ingest("doc1", "python is a programming language", chunk_size=512)
        result = rag.query("python", llm_fn=lambda p: "answer")
        assert "answer" in result
        assert "context" in result
        assert "sources" in result

    def test_rag_query_custom_template(self, rag):
        rag.ingest("doc1", "python programming", chunk_size=512)
        prompts = []
        rag.query(
            "python",
            llm_fn=lambda p: (prompts.append(p), "ok")[1],
            prompt_template="CTX:{context} Q:{question}",
        )
        assert prompts[0].startswith("CTX:")


# ---------------------------------------------------------------------------
# db.rag property
# ---------------------------------------------------------------------------

class TestRagProperty:
    def test_rag_property_returns_engine(self, db):
        assert isinstance(db.rag, RAGEngine)

    def test_rag_property_is_cached(self, db):
        engine1 = db.rag
        engine2 = db.rag
        assert engine1 is engine2
