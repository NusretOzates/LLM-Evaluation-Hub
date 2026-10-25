# Catalog workbench

Local client for the catalog API. React Router runs with server rendering off. In development, `/api` is proxied to `http://127.0.0.1:8000`.

Start the API from the repository root, then start the site:

```bash
LLM_EVAL_CATALOG=data/catalog uv run uvicorn llm_evaluation_hub.api.asgi:app --factory
```

```bash
cd web && npm run dev
```

The site is served at `http://127.0.0.1:5173`.
