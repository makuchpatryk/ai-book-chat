TODO

## LLM providers

Chat, query rewriting and re-ranking share one provider setting each
(`CHAT_PROVIDER`, `RERANK_PROVIDER`); embeddings have their own
(`EMBEDDING_PROVIDER`). Every adapter degrades to an offline fake when its key
is missing, so the test suite and a keyless checkout both work.

| Provider | Value | Key | Used for | Notes |
| --- | --- | --- | --- | --- |
| Hugging Face Inference Providers | `huggingface` (default) | `HF_TOKEN`, falling back to `LLM_API_KEY` | chat, rewrite, re-rank | OpenAI-compatible router at `https://router.huggingface.co/v1` |
| Anthropic | `anthropic` | `LLM_API_KEY` | chat, rewrite, re-rank | Was the default; structured output for re-rank |
| Mistral | `mistral` | `LLM_API_KEY` | chat, rewrite, re-rank | `mistralai` is not installed — falls back to the fakes |
| Ollama | `ollama` | none | chat, rewrite, re-rank | Local, via `OLLAMA_BASE_URL` |
| OpenAI | `openai` (default) | `OPENAI_API_KEY` | embeddings | `text-embedding-3-small`, 1536d |
| Hugging Face | `huggingface` | `HF_TOKEN` | embeddings | Built but not enabled: needs a vector-column migration first |

On Hugging Face the suffix on the model id picks the routing policy:
`:cheapest` (lowest price per output token), `:fastest` (the router default),
`:preferred` (the account's provider order), or a pinned provider such as
`:groq` / `:together`. Changing it is a `.env` edit.

Rolling back to the previous setup takes no code change:

```
CHAT_PROVIDER=anthropic
CHAT_MODEL=claude-sonnet-5
CHAT_REWRITE_MODEL=claude-haiku-4-5
RERANK_PROVIDER=anthropic
RERANK_MODEL=claude-haiku-4-5
```

Live provider checks are opt-in: `uv run pytest -m live` (needs `HF_TOKEN`
and/or `OPENAI_API_KEY`); the default run is fully offline.
