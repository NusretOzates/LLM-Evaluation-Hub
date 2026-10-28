# Catalog workbench

Local client for the catalog API. React Router runs with server rendering off. In development, `/api` is proxied to `http://127.0.0.1:8000`.

Start both processes from the repository root as described in [docs/how-to/run-locally.md](../docs/how-to/run-locally.md):

```bash
LLM_EVAL_CATALOG=data/catalog uv run uvicorn llm_evaluation_hub.api.asgi:app --factory
```

```bash
cd web && npm run dev -- --host 127.0.0.1 --port 5173
```

The site is at `http://127.0.0.1:5173/datasets`. Page behavior is in [docs/modules/workbench.md](../docs/modules/workbench.md).

`docker compose up --build` from the repository root serves the same workbench at `http://127.0.0.1:8080/datasets`. That path is in [docs/how-to/run-with-docker.md](../docs/how-to/run-with-docker.md).

Use Node 22.22 or newer. Run `npm ci`, `npm run lint`, `npm run format:check`, `npm run typecheck`, `npm test`, and `npm run build`. Real-browser setup and verification are in [Develop and test](../docs/how-to/develop-and-test.md).


To import a Hugging Face dataset from the workbench, open /datasets and choose **Add dataset**. Follow [Import a dataset in the workbench](../docs/how-to/import-a-dataset.md).
