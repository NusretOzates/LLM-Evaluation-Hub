import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Plus } from "lucide-react";
import { Dialog } from "../shared/dialog";
import { ActionMenu } from "../shared/action-menu";
import { Button, Field, SearchField } from "../shared/controls";
import { Link, useRevalidator, useRouteLoaderData, useSearchParams } from "react-router";
import { createTags, deleteTag, flattenTags, tagForest, tagImpact, type TagNode } from "../catalog";
import type { clientLoader as rootLoader } from "../root";
import { subtreeCounts } from "../shared/catalog-view";
import { TagPicker } from "../shared/tag-picker";

export default function TagsPage() {
  const catalog = useRouteLoaderData<typeof rootLoader>("root");
  const [params, setParams] = useSearchParams();
  const revalidator = useRevalidator();
  const detailHeading = useRef<HTMLHeadingElement>(null);
  const pageHeading = useRef<HTMLHeadingElement>(null);
  const focusTarget = useRef<"detail" | "row" | "heading" | null>(null);
  const [creation, setCreation] = useState<{ name: string; parent: string } | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletion, setDeletion] = useState<{ path: string; promote: boolean; paths: string[]; count: number } | null>(
    null,
  );
  const selected = params.get("selected") ?? "";
  useEffect(() => {
    if (focusTarget.current === "detail") detailHeading.current?.focus();
    if (focusTarget.current === "heading") (detailHeading.current ?? pageHeading.current)?.focus();
    if (focusTarget.current === "row")
      Array.from(document.querySelectorAll<HTMLButtonElement>("[data-tag-path]"))
        .find((button) => button.dataset.tagPath === selected)
        ?.focus();
    focusTarget.current = null;
  }, [selected]);
  if (!catalog) return null;
  const nodes = flattenTags(catalog.tags);
  const query = params.get("q") ?? "";
  const current = nodes.find((node) => node.path === selected);
  const counts = subtreeCounts(catalog.datasets);
  const direct = catalog.datasets.filter((dataset) => dataset.tags.includes(selected)).length;
  function setParam(key: string, value: string, replace = false) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace });
  }
  async function create() {
    if (!creation || pending) return;
    const name = creation.name.trim();
    if (!name || name.includes("/")) {
      setError("A tag name cannot be empty or contain /.");
      return;
    }
    setPending(true);
    setError(null);
    try {
      await createTags(tagForest(creation.parent, name));
      await revalidator.revalidate();
      const next = new URLSearchParams(params);
      next.delete("q");
      next.set("selected", creation.parent ? `${creation.parent}/${name}` : name);
      focusTarget.current = "row";
      setParams(next);
      setCreation(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not create tag.");
    } finally {
      setPending(false);
    }
  }
  async function requestDelete(node: TagNode, promote: boolean) {
    setError(null);
    try {
      const impact = await tagImpact(node.path);
      setDeletion({ path: node.path, promote, paths: impact.paths, count: impact.datasetCount });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load deletion impact.");
    }
  }
  async function remove() {
    if (!deletion || pending) return;
    setPending(true);
    setError(null);
    try {
      await deleteTag(deletion.path, deletion.promote);
      await revalidator.revalidate();
      const parent = deletion.path.split("/").slice(0, -1).join("/");
      focusTarget.current = "heading";
      setParam("selected", parent);
      setDeletion(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not delete tag.");
    } finally {
      setPending(false);
    }
  }
  const needle = query.trim().toLocaleLowerCase();
  const visible = nodes.filter(
    (node) =>
      !needle ||
      node.path.toLocaleLowerCase().includes(needle) ||
      nodes.some((child) => child.path.startsWith(`${node.path}/`) && child.path.toLocaleLowerCase().includes(needle)),
  );
  function select(path: string) {
    const tree = document.querySelector(".tags-tree");
    const detail = document.querySelector(".tags-detail");
    if (tree && detail && detail.getBoundingClientRect().top > tree.getBoundingClientRect().top)
      focusTarget.current = "detail";
    setParam("selected", path);
  }
  function addChild(path: string) {
    setError(null);
    setCreation({ name: "", parent: path });
  }
  return (
    <div className="page">
      <header className="topbar">
        <div className="title-row">
          <h1 ref={pageHeading} tabIndex={-1}>
            Tags
          </h1>
          <span>{nodes.length}</span>
        </div>
        <div className="topbar-actions">
          <button
            className="button-ghost"
            type="button"
            onClick={() => {
              setError(null);
              setCreation({ name: "", parent: "" });
            }}
          >
            New tag
          </button>
        </div>
      </header>
      <div className="tags-content">
        <SearchField
          id="tag-tree-search"
          label="Search tags"
          value={query}
          onChange={(value) => setParam("q", value, true)}
        />
        <div className="tags-workspace">
          <div className="tags-tree">
            {visible.length ? (
              <TagTree
                nodes={catalog.tags}
                selected={selected}
                needle={needle}
                counts={counts}
                onSelect={select}
                onCreate={addChild}
              />
            ) : nodes.length ? (
              <div>
                <p>No matching tags.</p>
                <Button type="button" onClick={() => setParam("q", "", true)}>
                  Clear search
                </Button>
              </div>
            ) : (
              <div>
                <p>Create your first tag.</p>
                <Button
                  type="button"
                  onClick={() => {
                    setError(null);
                    setCreation({ name: "", parent: "" });
                  }}
                >
                  New tag
                </Button>
              </div>
            )}
          </div>
          <section className="tags-detail">
            {current ? (
              <>
                <p>{current.path}</p>
                <h2 ref={detailHeading} tabIndex={-1}>
                  {current.path.split("/").at(-1)}
                </h2>
                <p>Directly tagged: {direct}</p>
                <p>In this branch: {counts.get(current.path) ?? 0}</p>
                <div className="tags-detail-actions">
                  <Button type="button" onClick={() => addChild(current.path)}>
                    Add sub-tag
                  </Button>
                  <Link className="button-ghost" to={`/datasets?tag=${encodeURIComponent(current.path)}`}>
                    View datasets
                  </Link>
                  <ActionMenu label={`Actions for tag ${current.path}`}>
                    <button role="menuitem" type="button" onClick={() => requestDelete(current, false)}>
                      Delete tag and sub-tags
                    </button>
                    {Object.keys(current.children).length ? (
                      <button role="menuitem" type="button" onClick={() => requestDelete(current, true)}>
                        Delete grouping and keep sub-tags
                      </button>
                    ) : null}
                  </ActionMenu>
                </div>
              </>
            ) : selected ? (
              <>
                <h2>This tag no longer exists</h2>
                <button type="button" onClick={() => setParam("selected", "")}>
                  Clear selection
                </button>
              </>
            ) : (
              <h2>Select a tag to manage it</h2>
            )}
            {error && !creation && !deletion ? <p role="alert">{error}</p> : null}
          </section>
        </div>
      </div>
      <Dialog
        open={creation !== null}
        title={creation?.parent ? "Add sub-tag" : "New tag"}
        pending={pending}
        onClose={() => setCreation(null)}
      >
        <Field id="new-tag-name" label="Tag name" error={error ?? undefined}>
          <input
            autoFocus
            value={creation?.name ?? ""}
            onChange={(event) => setCreation((value) => value && { ...value, name: event.target.value })}
          />
        </Field>
        <p>Parent: {creation?.parent || "Top level"}</p>
        <details>
          <summary>Change parent</summary>
          <TagPicker
            tags={catalog.tags}
            selected={creation?.parent ? [creation.parent] : []}
            mode="parent"
            onChange={(parent) => setCreation((value) => value && { ...value, parent })}
          />
        </details>
        <Button type="button" disabled={pending} onClick={() => setCreation(null)}>
          Cancel
        </Button>
        <Button variant="primary" type="button" loading={pending} onClick={create}>
          {pending ? "Creating…" : "Create tag"}
        </Button>
      </Dialog>
      <Dialog
        open={deletion !== null}
        title={`Delete ${deletion?.path ?? "tag"}?`}
        pending={pending}
        onClose={() => setDeletion(null)}
      >
        <p>
          {Math.max(0, (deletion?.paths.length ?? 1) - 1)} sub-tags and {deletion?.count} datasets are affected. Dataset
          records remain.
        </p>
        <p>
          {deletion?.promote
            ? "Children move to this tag's parent. Direct assignments to this grouping are removed."
            : "The tag and its sub-tags will be removed from datasets."}
        </p>
        {error && <p role="alert">{error}</p>}
        <Button type="button" autoFocus disabled={pending} onClick={() => setDeletion(null)}>
          Cancel
        </Button>
        <Button variant="destructive" type="button" loading={pending} onClick={remove}>
          Delete
        </Button>
      </Dialog>
    </div>
  );
}

function TagTree({
  nodes,
  selected,
  needle,
  counts,
  onSelect,
  onCreate,
}: {
  nodes: Record<string, TagNode>;
  selected: string;
  needle: string;
  counts: Map<string, number>;
  onSelect: (path: string) => void;
  onCreate: (path: string) => void;
}) {
  function matches(node: TagNode): boolean {
    return node.path.toLocaleLowerCase().includes(needle) || Object.values(node.children).some(matches);
  }
  return (
    <ul className="tags-tree-list">
      {Object.values(nodes)
        .filter(matches)
        .sort((a, b) => a.path.localeCompare(b.path))
        .map((node) => (
          <TagTreeNode
            key={node.path}
            node={node}
            selected={selected}
            needle={needle}
            counts={counts}
            onSelect={onSelect}
            onCreate={onCreate}
          />
        ))}
    </ul>
  );
}
function TagTreeNode({
  node,
  selected,
  needle,
  counts,
  onSelect,
  onCreate,
}: {
  node: TagNode;
  selected: string;
  needle: string;
  counts: Map<string, number>;
  onSelect: (path: string) => void;
  onCreate: (path: string) => void;
}) {
  const [expanded, setExpanded] = useState(true);
  const hasChildren = Object.keys(node.children).length > 0;
  const open = !!needle || expanded;
  return (
    <li>
      <div className="tags-row">
        {hasChildren ? (
          <button
            className="tags-expand"
            type="button"
            aria-label={`${open ? "Collapse" : "Expand"} ${node.path}`}
            aria-expanded={open}
            onClick={() => setExpanded(!expanded)}
          >
            {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </button>
        ) : (
          <span className="tags-expand" />
        )}
        <button
          className="tags-select"
          data-tag-path={node.path}
          type="button"
          onClick={() => onSelect(node.path)}
          aria-current={selected === node.path ? "true" : undefined}
        >
          {node.path.split("/").at(-1)}
        </button>
        <span>{counts.get(node.path) ?? 0}</span>
        <button
          className="tags-add"
          type="button"
          aria-label={`Add sub-tag to ${node.path}`}
          onClick={() => onCreate(node.path)}
        >
          <Plus size={16} />
        </button>
      </div>
      {hasChildren && open && (
        <TagTree
          nodes={node.children}
          selected={selected}
          needle={needle}
          counts={counts}
          onSelect={onSelect}
          onCreate={onCreate}
        />
      )}
    </li>
  );
}
