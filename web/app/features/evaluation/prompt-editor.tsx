import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { markdown } from "@codemirror/lang-markdown";
import { Compartment } from "@codemirror/state";
import { useTheme } from "../../shared/theme";
import { EditorView, keymap, lineNumbers } from "@codemirror/view";
import { useEffect, useRef, useState } from "react";

const editorTheme = (dark: boolean) =>
  EditorView.theme(
    {
      "&": { color: dark ? "#e8eef3" : "#18232d", backgroundColor: dark ? "#1b242d" : "#fff" },
      ".cm-gutters": {
        backgroundColor: dark ? "#1b242d" : "#fff",
        color: dark ? "#a9b7c4" : "#52616e",
        border: "none",
      },
      ".cm-cursor": { borderLeftColor: dark ? "#e8eef3" : "#18232d" },
      ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
        backgroundColor: dark ? "#345f60" : "#cce8e5",
      },
    },
    { dark },
  );

export function PromptEditor({
  value,
  onChange,
  fields,
}: {
  value: string;
  onChange: (value: string) => void;
  fields: string[];
}) {
  const { resolvedTheme } = useTheme();
  const theme = useRef(new Compartment());
  const initialTheme = useRef(resolvedTheme);
  const initialDocument = useRef(value);
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const change = useRef(onChange);
  const [field, setField] = useState(fields[0] ?? "conversation");
  change.current = onChange;
  useEffect(() => {
    if (!host.current) return;
    const editor = new EditorView({
      parent: host.current,
      doc: initialDocument.current,
      extensions: [
        lineNumbers(),
        history(),
        markdown(),
        theme.current.of(editorTheme(initialTheme.current === "dark")),
        keymap.of([...defaultKeymap, ...historyKeymap]),
        EditorView.contentAttributes.of({ "aria-label": "Judge prompt" }),
        EditorView.lineWrapping,
        EditorView.updateListener.of((update) => {
          if (update.docChanged) change.current(update.state.doc.toString());
        }),
      ],
    });
    view.current = editor;
    return () => {
      editor.destroy();
      view.current = null;
    };
  }, []);
  useEffect(() => {
    view.current?.dispatch({ effects: theme.current.reconfigure(editorTheme(resolvedTheme === "dark")) });
  }, [resolvedTheme]);
  useEffect(() => {
    const editor = view.current;
    if (editor && editor.state.doc.toString() !== value)
      editor.dispatch({ changes: { from: 0, to: editor.state.doc.length, insert: value } });
  }, [value]);
  const insert = () => {
    const editor = view.current;
    if (!editor) return;
    const selection = editor.state.selection.main;
    const token = `{{${field}}}`;
    editor.dispatch({
      changes: { from: selection.from, to: selection.to, insert: token },
      selection: { anchor: selection.from + token.length },
    });
    editor.focus();
  };
  return (
    <div>
      <div className="processor-editor" ref={host} />
      <div className="prompt-toolbar">
        <label>
          Insert field{" "}
          <select value={field} onChange={(e) => setField(e.target.value)}>
            {fields.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </label>{" "}
        <button className="control-button" type="button" onClick={insert}>
          Insert at cursor
        </button>
      </div>
    </div>
  );
}
