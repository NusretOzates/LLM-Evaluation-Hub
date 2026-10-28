import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { python } from "@codemirror/lang-python";
import { bracketMatching, defaultHighlightStyle, indentUnit, syntaxHighlighting } from "@codemirror/language";
import { StateEffect, StateField } from "@codemirror/state";
import { keymap, lineNumbers } from "@codemirror/view";
import { EditorView, Decoration, type DecorationSet } from "@codemirror/view";
import { useEffect, useRef } from "react";

const setDiagnostic = StateEffect.define<number | null>();
const diagnostics = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(decorations, transaction) {
    decorations = decorations.map(transaction.changes);
    for (const effect of transaction.effects) {
      if (effect.is(setDiagnostic)) {
        if (effect.value === null) decorations = Decoration.none;
        else {
          const line = Math.min(Math.max(effect.value, 1), transaction.state.doc.lines);
          decorations = Decoration.set(
            Decoration.line({ class: "cm-processor-error-line" }).range(transaction.state.doc.line(line).from),
          );
        }
      }
    }
    return decorations;
  },
  provide: (field) => EditorView.decorations.from(field),
});

export function ProcessorEditor({
  value,
  diagnosticLine,
  onChange,
}: {
  value: string;
  diagnosticLine: number | null;
  onChange: (value: string) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  const initialDocument = useRef(value);
  onChangeRef.current = onChange;

  useEffect(() => {
    if (host.current === null) return;
    const editor = new EditorView({
      parent: host.current,
      doc: initialDocument.current,
      extensions: [
        lineNumbers(),
        EditorView.contentAttributes.of({ "aria-label": "Python processor" }),
        history(),
        python(),
        syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
        bracketMatching(),
        indentUnit.of("    "),
        diagnostics,
        keymap.of([...defaultKeymap, ...historyKeymap]),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) onChangeRef.current(update.state.doc.toString());
        }),
        EditorView.lineWrapping,
        EditorView.theme({
          "&": { height: "100%" },
          ".cm-scroller": { overflow: "auto", fontFamily: "var(--font-mono)", fontSize: "12.5px" },
          ".cm-content": { padding: "12px 0" },
          ".cm-gutters": { backgroundColor: "var(--gray-1)", border: "none", color: "var(--gray-6)" },
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
    const editor = view.current;
    if (editor === null || editor.state.doc.toString() === value) return;
    editor.dispatch({ changes: { from: 0, to: editor.state.doc.length, insert: value } });
  }, [value]);

  useEffect(() => {
    const editor = view.current;
    if (editor !== null) editor.dispatch({ effects: setDiagnostic.of(diagnosticLine) });
  }, [diagnosticLine]);

  return <div className="processor-editor" ref={host} />;
}
