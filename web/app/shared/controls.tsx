import { CircleAlert, CircleCheck, Clock3, LoaderCircle, X } from "lucide-react";
import {
  cloneElement,
  isValidElement,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactElement,
  type ReactNode,
} from "react";

export function Button({
  variant = "secondary",
  loading = false,
  disabled,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "quiet" | "danger" | "destructive";
  loading?: boolean;
}) {
  return (
    <button
      {...props}
      className={`control-button control-button-${variant} ${props.className ?? ""}`}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
    >
      {loading && <LoaderCircle aria-hidden="true" size={16} />}
      {children}
    </button>
  );
}
export function Field({
  id,
  label,
  hint,
  error,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  children: ReactElement<InputHTMLAttributes<HTMLInputElement>>;
}) {
  const describedBy = [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(" ") || undefined;
  return (
    <div className="control-field">
      <label htmlFor={id}>{label}</label>
      {isValidElement(children) &&
        cloneElement(children, { id, "aria-describedby": describedBy, "aria-invalid": !!error || undefined })}
      {hint && (
        <p id={`${id}-hint`} className="hint">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} className="field-error">
          {error}
        </p>
      )}
    </div>
  );
}
export function SearchField({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="control-field">
      <label htmlFor={id}>{label}</label>
      <div className="search-control">
        <input id={id} type="search" value={value} onChange={(event) => onChange(event.target.value)} />
        {value && (
          <button type="button" aria-label={`Clear ${label}`} onClick={() => onChange("")}>
            <X size={16} aria-hidden="true" />
          </button>
        )}
      </div>
    </div>
  );
}
export function FilterChip({
  label,
  unavailable,
  onRemove,
}: {
  label: string;
  unavailable?: boolean;
  onRemove: () => void;
}) {
  return (
    <span className="filter-token">
      <details>
        <summary>
          {label}
          {unavailable ? " (Unavailable)" : ""}
        </summary>
        <span>{label}</span>
      </details>
      <button className="token-clear" type="button" aria-label={`Remove ${label}`} onClick={onRemove}>
        <X size={16} aria-hidden="true" />
      </button>
    </span>
  );
}
export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return (
    <div className="empty-state">
      <h2>{title}</h2>
      <p>{description}</p>
      {action}
    </div>
  );
}
export function StatusLabel({ status }: { status: string }) {
  const Icon =
    status === "succeeded" || status === "completed"
      ? CircleCheck
      : status === "failed" || status === "interrupted"
        ? CircleAlert
        : status === "running" || status === "cancelling"
          ? LoaderCircle
          : Clock3;
  return (
    <span className="status-label" data-status={status}>
      <Icon
        size={14}
        aria-hidden="true"
        className={status === "running" || status === "cancelling" ? "spin" : undefined}
      />
      {status}
    </span>
  );
}
export function Skeleton({ className = "" }: { className?: string }) {
  return <div aria-hidden="true" className={`skeleton ${className}`} />;
}
