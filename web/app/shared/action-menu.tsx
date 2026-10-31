import { MoreHorizontal } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";

export function ActionMenu({ label, children }: { label: string; children: ReactNode }) {
  const id = useId();
  const panel = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ top: 8, left: 8 });
  const [positioned, setPositioned] = useState(false);
  useEffect(() => {
    if (!open) return;
    const close = () => panel.current?.hidePopover();
    window.addEventListener("resize", close);
    const onScroll = (event: Event) => {
      if (!(event.target instanceof Node) || !panel.current?.contains(event.target)) close();
    };
    window.addEventListener("scroll", onScroll, true);
    return () => {
      window.removeEventListener("resize", close);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [open]);
  return (
    <>
      <button
        ref={trigger}
        type="button"
        className="icon-button action-menu-trigger"
        aria-label={label}
        aria-expanded={open}
        popoverTarget={id}
      >
        <MoreHorizontal size={16} aria-hidden="true" />
      </button>
      <div
        role="menu"
        aria-label={label}
        ref={panel}
        id={id}
        popover="auto"
        className="action-menu-panel"
        data-positioned={positioned}
        style={position}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            const buttons = Array.from(
              event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"),
            );
            const current =
              document.activeElement instanceof HTMLButtonElement ? buttons.indexOf(document.activeElement) : -1;
            buttons[
              (current + (event.key === "ArrowDown" ? 1 : buttons.length - 1) + buttons.length) % buttons.length
            ]?.focus();
          } else if (event.key === "Tab") panel.current?.hidePopover();
        }}
        onToggle={(event) => {
          const isOpen = event.newState === "open";
          setOpen(isOpen);
          if (!isOpen) setPositioned(false);
          if (isOpen && panel.current && trigger.current) {
            const anchor = trigger.current.getBoundingClientRect();
            const bounds = panel.current.getBoundingClientRect();
            const top =
              anchor.bottom + bounds.height + 8 <= window.innerHeight
                ? anchor.bottom + 4
                : anchor.top - bounds.height - 4;
            setPosition({
              top: Math.max(8, Math.min(top, window.innerHeight - bounds.height - 8)),
              left: Math.max(8, Math.min(anchor.right - bounds.width, window.innerWidth - bounds.width - 8)),
            });
            setPositioned(true);
            requestAnimationFrame(() => panel.current?.querySelector<HTMLButtonElement>("button")?.focus());
          }
        }}
      >
        {children}
      </div>
    </>
  );
}
