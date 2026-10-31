import { Check, ChevronDown, ChevronUp, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import type { ExamplePage, Message } from "../../catalog-types";
import { AvailableTools } from "../../shared/available-tools";
import { useShortcut } from "../../shared/browser";
import { formatCount } from "../../shared/format";
import { callText, isJsonText, messageText, formatValue } from "./model";

export function RowViewer({
  go,
  page,
  selected,
}: {
  go: (row: number) => void;
  page: ExamplePage;
  selected: number | null;
}) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const [raw, setRaw] = useState(false);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const example = selected === null ? undefined : page.examples[selected - page.offset - 1];

  useShortcut("j", () => {
    if (selected !== null) go(selected + 1);
  });
  useShortcut("k", () => {
    if (selected !== null) go(selected - 1);
  });

  // biome-ignore lint/correctness/useExhaustiveDependencies: A row change resets scroll and transient copy feedback.
  useEffect(() => {
    bodyRef.current?.scrollTo({ top: 0 });
    setCopyState("idle");
  }, [selected]);

  if (example === undefined || selected === null) {
    return (
      <section aria-label="Row" className="viewer">
        <div className="viewer-empty">
          {page.total === 0 ? (
            <p>This dataset has no stored rows.</p>
          ) : (
            <p>
              This page is past the last row. <Link to="?offset=0">Go to the first row.</Link>
            </p>
          )}
        </div>
      </section>
    );
  }

  const segments = Object.entries(example.segments);
  const extras = Object.entries(example.extras);
  const tools = example.tools ?? [];
  return (
    <section aria-labelledby="row-title" className="viewer">
      <header className="viewer-bar">
        <h2 id="row-title" tabIndex={-1}>
          Example <span className="mono">{formatCount(selected)}</span>
          <span className="muted"> of {formatCount(page.total)}</span>
        </h2>
        <div className="viewer-actions">
          <fieldset className="view-mode" aria-label="Example display">
            <button
              type="button"
              className="button-ghost button-small"
              aria-pressed={!raw}
              onClick={() => setRaw(false)}
            >
              Rendered
            </button>
            <button type="button" className="button-ghost button-small" aria-pressed={raw} onClick={() => setRaw(true)}>
              JSON
            </button>
          </fieldset>
          <button
            className="button-ghost button-small"
            onClick={() => {
              void Promise.resolve()
                .then(() => navigator.clipboard.writeText(JSON.stringify(example, null, 2)))
                .then(
                  () => setCopyState("copied"),
                  () => setCopyState("failed"),
                );
            }}
            type="button"
          >
            {copyState === "copied" ? (
              <Check aria-hidden="true" size={13} strokeWidth={2} />
            ) : (
              <Copy aria-hidden="true" size={13} strokeWidth={1.75} />
            )}
            {copyState === "copied" ? "Copied" : copyState === "failed" ? "Copy failed" : "Copy"}
          </button>
          <span className="divider" />
          <button
            aria-label="Previous row"
            className="icon-button"
            disabled={selected <= 1}
            onClick={() => go(selected - 1)}
            title="Previous row (k)"
            type="button"
          >
            <ChevronUp aria-hidden="true" size={15} strokeWidth={1.75} />
          </button>
          <button
            aria-label="Next row"
            className="icon-button"
            disabled={selected >= page.total}
            onClick={() => go(selected + 1)}
            title="Next row (j)"
            type="button"
          >
            <ChevronDown aria-hidden="true" size={15} strokeWidth={1.75} />
          </button>
          <span className="sr-only" role="status">
            {copyState === "failed" ? "Clipboard unavailable. Use JSON view to select the text." : ""}
          </span>
        </div>
      </header>
      {segments.length === 0 ? null : (
        <dl className="segments">
          {segments.map(([key, value]) => (
            <div key={key}>
              <dt>{key}</dt>
              <dd className="mono">{value}</dd>
            </div>
          ))}
        </dl>
      )}
      <div className="viewer-body" ref={bodyRef}>
        {raw ? (
          <pre className="raw mono">{JSON.stringify(example, null, 2)}</pre>
        ) : (
          <>
            <article aria-labelledby="conversation-heading" className="example">
              <h3 id="conversation-heading">Conversation</h3>
              {example.conversation.map((message, turn) => (
                <MessageView key={`${message.role}-${turn}`} message={message} />
              ))}
            </article>
            {example.expected_output === null || example.expected_output === undefined ? null : (
              <section className="expected" aria-labelledby="expected-heading">
                <h3 id="expected-heading">Expected output</h3>
                {typeof example.expected_output === "string" ? (
                  <p>{example.expected_output}</p>
                ) : (
                  <pre className="mono">{formatValue(example.expected_output)}</pre>
                )}
              </section>
            )}
            {extras.length === 0 ? null : (
              <section aria-labelledby="extras-heading" className="extras-card">
                <h3 id="extras-heading">Extras</h3>
                <dl>
                  {extras.map(([key, value]) => (
                    <div key={key}>
                      <dt className="mono">{key}</dt>
                      <dd>
                        {typeof value === "string" ? <p>{value}</p> : <pre className="mono">{formatValue(value)}</pre>}
                      </dd>
                    </div>
                  ))}
                </dl>
              </section>
            )}
            <AvailableTools className="inspector-tools" key={selected} tools={tools} />
          </>
        )}
      </div>
    </section>
  );
}

function MessageView({ message }: { message: Message }) {
  const text = typeof message.content === "string" ? message.content : messageText(message.content);
  const toolCalls =
    message.role === "assistant" && message.tool_calls && message.tool_calls.length > 0 ? message.tool_calls : null;
  const structured = message.role === "tool" && text !== null && isJsonText(text);
  if (message.role === "system" && text === null && toolCalls === null) return null;
  if (message.role === "system" && text !== null) {
    return (
      <details className="system-fold">
        <summary>
          <span className="turn-role mono">system</span>
          <span className="system-preview">{text === "" ? "Empty message" : text.replace(/\s+/g, " ")}</span>
        </summary>
        <p>{text}</p>
      </details>
    );
  }
  return (
    <div className="turn" data-role={message.role}>
      <span className="turn-role mono">
        {message.role}
        {message.role === "tool" && typeof message.name === "string" ? (
          <span className="turn-name">{message.name}</span>
        ) : null}
      </span>
      <div className="turn-body">
        {text === null && toolCalls === null ? <p className="turn-empty">No content</p> : null}
        {message.role === "assistant" && typeof message.thinking === "string" && message.thinking !== "" ? (
          <details className="thinking">
            <summary>Thinking</summary>
            <p>{message.thinking}</p>
          </details>
        ) : null}
        {text === null ? null : structured ? <code className="call mono">{text}</code> : <p>{text}</p>}
        {toolCalls === null
          ? null
          : toolCalls.map((call, index) => (
              <code className="call mono" key={index}>
                {callText(call)}
              </code>
            ))}
      </div>
    </div>
  );
}
