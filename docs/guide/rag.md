# Retrieval-Augmented Generation (RAG)

The `db.rag` property exposes a [`RAGEngine`](../api/rag.md)
that handles the full RAG pipeline: chunking long documents, embedding each
chunk, storing them in the vector store, retrieving relevant chunks for a
query, and optionally calling an LLM to generate an answer.

---

## Ingesting documents

```python
with open("article.txt") as f:
    text = f.read()

db.rag.ingest(
    doc_id="article_1",
    text=text,
    collection="docs",        # optional, defaults to "default"
    metadata={"source": "article.txt"},
    chunk_size=512,           # characters per chunk
    overlap=64,               # character overlap between chunks
)
```

Each chunk is stored with `chunk_index` and `total_chunks` keys added to its
metadata automatically.

---

## Retrieving relevant chunks

```python
chunks = db.rag.retrieve(
    "What is the article about?",
    top_k=5,
    collection="docs",
    threshold=0.0,
)

for c in chunks:
    print(c["score"], c["text"][:100])
```

---

## Building a context string

```python
context = db.rag.build_context(
    "What is the article about?",
    top_k=5,
    collection="docs",
    preamble="Relevant context:\n\n",
    separator="\n\n---\n\n",
)
print(context)
```

---

## End-to-end RAG with any LLM

`db.rag.query` retrieves context and calls *any* callable you provide:

```python
# OpenAI example
import openai

def call_openai(prompt: str) -> str:
    resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content

result = db.rag.query(
    "What is this article about?",
    llm_fn=call_openai,
    top_k=5,
    collection="docs",
    # Optional: customise the prompt template
    prompt_template=(
        "Use the context below to answer the question.\n\n"
        "{context}\n\n"
        "Question: {question}\n\nAnswer:"
    ),
)

print(result["answer"])
print(result["context"])   # assembled context string
print(result["sources"])   # list of retrieved chunk dicts
```

---

## Ollama / local LLM example

```python
import httpx

def ollama_llm(prompt: str) -> str:
    resp = httpx.post(
        "http://localhost:11434/api/generate",
        json={"model": "llama3", "prompt": prompt, "stream": False},
    )
    return resp.json()["response"]

result = db.rag.query("Summarise the document.", llm_fn=ollama_llm)
print(result["answer"])
```
