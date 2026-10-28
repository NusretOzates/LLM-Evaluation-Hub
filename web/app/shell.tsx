import { Database, FilePlus2, PanelLeftClose, PanelLeftOpen, Plus, Tags } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, NavLink, Outlet, useFetcher, useLocation, useNavigation, useSearchParams } from "react-router";

import type { Dataset, TagNode } from "./catalog";
import { useShortcut, useStoredFlag } from "./shared/browser";
import { subtreeCounts } from "./shared/catalog-view";

export type TagActionData = { error: string } | { created: true };

export function Shell({ datasets, tags }: { datasets: Dataset[]; tags: Record<string, TagNode> }) {
  const navigation = useNavigation();
  const location = useLocation();
  const [params] = useSearchParams();
  const inspecting = /^\/datasets\/.+/.test(location.pathname);
  const [listCollapsed, setListCollapsed] = useStoredFlag("sidebar-collapsed", false);
  const [detailCollapsed, setDetailCollapsed] = useStoredFlag("sidebar-collapsed-detail", true);
  const collapsed = inspecting ? detailCollapsed : listCollapsed;
  const setCollapsed = inspecting ? setDetailCollapsed : setListCollapsed;
  useShortcut("[", () => setCollapsed((value) => !value));
  const selected = location.pathname === "/datasets" ? params.get("tag") : null;
  return (
    <div className="shell" data-sidebar={collapsed ? "collapsed" : "open"}>
      <aside aria-label="Sidebar" className="sidebar">
        <div className="brand">
          {collapsed ? null : <span>Evaluation hub</span>}
          <button
            aria-expanded={!collapsed}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="icon-button"
            onClick={() => setCollapsed((value) => !value)}
            title={collapsed ? "Expand sidebar ([)" : "Collapse sidebar ([)"}
            type="button"
          >
            {collapsed ? (
              <PanelLeftOpen aria-hidden="true" size={15} strokeWidth={1.75} />
            ) : (
              <PanelLeftClose aria-hidden="true" size={15} strokeWidth={1.75} />
            )}
          </button>
        </div>
        <nav aria-label="Sections" className="nav">
          <NavLink className="nav-link" title={collapsed ? "Datasets" : undefined} to="/datasets">
            <Database aria-hidden="true" size={15} strokeWidth={1.75} />
            <span className="nav-label">Datasets</span>
            <span className="nav-count mono">{datasets.length}</span>
          </NavLink>{" "}
          <NavLink className="nav-link" title={collapsed ? "Dataset imports" : undefined} to="/dataset-imports">
            <FilePlus2 aria-hidden="true" size={15} strokeWidth={1.75} />
            <span className="nav-label">Imports</span>
          </NavLink>
        </nav>
        {collapsed ? (
          <div className="rail-tags">
            <button
              aria-label={selected === null ? "Show tags" : `Show tags, filtered by ${selected}`}
              className="icon-button"
              data-active={selected !== null}
              onClick={() => setCollapsed(false)}
              title="Show tags"
              type="button"
            >
              <Tags aria-hidden="true" size={15} strokeWidth={1.75} />
            </button>
          </div>
        ) : (
          <TagSection datasets={datasets} selected={selected} tags={tags} />
        )}
      </aside>
      <main className="workspace" data-loading={navigation.state === "loading"}>
        <Outlet />
      </main>
    </div>
  );
}

function TagSection({
  datasets,
  selected,
  tags,
}: {
  datasets: Dataset[];
  selected: string | null;
  tags: Record<string, TagNode>;
}) {
  const fetcher = useFetcher<TagActionData>();
  const [adding, setAdding] = useState(false);
  const created = fetcher.data !== undefined && "created" in fetcher.data;
  const error = fetcher.data !== undefined && "error" in fetcher.data ? fetcher.data.error : null;
  const parentName = selected?.split("/").at(-1) ?? null;
  const counts = useMemo(() => subtreeCounts(datasets), [datasets]);

  useEffect(() => {
    if (created && fetcher.state === "idle") setAdding(false);
  }, [created, fetcher.state]);

  return (
    <section aria-labelledby="tags-heading" className="tag-section">
      <div className="section-head">
        <h2 id="tags-heading">Tags</h2>
        <button
          aria-expanded={adding}
          aria-label="New tag"
          className="icon-button"
          onClick={() => setAdding((value) => !value)}
          type="button"
        >
          <Plus aria-hidden="true" size={14} strokeWidth={1.75} />
        </button>
      </div>
      {adding ? (
        <fetcher.Form action="/datasets" className="tag-new" method="post">
          <input name="parent" type="hidden" value={selected ?? ""} />
          <input
            aria-describedby="tag-new-hint"
            aria-label="Tag name"
            autoComplete="off"
            autoFocus
            name="name"
            onKeyDown={(event) => {
              if (event.key === "Escape") setAdding(false);
            }}
            placeholder="Tag name"
            required
          />
          <p className="hint" id="tag-new-hint">
            {parentName === null ? "Adds a top-level tag." : `Adds a tag inside ${parentName}.`}
          </p>
          {error === null ? null : (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
        </fetcher.Form>
      ) : null}
      <div className="tag-scroll">
        {Object.keys(tags).length === 0 ? (
          <p className="hint tag-empty">Tags group datasets. Use + to add the first one.</p>
        ) : (
          <TagTree counts={counts} nodes={tags} selected={selected} />
        )}
      </div>
    </section>
  );
}

function TagTree({
  counts,
  nodes,
  selected,
}: {
  counts: Map<string, number>;
  nodes: Record<string, TagNode>;
  selected: string | null;
}) {
  const names = Object.keys(nodes).sort((a, b) => a.localeCompare(b));
  return (
    <ul className="tag-tree">
      {names.map((name) => {
        const node = nodes[name];
        if (node === undefined) return null;
        const current = node.path === selected;
        return (
          <li key={node.path}>
            <Link
              aria-current={current ? "true" : undefined}
              className="tag-link"
              to={current ? "/datasets" : `/datasets?tag=${encodeURIComponent(node.path)}`}
            >
              <span className="tag-name">{name}</span>
              <span className="tag-count mono">{counts.get(node.path) ?? 0}</span>
            </Link>
            {Object.keys(node.children).length > 0 ? (
              <TagTree counts={counts} nodes={node.children} selected={selected} />
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

export function CatalogAlert({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "The catalog could not be loaded.";
  return (
    <p className="alert" role="alert">
      {message}
    </p>
  );
}

export function ShellSkeleton() {
  return (
    <div className="shell" aria-busy="true">
      <aside className="sidebar">
        <div className="brand">
          <span>Evaluation hub</span>
        </div>
        <div className="skeleton-stack">
          {Array.from({ length: 5 }, (_, index) => (
            <div className="skeleton skeleton-nav" key={index} />
          ))}
        </div>
      </aside>
      <main className="workspace">
        <header className="topbar">
          <h1>Datasets</h1>
        </header>
        <div className="skeleton-stack skeleton-table">
          {Array.from({ length: 8 }, (_, index) => (
            <div className="skeleton skeleton-row" key={index} />
          ))}
        </div>
      </main>
    </div>
  );
}
