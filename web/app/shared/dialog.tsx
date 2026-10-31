import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { Button } from "./controls";

export function containDialogFocus(event: KeyboardEvent<HTMLDialogElement>) {
  if (event.key !== "Tab") return;
  const items = Array.from(
    event.currentTarget.querySelectorAll<HTMLElement>(
      'a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((element) => element.getClientRects().length > 0);
  const first = items[0];
  const last = items.at(-1);
  if (!first || !last) {
    event.preventDefault();
    event.currentTarget.focus();
    return;
  }
  if (event.shiftKey && (document.activeElement === first || !event.currentTarget.contains(document.activeElement))) {
    event.preventDefault();
    last.focus();
  } else if (
    !event.shiftKey &&
    (document.activeElement === last || !event.currentTarget.contains(document.activeElement))
  ) {
    event.preventDefault();
    first.focus();
  }
}

export function Dialog({
  open,
  title,
  description,
  pending = false,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  description?: string;
  pending?: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (!open || !dialog) return;
    const invoker = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog.showModal();
    return () => {
      dialog.close();
      if (invoker && !invoker.isConnected) {
        requestAnimationFrame(() => {
          const fallback = document.querySelector<HTMLElement>("main h1, main h2");
          if (fallback) {
            fallback.tabIndex = -1;
            fallback.focus();
          }
        });
      }
    };
  }, [open]);
  return (
    <dialog
      ref={ref}
      tabIndex={-1}
      onKeyDown={containDialogFocus}
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      onCancel={(event) => {
        event.preventDefault();
        if (!pending) onClose();
      }}
    >
      <h2 id={titleId}>{title}</h2>
      {description && <p id={descriptionId}>{description}</p>}
      {children}
    </dialog>
  );
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = "Cancel",
  pending = false,
  error,
  onClose,
  onConfirm,
  destructive = false,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel?: string;
  pending?: boolean;
  error?: string | null;
  onClose: () => void;
  onConfirm: () => void | Promise<void>;
  destructive?: boolean;
}) {
  return (
    <Dialog open={open} title={title} description={description} pending={pending} onClose={onClose}>
      {error && <p role="alert">{error}</p>}
      <Button autoFocus type="button" disabled={pending} onClick={onClose}>
        {cancelLabel}
      </Button>
      <Button
        variant={destructive ? "destructive" : "secondary"}
        type="button"
        loading={pending}
        onClick={() => void onConfirm()}
      >
        {confirmLabel}
      </Button>
    </Dialog>
  );
}
