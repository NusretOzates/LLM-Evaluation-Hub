import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { Button } from "../../shared/controls";
import { api, type Output } from "./api";
import { message } from "./connections";
import { OutputEditor } from "./output-editor";
export default function DatasetOutput() {
  const { id = "" } = useParams();
  const [output, setOutput] = useState<Output | null>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [valid, setValid] = useState(true);
  useEffect(() => {
    api
      .output(id)
      .then(setOutput)
      .catch((e) => setError(message(e)));
  }, [id]);
  async function save() {
    if (!output) return;
    try {
      await api.saveOutput(id, output);
      setStatus("Output settings saved.");
    } catch (e) {
      setError(message(e));
    }
  }
  return (
    <div className="page">
      <header className="topbar">
        <Link to={`/datasets/${encodeURIComponent(id)}`}>Datasets</Link>
        <h1>Output settings</h1>
      </header>
      <div className="page-body inference-page">
        <p>These defaults apply to new runs. Existing dataset snapshots and runs are unchanged.</p>
        {error && (
          <p role="alert" className="field-error">
            {error}
          </p>
        )}
        {status && <p role="status">{status}</p>}
        {output && (
          <div className="inference-panel">
            <OutputEditor
              onValidityChange={setValid}
              value={output}
              onChange={(v) => {
                setOutput(v);
                setStatus("");
              }}
            />
            <Button disabled={!valid} variant="primary" onClick={() => void save()}>
              Save defaults
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
