import { containDialogFocus } from "../../shared/dialog";
import { DatasetMenu } from "../../shared/dataset-menu";
import { ChevronRight, List, PanelRight } from "lucide-react";
import { useEffect, useRef, useState } from "react";
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
  const [narrow, setNarrow] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(max-width: 767px)").matches,
  );
  const gridRef = useRef<HTMLDivElement>(null);
  const [gridWidth, setGridWidth] = useState(Number.POSITIVE_INFINITY);
  useEffect(() => {
    const grid = gridRef.current;
    if (!grid) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setGridWidth(entry.contentRect.width);
    });
    observer.observe(grid);
    return () => observer.disconnect();
  }, []);
  const [sheet, setSheet] = useState<"examples" | "details" | null>(null);
  const examplesDialog = useRef<HTMLDialogElement>(null);
  const detailsDialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const media = matchMedia("(max-width: 767px)");
    const update = () => setNarrow(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (sheet === "examples") examplesDialog.current?.showModal();
    else examplesDialog.current?.close();
    if (sheet === "details") detailsDialog.current?.showModal();
    else detailsDialog.current?.close();
  }, [sheet]);
  const navigate = useNavigate();
  const [showDetails, setShowDetails] = useStoredFlag("dataset-aside", false);
  const [showIndex, setShowIndex] = useStoredFlag("dataset-index", true);
  const selected = selectedRow(page, params.get("row"));
  const indexOverlay = narrow || gridWidth < 704;
  const detailsOverlay = narrow || gridWidth < 1048;
  useShortcut("]", () =>
    detailsOverlay ? setSheet((value) => (value === "details" ? null : "details")) : setShowDetails((value) => !value),
  );
  useShortcut("\\", () =>
    indexOverlay ? setSheet((value) => (value === "examples" ? null : "examples")) : setShowIndex((value) => !value),
  );

  function go(row: number) {
    if (row < 1 || row > page.total) return;
    const offset = Math.floor((row - 1) / PAGE_SIZE) * PAGE_SIZE;
    navigate(`?offset=${offset}&row=${row}`, { replace: true, preventScrollReset: true });
    if (indexOverlay) {
      setSheet(null);
      requestAnimationFrame(() => document.getElementById("row-title")?.focus());
    }
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
        <DatasetMenu dataset={dataset} />
        <button
          aria-label="Row list"
          aria-pressed={indexOverlay ? sheet === "examples" : showIndex}
          className="icon-button topbar-toggle"
          onClick={() => (indexOverlay ? setSheet("examples") : setShowIndex((value) => !value))}
          title="Row list (\\)"
          type="button"
        >
          <List aria-hidden="true" size={15} strokeWidth={1.75} />
        </button>
        <button
          aria-label="Dataset details"
          aria-pressed={detailsOverlay ? sheet === "details" : showDetails}
          className="icon-button"
          onClick={() => (detailsOverlay ? setSheet("details") : setShowDetails((value) => !value))}
          title="Dataset details (])"
          type="button"
        >
          <PanelRight aria-hidden="true" size={15} strokeWidth={1.75} />
        </button>
      </header>
      <div
        ref={gridRef}
        className="inspector"
        data-details={showDetails && !detailsOverlay}
        data-index={showIndex && !indexOverlay}
        data-compact={gridWidth < 1048}
      >
        {showIndex && !indexOverlay ? (
          <RowIndex key={`${dataset.id}:${page.offset}`} go={go} page={page} selected={selected} />
        ) : null}
        <RowViewer go={go} page={page} selected={selected} />
        {showDetails && !detailsOverlay ? (
          <aside aria-label="Dataset details" className="aside">
            <TagManager dataset={dataset} tags={tags} />
            <Details dataset={dataset} />
          </aside>
        ) : null}
      </div>
      {indexOverlay ? (
        <dialog
          onKeyDown={containDialogFocus}
          aria-label="Examples"
          className="inspector-sheet"
          ref={examplesDialog}
          onCancel={(event) => {
            event.preventDefault();
            setSheet(null);
          }}
        >
          <button type="button" onClick={() => setSheet(null)}>
            Close examples
          </button>
          {sheet === "examples" && (
            <RowIndex key={`${dataset.id}:${page.offset}`} go={go} page={page} selected={selected} />
          )}
        </dialog>
      ) : null}
      {detailsOverlay ? (
        <dialog
          onKeyDown={containDialogFocus}
          aria-label="Dataset details"
          className="inspector-sheet"
          ref={detailsDialog}
          onCancel={(event) => {
            event.preventDefault();
            setSheet(null);
          }}
        >
          <button type="button" onClick={() => setSheet(null)}>
            Close details
          </button>
          {sheet === "details" && (
            <aside aria-label="Dataset details" className="aside">
              <TagManager dataset={dataset} tags={tags} />
              <Details dataset={dataset} />
            </aside>
          )}
        </dialog>
      ) : null}
    </div>
  );
}
