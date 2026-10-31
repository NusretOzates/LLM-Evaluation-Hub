import { useCallback, useEffect, useState } from "react";
import { Button } from "../../shared/controls";
import { api, newProfile, type Profile } from "./api";

export default function Connections() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [editing, setEditing] = useState<Profile | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    try {
      setProfiles(await api.profiles());
    } catch (e) {
      setError(message(e));
    }
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!editing) return;
    setBusy(true);
    setError("");
    try {
      await api.saveProfile(editing);
      setEditing(null);
      await refresh();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  async function remove(p: Profile) {
    if (!window.confirm(`Delete connection “${p.name}”?`)) return;
    setBusy(true);
    try {
      await api.deleteProfile(p.id);
      await refresh();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page">
      <header className="topbar">
        <h1>Connections</h1>
        <Button variant="primary" onClick={() => setEditing({ ...newProfile })}>
          New connection
        </Button>
      </header>
      <div className="page-body inference-page">
        <p className="muted">
          Save endpoint settings for inference. API keys stay on the server; enter only an environment variable name.
        </p>
        {error && (
          <p role="alert" className="field-error">
            {error}
          </p>
        )}
        {profiles.length === 0 && !editing ? (
          <p>No connections yet.</p>
        ) : (
          <div className="inference-list">
            {profiles.map((p) => (
              <article className="inference-card" key={p.id}>
                <div>
                  <h2>{p.name}</h2>
                  <p className="mono">
                    {p.model} · {p.base_url}
                  </p>
                  <p className="muted">
                    Reasoning: {p.reasoning_mode} {p.api_key_env ? `· Key: ${p.api_key_env}` : "· No key reference"}
                  </p>
                </div>
                <div className="inference-actions">
                  <Button onClick={() => setEditing({ ...p })}>Edit</Button>
                  <Button variant="danger" disabled={busy} onClick={() => void remove(p)}>
                    Delete
                  </Button>
                </div>
              </article>
            ))}
          </div>
        )}
        {editing && (
          <form className="inference-panel" onSubmit={(e) => void save(e)}>
            <h2>{editing.id ? "Edit connection" : "New connection"}</h2>
            <div className="inference-grid">
              <label>
                Name
                <input
                  required
                  value={editing.name}
                  onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                />
              </label>
              <label>
                Base URL
                <input
                  required
                  type="url"
                  value={editing.base_url}
                  onChange={(e) => setEditing({ ...editing, base_url: e.target.value })}
                  placeholder="https://example.com/v1"
                />
              </label>
              <label>
                Model
                <input
                  required
                  value={editing.model}
                  onChange={(e) => setEditing({ ...editing, model: e.target.value })}
                />
              </label>
              <label>
                API key environment variable
                <input
                  value={editing.api_key_env ?? ""}
                  onChange={(e) => setEditing({ ...editing, api_key_env: e.target.value || null })}
                  placeholder="OPTIONAL_API_KEY"
                />
              </label>
              <label>
                Maximum token field
                <select
                  value={editing.max_tokens_field}
                  onChange={(e) =>
                    setEditing({ ...editing, max_tokens_field: e.target.value as Profile["max_tokens_field"] })
                  }
                >
                  <option value="max_completion_tokens">max_completion_tokens</option>
                  <option value="max_tokens">max_tokens</option>
                </select>
              </label>
              <label>
                Reasoning controls
                <select
                  value={editing.reasoning_mode}
                  onChange={(e) =>
                    setEditing({ ...editing, reasoning_mode: e.target.value as Profile["reasoning_mode"] })
                  }
                >
                  <option value="effort">Effort levels</option>
                  <option value="thinking">Thinking on/off</option>
                </select>
              </label>
              {editing.reasoning_mode === "effort" && (
                <>
                  <label>
                    Effort values (comma-separated)
                    <input
                      value={editing.effort_levels.join(", ")}
                      onChange={(e) =>
                        setEditing({ ...editing, effort_levels: e.target.value.split(",").map((x) => x.trim()) })
                      }
                    />
                  </label>
                  <label>
                    Effort request path
                    <input
                      required
                      value={editing.effort_path}
                      onChange={(e) => setEditing({ ...editing, effort_path: e.target.value })}
                    />
                  </label>
                </>
              )}
              {editing.reasoning_mode === "thinking" && (
                <label>
                  Thinking request path
                  <input
                    required
                    value={editing.thinking_path}
                    onChange={(e) => setEditing({ ...editing, thinking_path: e.target.value })}
                  />
                </label>
              )}
            </div>
            <div className="inference-actions">
              <Button variant="primary" loading={busy} type="submit">
                Save connection
              </Button>
              <Button type="button" onClick={() => setEditing(null)}>
                Cancel
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
export function message(e: unknown) {
  return e instanceof Error ? e.message : "Something went wrong.";
}
