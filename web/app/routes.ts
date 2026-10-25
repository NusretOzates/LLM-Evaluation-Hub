import { index, route, type RouteConfig } from "@react-router/dev/routes";

export default [
  index("routes/home.tsx"),
  route("datasets", "routes/datasets.tsx"),
  route("datasets/:name", "routes/dataset.tsx"),
] satisfies RouteConfig;
