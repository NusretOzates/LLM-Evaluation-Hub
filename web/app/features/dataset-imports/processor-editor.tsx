import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { python } from "@codemirror/lang-python";
import { bracketMatching, HighlightStyle, indentUnit, syntaxHighlighting } from "@codemirror/language";
import { Compartment, StateEffect, StateField } from "@codemirror/state";
import { keymap, lineNumbers } from "@codemirror/view";
import { EditorView, Decoration, type DecorationSet } from "@codemirror/view";
import { useEffect, useRef } from "react";
import { tags } from "@lezer/highlight";
import { useTheme } from "../../shared/theme";

const themeExtension = (dark: boolean) => [
  EditorView.theme(
    {
      "&": { color: dark ? "#e8eef3" : "#18232d", backgroundColor: dark ? "#1b242d" : "#ffffff" },
      ".cm-cursor": { borderLeftColor: dark ? "#e8eef3" : "#18232d" },
      ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
        backgroundColor: dark ? "#345f60" : "#cce8e5",
      },
    },
    { dark },
  ),
  syntaxHighlighting(
    HighlightStyle.define([
      { tag: tags.keyword, color: dark ? "#b8a5ff" : "#653a9e" },
      { tag: tags.string, color: dark ? "#a7dba0" : "#276b35" },
      { tag: tags.comment, color: dark ? "#a9b7c4" : "#52616e", fontStyle: "italic" },
      { tag: tags.number, color: dark ? "#ffd09b" : "#8e4b13" },
    ]),
  ),
];
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
  const { resolvedTheme } = useTheme();
  const theme = useRef(new Compartment());
  const initialTheme = useRef(resolvedTheme);
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
        theme.current.of(themeExtension(initialTheme.current === "dark")),
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
          ".cm-scroller": { overflow: "auto", fontFamily: "var(--font-mono)", fontSize: "13px" },
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
    view.current?.dispatch({ effects: theme.current.reconfigure(themeExtension(resolvedTheme === "dark")) });
  }, [resolvedTheme]);
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
