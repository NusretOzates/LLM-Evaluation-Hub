import { index, route, type RouteConfig } from "@react-router/dev/routes";

export default [
  index("routes/home.tsx"),
  route("tags", "routes/tags.tsx"),
  route("trash", "routes/trash.tsx"),
  route("datasets", "routes/datasets.tsx"),
  route("datasets/:name", "routes/dataset.tsx"),
  route("dataset-imports", "features/dataset-imports/list.tsx"),
  route("dataset-imports/new", "features/dataset-imports/new.tsx"),
  route("dataset-imports/:id", "features/dataset-imports/detail.tsx"),
] satisfies RouteConfig;
