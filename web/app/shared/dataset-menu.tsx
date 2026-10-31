import { ActionMenu } from "./action-menu";
import { ConfirmDialog } from "./dialog";
import { useState } from "react";
import { useNavigate, useRevalidator } from "react-router";
import { trashDataset, type Dataset } from "../catalog";

export function DatasetMenu({ dataset }: { dataset: Dataset }) {
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const navigate = useNavigate();
  const revalidator = useRevalidator();
  async function move() {
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      await trashDataset(dataset.id);
      setOpen(false);
      await navigate("/datasets");
      await revalidator.revalidate();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not move dataset to Trash.");
    } finally {
      setPending(false);
    }
  }
  return (
    <>
      <ActionMenu label={`Actions for ${dataset.name}`}>
        <button type="button" role="menuitem" className="action-menu-danger" onClick={() => setOpen(true)}>
          Move to Trash
        </button>
      </ActionMenu>
      <ConfirmDialog
        open={open}
        title={`Move ${dataset.name} to Trash?`}
        description={`${dataset.rows_kept} rows will be moved. You can restore the dataset later.`}
        confirmLabel="Move to Trash"
        pending={pending}
        error={error}
        onClose={() => setOpen(false)}
        onConfirm={move}
      />
    </>
  );
}
