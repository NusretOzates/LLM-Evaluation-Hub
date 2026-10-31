import { index, route, type RouteConfig } from "@react-router/dev/routes";

export default [
  index("routes/home.tsx"),
  route("connections", "features/inference/connections.tsx"),
  route("inference", "features/inference/runs-list.tsx"),
  route("inference/new", "features/inference/run-new.tsx"),
  route("inference/runs/:id", "features/inference/run-detail.tsx"),
  route("dataset-ids/:id/output-format", "features/inference/dataset-output.tsx"),
  route("tags", "routes/tags.tsx"),
  route("trash", "routes/trash.tsx"),
  route("datasets", "routes/datasets.tsx"),
  route("datasets/:id", "routes/dataset.tsx"),
  route("dataset-imports", "features/dataset-imports/list.tsx"),
  route("dataset-imports/new", "features/dataset-imports/new.tsx"),
  route("dataset-imports/:id", "features/dataset-imports/detail.tsx"),
] satisfies RouteConfig;
