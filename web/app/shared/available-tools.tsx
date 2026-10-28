import { Copy } from "lucide-react";
import { useId, useState } from "react";
import type { ToolDefinition } from "../catalog-types";

export function AvailableTools({ tools, className = "" }: { tools: ToolDefinition[]; className?: string }) {
  const headingId = useId();
  const [json, setJson] = useState(false);
  const [copy, setCopy] = useState<"idle" | "copied" | "failed">("idle");

  return (
    <section aria-labelledby={headingId} className={`available-tools ${className}`}>
      <div className="tools-heading">
        <h3 id={headingId}>
          Available tools <span className="mono">{tools.length}</span>
        </h3>
        <div className="viewer-actions">
          <button
            aria-pressed={json}
            className="button-ghost button-small"
            onClick={() => setJson((value) => !value)}
            type="button"
          >
            Tools JSON
          </button>
          <button
            className="button-ghost button-small"
            onClick={() => {
              void Promise.resolve()
                .then(() => navigator.clipboard.writeText(JSON.stringify(tools, null, 2)))
                .then(
                  () => setCopy("copied"),
                  () => setCopy("failed"),
                );
            }}
            type="button"
          >
            <Copy aria-hidden="true" size={13} />
            {copy === "copied" ? "Tools copied" : copy === "failed" ? "Copy tools failed" : "Copy tools"}
          </button>
        </div>
      </div>
      {copy === "failed" ? (
        <p className="hint" role="status">
          Clipboard unavailable. Use Tools JSON to select the definitions.
        </p>
      ) : null}
      {tools.length === 0 ? (
        <p className="hint">No tools</p>
      ) : json ? (
        <pre className="raw mono">{JSON.stringify(tools, null, 2)}</pre>
      ) : (
        tools.map((tool) => (
          <details key={tool.function.name}>
            <summary>
              <code className="mono">{tool.function.name}</code>
              {tool.function.strict === undefined ? null : (
                <span className="muted"> · strict: {String(tool.function.strict)}</span>
              )}
            </summary>
            {tool.function.description ? <p>{tool.function.description}</p> : null}
            <pre className="raw mono">{JSON.stringify(tool.function.parameters, null, 2)}</pre>
          </details>
        ))
      )}
    </section>
  );
}
