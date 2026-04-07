# content-engine-v0

`content-engine-v0` turns a content idea into multiple platform-specific post variants through a FastAPI service or Typer CLI.

## Quickstart

```bash
uv venv && source .venv/bin/activate
uv pip install -e .
cp .env.example .env  # add LLM_API_KEY
uv run uvicorn content_engine.api:app --reload
curl -X POST http://localhost:8000/generate -H "Content-Type: application/json" -d '{
  "platform":"x",
  "topic":"MVP launch",
  "keywords":["build fast","feedback"],
  "brand":{"voice":"witty, concise","audience":"founders","reading_level":"grade 8","prohibited":["guaranteed results"]},
  "cta_style":"question",
  "n_variants":3
}'
# CLI:
autocreate generate --platform x --topic "MVP launch" --keywords "build fast,feedback" --voice "witty, concise" --audience "founders" --reading-level "grade 8" --cta-style question --n 3
```

## Troubleshooting

* Ensure `.env` is populated with `LLM_API_KEY` and reachable `LLM_API_BASE`.
* Use `--out` to write CLI results if stdout is truncated.
* Delete `__pycache__` folders if module import issues arise after edits.
