import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router";
import type { TagNode } from "../catalog-types";
import { containDialogFocus } from "../shared/dialog";
import { TagPicker } from "../shared/tag-picker";

export function DatasetTagFilter({
  tags,
  selected,
  onChange,
}: {
  tags: Record<string, TagNode>;
  selected: string[];
  onChange: (path: string) => void;
}) {
  const id = useId();
  const panel = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const [narrow, setNarrow] = useState(() => typeof window !== "undefined" && matchMedia("(max-width: 767px)").matches);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ left: 16, top: 16 });
  const [positioned, setPositioned] = useState(false);
  useEffect(() => {
    const media = matchMedia("(max-width: 767px)");
    const update = () => setNarrow(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (!narrow) return;
    if (open) dialog.current?.showModal();
    else dialog.current?.close();
  }, [open, narrow]);
  useEffect(() => {
    if (!open || narrow) return;
    const close = () => panel.current?.hidePopover();
    const onScroll = (event: Event) => {
      if (!(event.target instanceof Node) || !panel.current?.contains(event.target)) close();
    };
    window.addEventListener("resize", close);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      window.removeEventListener("resize", close);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [open, narrow]);
  const contents = (
    <>
      <TagPicker tags={tags} selected={selected} onChange={onChange} />
      <Link to="/tags" onClick={() => setOpen(false)}>
        Manage tags
      </Link>
    </>
  );
  return (
    <>
      <button
        ref={trigger}
        type="button"
        className="control-button"
        aria-expanded={open}
        popoverTarget={narrow ? undefined : id}
        onClick={narrow ? () => setOpen(true) : undefined}
      >
        Tags{selected.length ? ` (${selected.length})` : ""}
      </button>
      {narrow ? (
        <dialog
          onKeyDown={containDialogFocus}
          ref={dialog}
          className="filter-sheet"
          aria-label="Filter by tags"
          onCancel={(event) => {
            event.preventDefault();
            setOpen(false);
          }}
        >
          {contents}
          <button className="control-button" type="button" onClick={() => setOpen(false)}>
            Done
          </button>
        </dialog>
      ) : (
        <div
          ref={panel}
          id={id}
          popover="auto"
          className="catalog-filter-panel"
          data-positioned={positioned}
          style={position}
          onToggle={(event) => {
            const next = event.newState === "open";
            setOpen(next);
            if (!next) setPositioned(false);
            if (next && panel.current && trigger.current) {
              const anchor = trigger.current.getBoundingClientRect();
              const bounds = panel.current.getBoundingClientRect();
              setPosition({
                left: Math.max(16, Math.min(anchor.left, innerWidth - bounds.width - 16)),
                top: Math.max(16, Math.min(anchor.bottom + 4, innerHeight - bounds.height - 16)),
              });
              setPositioned(true);
            }
          }}
        >
          {contents}
        </div>
      )}
    </>
  );
}
