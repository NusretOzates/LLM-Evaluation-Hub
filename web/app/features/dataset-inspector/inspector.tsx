import { ChevronRight, List, PanelRight } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router";
import type { Dataset, ExamplePage, TagNode } from "../../catalog-types";
import { useShortcut, useStoredFlag } from "../../shared/browser";
import { PAGE_SIZE, selectedRow } from "./model";
import { RowIndex } from "./rows";
import { RowViewer } from "./viewer";
import { Summary, TagManager, Details } from "./metadata";

export function DatasetInspector({
  dataset,
  page,
  tags,
}: {
  dataset: Dataset;
  page: ExamplePage;
  tags: Record<string, TagNode>;
}) {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [showDetails, setShowDetails] = useStoredFlag("dataset-aside", false);
  const [showIndex, setShowIndex] = useStoredFlag("dataset-index", true);
  useShortcut("]", () => setShowDetails((value) => !value));
  useShortcut("\\", () => setShowIndex((value) => !value));
  const selected = selectedRow(page, params.get("row"));

  function go(row: number) {
    if (row < 1 || row > page.total) return;
    const offset = Math.floor((row - 1) / PAGE_SIZE) * PAGE_SIZE;
    navigate(`?offset=${offset}&row=${row}`, { replace: true, preventScrollReset: true });
  }

  return (
    <div className="page">
      <header className="topbar">
        <nav aria-label="Breadcrumb" className="crumbs">
          <Link to="/datasets">Datasets</Link>
          <ChevronRight aria-hidden="true" size={14} strokeWidth={1.75} />
          <h1>{dataset.name}</h1>
        </nav>
        <Summary dataset={dataset} />
        <button
          aria-label="Row list"
          aria-pressed={showIndex}
          className="icon-button topbar-toggle"
          onClick={() => setShowIndex((value) => !value)}
          title="Row list (\\)"
          type="button"
        >
          <List aria-hidden="true" size={15} strokeWidth={1.75} />
        </button>
        <button
          aria-label="Dataset details"
          aria-pressed={showDetails}
          className="icon-button"
          onClick={() => setShowDetails((value) => !value)}
          title="Dataset details (])"
          type="button"
        >
          <PanelRight aria-hidden="true" size={15} strokeWidth={1.75} />
        </button>
      </header>
      <div className="inspector" data-details={showDetails} data-index={showIndex}>
        {showIndex ? <RowIndex key={`${dataset.id}:${page.offset}`} go={go} page={page} selected={selected} /> : null}
        <RowViewer go={go} page={page} selected={selected} />
        {showDetails ? (
          <aside aria-label="Dataset details" className="aside">
            <TagManager dataset={dataset} tags={tags} />
            <Details dataset={dataset} />
          </aside>
        ) : null}
      </div>
    </div>
  );
}
