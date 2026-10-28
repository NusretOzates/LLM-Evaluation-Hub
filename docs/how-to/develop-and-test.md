---
type: Playbook
title: Develop and test
description: Set up locked dependencies and verify backend, frontend, contracts and docs.
generated: { by: process:codex-refactor, at: 2026-10-26T13:56:10+03:00 }
status: stable
---

# Develop and test

Use Linux or WSL with a local filesystem, Python 3.12 or newer, uv, and Node 22.22 or newer. CI uses Python 3.12 and Node 24. Native Windows and network-filesystem locking are outside the supported persistence contract. Source layout is in [Code map](../architecture/code-map.md).

## Install and verify

Run from the repository root:

```bash
uv sync --locked
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run ty check
uv run pytest
uv run python scripts/export_contract.py --check
uv run python scripts/check_docs.py
```

Then install the frontend from its lockfile and verify it:

```bash
cd web
npm ci
npm run lint
npm run format:check
npm run typecheck
npm test
npm run build
npx playwright install --with-deps chromium
npm run test:e2e
```

Browser tests build the production SPA, serve it through Vite preview and own ports 8000 and 5173 and refuse to reuse running servers. Stop a local development stack first. The fixture server creates a temporary synthetic catalog, never reads your configured catalog and never contacts Hugging Face. Tests cover UUID links, page facets, keyboard selection, tag links, blocked browser storage/clipboard, and three viewport sizes. Failure traces and screenshots live in ignored `web/test-results/`.

## Change a capability

1. Find the behavior and owning tests in the code map. Add a focused regression before changing a contract.
2. Keep processing and records independent of HTTP. Keep route coordination separate from feature display and pure inspector transformations.
3. When API models change, run `uv run python scripts/export_contract.py` and review `web/app/api-schema.ts`. The checked generator supports this API's emitted JSON Schema constructs and fails on unsupported ones. Generated declarations do not replace runtime parsing in `catalog-parsers.ts`.
4. Run affected checks, then the commands above before handoff. Update the corresponding module contract, code-map rows and configuration recipe with the code.

`npm run format` applies the formatter. Python formatting uses `uv run ruff format src tests scripts`. Do not edit generated TypeScript manually. Keep arbitrary JSON at its real boundary; do not replace role-specific message types with `any`.

The documentation checker validates Markdown file targets and concept YAML `type` fields. It does not validate fragment anchors, external links, examples, complete OKF conformance, or empirical claims. The GitHub workflow runs these checks, frontend checks, Python checks and browser flows without private datasets.
