import { useState } from "react";
import { Button, EmptyState } from "../shared/controls";
import { ConfirmDialog } from "../shared/dialog";
import { useRevalidator } from "react-router";
import { listTrash, purgeDataset, restoreDataset, type Dataset } from "../catalog";
import type { Route } from "./+types/trash";

export async function clientLoader({ request }: Route.ClientLoaderArgs) {
  return { datasets: await listTrash(request.signal) };
}
export default function Trash({ loaderData }: Route.ComponentProps) {
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<Dataset | null>(null);
  const revalidator = useRevalidator();
  async function run(dataset: Dataset, permanent: boolean) {
    if (pending) return;
    setPending(dataset.id);
    setErrors((current) => ({ ...current, [dataset.id]: "" }));
    try {
      if (permanent) await purgeDataset(dataset.id);
      else await restoreDataset(dataset.id);
      setConfirm(null);
      revalidator.revalidate();
    } catch (cause) {
      setErrors((current) => ({
        ...current,
        [dataset.id]: cause instanceof Error ? cause.message : "The action failed.",
      }));
    } finally {
      setPending(null);
    }
  }
  return (
    <div className="page">
      <header className="topbar">
        <div className="title-row">
          <h1>Trash</h1>
          <span>{loaderData.datasets.length}</span>
        </div>
      </header>
      <div className="page-body trash-list">
        <p>
          Names remain reserved while datasets are in Trash. Restore or permanently delete a dataset to resolve a name
          conflict.
        </p>
        {loaderData.datasets.length === 0 ? (
          <EmptyState title="Trash is empty" description="Deleted datasets will appear here." />
        ) : (
          <ul>
            {loaderData.datasets.map((dataset) => (
              <li key={dataset.id}>
                <div>
                  <strong>{dataset.name}</strong>
                  <p>{dataset.rows_kept} rows kept</p>
                  {errors[dataset.id] && confirm?.id !== dataset.id ? <p role="alert">{errors[dataset.id]}</p> : null}
                </div>
                <div>
                  <Button
                    type="button"
                    loading={pending === dataset.id}
                    disabled={pending !== null}
                    onClick={() => run(dataset, false)}
                  >
                    {pending === dataset.id ? "Restoring…" : "Restore"}
                  </Button>{" "}
                  <Button
                    variant="danger"
                    type="button"
                    disabled={pending !== null}
                    onClick={() => setConfirm(dataset)}
                  >
                    Delete permanently
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
      <ConfirmDialog
        open={confirm !== null}
        title={`Delete ${confirm?.name ?? "dataset"} permanently?`}
        description={`${confirm?.rows_kept ?? 0} rows and the stored snapshot will be removed. This cannot be undone.`}
        confirmLabel="Delete permanently"
        pending={pending !== null}
        error={confirm ? errors[confirm.id] : null}
        onClose={() => setConfirm(null)}
        onConfirm={() => {
          if (confirm) return run(confirm, true);
        }}
        destructive
      />
    </div>
  );
}
