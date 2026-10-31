import { ChevronDown, ChevronRight } from "lucide-react";
import { useId, useState } from "react";
import type { TagNode } from "../catalog-types";

/** Keep the most recently chosen path, removing redundant ancestors and descendants. */
export function toggleTagPath(selected: string[], path: string): string[] {
  if (selected.includes(path)) return selected.filter((item) => item !== path);
  return [...selected.filter((item) => !item.startsWith(`${path}/`) && !path.startsWith(`${item}/`)), path];
}

type Props = {
  tags: Record<string, TagNode>;
  selected: string[];
  onChange: (path: string) => void;
  mode?: "multiple" | "parent";
};

export function TagPicker({ tags, selected, onChange, mode = "multiple" }: Props) {
  const [query, setQuery] = useState("");
  const group = useId();
  const needle = query.trim().toLocaleLowerCase();
  function matches(node: TagNode): boolean {
    return node.path.toLocaleLowerCase().includes(needle) || Object.values(node.children).some(matches);
  }
  const roots = Object.values(tags).filter(matches);
  return (
    <div className="hierarchy-picker">
      <label htmlFor={`${group}-search`}>{mode === "parent" ? "Search parent tags" : "Search tags"}</label>
      <input
        id={`${group}-search`}
        aria-label={mode === "parent" ? "Search parent tags" : "Search tags"}
        className="tag-search"
        placeholder="Search tags…"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <div className="hierarchy-options">
        {mode === "parent" ? (
          <label className="hierarchy-root">
            <input type="radio" name={group} checked={selected.length === 0} onChange={() => onChange("")} />
            <span>
              Top level <small>No parent tag</small>
            </span>
          </label>
        ) : null}
        {roots.length ? (
          <ul aria-label={mode === "parent" ? "Parent tags" : "Available tags"}>
            {roots
              .sort((a, b) => a.path.localeCompare(b.path))
              .map((node) => (
                <TagPickerNode
                  key={node.path}
                  node={node}
                  selected={selected}
                  onChange={onChange}
                  mode={mode}
                  group={group}
                  needle={needle}
                  matches={matches}
                />
              ))}
          </ul>
        ) : (
          <p className="hint">{needle ? "No matching tags." : "No tags yet."}</p>
        )}
      </div>
    </div>
  );
}

function TagPickerNode({
  node,
  selected,
  onChange,
  mode,
  group,
  needle,
  matches,
}: Omit<Props, "tags"> & { node: TagNode; group: string; needle: string; matches: (node: TagNode) => boolean }) {
  const [expanded, setExpanded] = useState(true);
  const children = Object.values(node.children)
    .filter(matches)
    .sort((a, b) => a.path.localeCompare(b.path));
  const inherited = selected.some((path) => path.startsWith(`${node.path}/`));
  const open = needle.length > 0 || expanded;
  const name = node.path.split("/").at(-1);
  return (
    <li>
      <div className="hierarchy-row" data-selected={selected.includes(node.path) || undefined}>
        {children.length ? (
          <button
            type="button"
            className="hierarchy-toggle"
            aria-label={`${open ? "Collapse" : "Expand"} ${node.path}`}
            aria-expanded={open}
            onClick={() => setExpanded(!expanded)}
          >
            {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        ) : (
          <span className="hierarchy-spacer" />
        )}
        <label title={node.path}>
          <input
            type={mode === "parent" ? "radio" : "checkbox"}
            name={mode === "parent" ? group : undefined}
            aria-label={node.path}
            checked={selected.includes(node.path)}
            onChange={() => onChange(node.path)}
          />
          <span>{name}</span>
          {inherited && mode !== "parent" ? <small>Included through child</small> : null}
        </label>
      </div>
      {children.length && open ? (
        <ul>
          {children.map((child) => (
            <TagPickerNode
              key={child.path}
              node={child}
              selected={selected}
              onChange={onChange}
              mode={mode}
              group={group}
              needle={needle}
              matches={matches}
            />
          ))}
        </ul>
      ) : null}
    </li>
  );
}
