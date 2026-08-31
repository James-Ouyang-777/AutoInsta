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

## Daily automated Reel post

`daily_brand_post.py` picks today's scene from `brands/<brand>/scenes.yaml`
(deterministic by date, no state needed), generates a still image from the
brand's approved character references, animates it into a short video via
fal.ai, writes a caption in the brand voice, and publishes it as an
Instagram Reel.

```bash
python daily_brand_post.py --no-publish   # preview: generate but don't post
python daily_brand_post.py                # generate and publish
python daily_brand_post.py --brand jammy-o --date 2026-09-05  # preview a future rotation slot
```

This repo runs it automatically once a day at 5pm America/New_York via
`.github/workflows/daily-post.yml` (GitHub Actions cron), with
`.github/workflows/refresh-token.yml` refreshing the Instagram long-lived
access token weekly. See those workflow files for the required repo
secrets (`LLM_API_KEY`, `FAL_KEY`, `INSTAGRAM_USER_ID`,
`INSTAGRAM_ACCESS_TOKEN`, `GH_PAT`). A failed scheduled run triggers
GitHub's built-in failure-notification email.

Adding a new brand: create `brands/<name>/` with `brand_style.yaml`,
`scenes.yaml`, and `references/<character>.png` (use
`generate_reference.py --brand <name>` to generate and approve references),
then set `BRAND=<name>` in `.env` or pass `--brand <name>`.

## Troubleshooting

* Ensure `.env` is populated with `LLM_API_KEY` and reachable `LLM_API_BASE`.
* Use `--out` to write CLI results if stdout is truncated.
* Delete `__pycache__` folders if module import issues arise after edits.
