import type { Dataset } from "../catalog-types";

export function subtreeCounts(datasets: Dataset[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const dataset of datasets) {
    const paths = new Set<string>();
    for (const tag of dataset.tags) {
      const parts = tag.split("/");
      for (let i = 1; i <= parts.length; i++) paths.add(parts.slice(0, i).join("/"));
    }
    for (const path of paths) counts.set(path, (counts.get(path) ?? 0) + 1);
  }
  return counts;
}

export function datasetsUnder(datasets: Dataset[], tag: string | null): Dataset[] {
  if (tag === null || tag === "") return datasets;
  return datasets.filter((dataset) => dataset.tags.some((path) => path === tag || path.startsWith(`${tag}/`)));
}
