TODO

## LLM configuration

Two backends, no provider switch:

| Stage | Backend | Config | Fallback when unconfigured |
| --- | --- | --- | --- |
| chat, query rewriting, re-ranking | any OpenAI-compatible chat endpoint | `LLM_BASE_URL`, `LLM_TOKEN`, `CHAT_MODEL`, `CHAT_REWRITE_MODEL`, `RERANK_MODEL` | deterministic `Fake*` adapters |
| embeddings | local Ollama | `OLLAMA_BASE_URL`, `OLLAMA_EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS` | none — Ollama must be reachable |

`LLM_BASE_URL` defaults to Groq's free tier. Any other OpenAI-protocol gateway
works by changing that one URL plus the model ids — the HF router
(`https://router.huggingface.co/v1`), OpenAI, or a local vLLM. There is no code
path per vendor.

Embeddings are deliberately not switchable: `chunks.embedding` is a fixed-width
`Vector(768)` column, so another model is a migration and a re-ingest, not a
config edit. `build_embedder` refuses to start if `EMBEDDING_DIMENSIONS` and the
column disagree, and the embedder re-checks the model's real width on its first
batch.

Live checks are opt-in: `uv run pytest -m live` (needs `LLM_TOKEN` and/or a
running Ollama); the default run is fully offline.
