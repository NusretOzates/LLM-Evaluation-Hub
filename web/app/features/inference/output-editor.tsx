import { Trash2 } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { JsonValue } from "../../catalog-types";
import { Button } from "../../shared/controls";
import type { Output } from "./api";

type Schema = Record<string, JsonValue>;
const isObject = (value: unknown): value is Schema =>
  value !== null && typeof value === "object" && !Array.isArray(value);
const keys = new Set(["type", "properties", "required", "additionalProperties", "items", "description", "enum"]);
export function visualReason(schema: Schema): string | null {
  for (const key of Object.keys(schema)) if (!keys.has(key)) return `“${key}” is not supported by the visual editor.`;
  const type = schema.type;
  const types = Array.isArray(type) ? type : [type];
  if (
    types.length > 2 ||
    types.filter((v) => v !== "null").length !== 1 ||
    !types.every((v) => ["object", "array", "string", "number", "integer", "boolean", "null"].includes(String(v)))
  )
    return "This type is not supported by the visual editor.";
  const base = types.find((v) => v !== "null");
  if (base !== "object" && ["properties", "required", "additionalProperties"].some((k) => k in schema))
    return "Object keywords on a non-object cannot be edited visually.";
  if (base !== "array" && "items" in schema) return "Items on a non-array cannot be edited visually.";
  if (
    base === "object" &&
    Array.isArray(schema.required) &&
    isObject(schema.properties) &&
    schema.required.some(
      (k) => typeof k !== "string" || !Object.hasOwn(isObject(schema.properties) ? schema.properties : {}, k),
    )
  )
    return "Required includes a property not present in properties.";
  if (schema.description !== undefined && typeof schema.description !== "string") return "Description must be text.";
  if (schema.enum !== undefined && !Array.isArray(schema.enum)) return "Enum must be an array.";
  if (base === "object") {
    if (schema.properties !== undefined && !isObject(schema.properties)) return "Object properties must be an object.";
    if (
      schema.required !== undefined &&
      (!Array.isArray(schema.required) || !schema.required.every((x) => typeof x === "string"))
    )
      return "Required must be a list of names.";
    if (
      schema.additionalProperties !== undefined &&
      schema.additionalProperties !== false &&
      schema.additionalProperties !== true
    )
      return "Schema-valued additionalProperties is not supported visually.";
    for (const child of Object.values(isObject(schema.properties) ? schema.properties : {})) {
      if (!isObject(child)) return "Boolean schemas are not supported visually.";
      const reason = visualReason(child);
      if (reason) return reason;
    }
  } else if (base === "array") {
    if (!isObject(schema.items)) return "Arrays need one item schema for visual editing.";
    return visualReason(schema.items);
  }
  return null;
}
const initialSchema: Schema = { type: "object", properties: {}, required: [], additionalProperties: false };
export function OutputEditor({
  value,
  onChange,
  onValidityChange,
}: {
  value: Output;
  onChange: (v: Output) => void;
  onValidityChange?: (valid: boolean) => void;
}) {
  const [tab, setTab] = useState<"visual" | "json">("visual");
  const [text, setText] = useState(() => JSON.stringify(value.schema ?? initialSchema, null, 2));
  const [error, setError] = useState("");
  const [invalidDrafts, setInvalidDrafts] = useState<string[]>([]);
  const reportDraft = useCallback((id: string, valid: boolean) => {
    setInvalidDrafts((old) =>
      valid ? (old.includes(id) ? old.filter((x) => x !== id) : old) : old.includes(id) ? old : [...old, id],
    );
  }, []);
  const id = useId();
  const emitted = useRef(JSON.stringify(value.schema));
  useEffect(() => {
    const incoming = JSON.stringify(value.schema);
    if (incoming !== emitted.current) {
      setText(JSON.stringify(value.schema ?? initialSchema, null, 2));
      setError("");
      emitted.current = incoming;
    }
  }, [value.schema]);
  const schema = value.schema ?? initialSchema;
  const reason = visualReason(schema);
  useEffect(() => {
    onValidityChange?.(
      value.kind !== "json_schema" ||
        (!error && invalidDrafts.length === 0 && !!value.schema && (!value.strict || !strictReason(value.schema))),
    );
  }, [value, error, invalidDrafts, onValidityChange]);
  function updateSchema(next: Schema) {
    emitted.current = JSON.stringify(next);
    onChange({ ...value, schema: next });
    setText(JSON.stringify(next, null, 2));
    setError("");
  }
  function updateText(next: string) {
    setText(next);
    try {
      const parsed: unknown = JSON.parse(next);
      if (!isObject(parsed) || parsed.type !== "object")
        throw new Error("The schema must be a JSON object with type object.");
      emitted.current = JSON.stringify(parsed);
      onChange({ ...value, schema: parsed });
      onValidityChange?.(true);
      setError("");
    } catch (e) {
      onValidityChange?.(false);
      setError(e instanceof Error ? e.message : "Invalid JSON");
    }
  }
  return (
    <div className="output-editor">
      <label className="output-kind" htmlFor={`${id}-kind`}>
        Output format
        <select
          id={`${id}-kind`}
          value={value.kind}
          onChange={(e) =>
            onChange({
              ...value,
              kind: e.target.value as Output["kind"],
              schema: e.target.value === "json_schema" ? schema : value.schema,
            })
          }
        >
          <option value="text">Text</option>
          <option value="json_object">JSON object</option>
          <option value="json_schema">JSON Schema</option>
        </select>
      </label>
      {value.kind === "json_schema" && (
        <>
          <label className="check">
            <input
              type="checkbox"
              checked={value.strict}
              onChange={(e) => onChange({ ...value, strict: e.target.checked })}
            />{" "}
            Strict mode
          </label>
          <p className="hint">
            Requires all fields and closed objects. Use Allow null for optional values. Endpoint support may vary.
          </p>
          <div className="schema-tabs">
            <Button type="button" aria-pressed={tab === "visual"} onClick={() => setTab("visual")}>
              Visual
            </Button>
            <Button
              type="button"
              disabled={invalidDrafts.length > 0}
              aria-pressed={tab === "json"}
              onClick={() => setTab("json")}
            >
              JSON
            </Button>
          </div>
          {value.strict && value.schema && strictReason(value.schema) && (
            <p role="alert" className="field-error">
              {strictReason(value.schema)}
            </p>
          )}
          {tab === "json" ? (
            <>
              <label htmlFor={`${id}-json`}>JSON Schema</label>
              <textarea
                id={`${id}-json`}
                className="inference-json"
                value={text}
                onChange={(e) => updateText(e.target.value)}
                aria-invalid={!!error}
              />
              {error && (
                <p role="alert" className="field-error">
                  {error}
                </p>
              )}
            </>
          ) : error || reason ? (
            <p role="status">
              Visual editing is unavailable: {error || reason} The JSON remains intact; use the JSON tab to edit it.
            </p>
          ) : (
            <div className="schema-builder">
              <details className="schema-root-description">
                <summary>About this output (optional)</summary>
                <label>
                  Output description
                  <input
                    value={typeof schema.description === "string" ? schema.description : ""}
                    onChange={(e) => updateSchema({ ...schema, description: e.target.value })}
                  />
                </label>
                <p className="hint">Describe the whole response for the model.</p>
              </details>
              <SchemaFields
                schema={schema}
                onChange={updateSchema}
                strict={value.strict}
                onValidityChange={reportDraft}
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}
type DraftReporter = (id: string, valid: boolean) => void;
const schemaTypes = ["string", "number", "integer", "boolean", "object", "array"];
function typeOf(schema: Schema) {
  const types = Array.isArray(schema.type) ? schema.type : [schema.type];
  return String(types.find((item) => item !== "null") ?? "string");
}
function changeType(schema: Schema, type: string): Schema {
  const nullable = Array.isArray(schema.type) && schema.type.includes("null");
  const result: Schema = { type: nullable ? [type, "null"] : type };
  if (typeof schema.description === "string") result.description = schema.description;
  if (type === "object") Object.assign(result, { properties: {}, required: [], additionalProperties: false });
  if (type === "array") result.items = { type: "string" };
  return result;
}
function SchemaFields({
  schema,
  onChange,
  strict,
  onValidityChange,
}: {
  schema: Schema;
  onChange: (schema: Schema) => void;
  strict: boolean;
  onValidityChange: DraftReporter;
}) {
  const properties = isObject(schema.properties) ? schema.properties : {};
  const required = Array.isArray(schema.required) ? schema.required : [];
  const entries = Object.entries(properties);
  function add() {
    let name = "field";
    let n = 2;
    while (Object.hasOwn(properties, name)) name = `field${n++}`;
    onChange({
      ...schema,
      properties: { ...properties, [name]: { type: "string" } },
      required: strict ? [...required, name] : required,
    });
  }
  return (
    <div className="schema-fields">
      <div className="schema-fields-header">
        <div>
          <strong>Fields</strong>
          <span className="schema-count">{entries.length}</span>
        </div>
        <Button type="button" onClick={add}>
          Add field
        </Button>
      </div>
      {entries.length === 0 && <p className="schema-empty">No fields yet. Add a field to describe the response.</p>}
      {entries.map(
        ([name, child]) =>
          isObject(child) && (
            <FieldCard
              key={name}
              name={name}
              schema={child}
              required={required.includes(name)}
              strict={strict}
              onValidityChange={onValidityChange}
              onRename={(nextName) => {
                if (!nextName || (nextName !== name && Object.hasOwn(properties, nextName))) return false;
                onChange({
                  ...schema,
                  properties: Object.fromEntries(entries.map(([key, val]) => [key === name ? nextName : key, val])),
                  required: required.map((key) => (key === name ? nextName : key)),
                });
                return true;
              }}
              isValidName={(nextName) => !!nextName && (nextName === name || !Object.hasOwn(properties, nextName))}
              onRequired={(checked) =>
                onChange({
                  ...schema,
                  required: checked ? [...required, name] : required.filter((key) => key !== name),
                })
              }
              onChange={(next) => onChange({ ...schema, properties: { ...properties, [name]: next } })}
              onRemove={() => {
                const next = { ...properties };
                delete next[name];
                onChange({ ...schema, properties: next, required: required.filter((key) => key !== name) });
              }}
            />
          ),
      )}
    </div>
  );
}
function FieldCard({
  name,
  schema,
  required,
  strict,
  onValidityChange,
  onRename,
  isValidName,
  onRequired,
  onChange,
  onRemove,
}: {
  name: string;
  schema: Schema;
  required: boolean;
  strict: boolean;
  onValidityChange: DraftReporter;
  onRename: (name: string) => boolean;
  isValidName: (name: string) => boolean;
  onRequired: (checked: boolean) => void;
  onChange: (schema: Schema) => void;
  onRemove: () => void;
}) {
  const type = typeOf(schema);
  return (
    <div className="schema-property">
      <div className="schema-field-row">
        <PropertyName name={name} onCommit={onRename} isValid={isValidName} onValidityChange={onValidityChange} />
        <TypeSelect schema={schema} onChange={onChange} label="Type" />
        <label className="schema-check">
          <input type="checkbox" checked={required} onChange={(e) => onRequired(e.target.checked)} />
          Required
        </label>
        <label className="schema-check">
          <input
            type="checkbox"
            checked={Array.isArray(schema.type) && schema.type.includes("null")}
            onChange={(e) => onChange({ ...schema, type: e.target.checked ? [type, "null"] : type })}
          />
          Allow null
        </label>
        <button
          type="button"
          className="icon-button schema-delete"
          aria-label={`Delete field ${name}`}
          title={`Delete field ${name}`}
          onClick={onRemove}
        >
          <Trash2 size={16} aria-hidden="true" />
        </button>
      </div>
      <FieldSettings schema={schema} onChange={onChange} onValidityChange={onValidityChange} />
      {type === "object" && (
        <div className="schema-nested">
          <span className="schema-nested-label">Object fields</span>
          <SchemaFields schema={schema} onChange={onChange} strict={strict} onValidityChange={onValidityChange} />
        </div>
      )}
      {type === "array" && isObject(schema.items) && (
        <ArrayItems
          schema={schema.items}
          onChange={(items) => onChange({ ...schema, items })}
          strict={strict}
          onValidityChange={onValidityChange}
        />
      )}
    </div>
  );
}
function TypeSelect({
  schema,
  onChange,
  label,
}: {
  schema: Schema;
  onChange: (schema: Schema) => void;
  label: string;
}) {
  return (
    <label>
      {label}
      <select value={typeOf(schema)} onChange={(e) => onChange(changeType(schema, e.target.value))}>
        {schemaTypes.map((type) => (
          <option key={type} value={type}>
            {type}
          </option>
        ))}
      </select>
    </label>
  );
}
function FieldSettings({
  schema,
  onChange,
  onValidityChange,
}: {
  schema: Schema;
  onChange: (schema: Schema) => void;
  onValidityChange: DraftReporter;
}) {
  return (
    <details className="schema-settings">
      <summary>Field settings</summary>
      <div className="schema-settings-body">
        <label>
          Field description
          <input
            value={typeof schema.description === "string" ? schema.description : ""}
            onChange={(e) => {
              const next = { ...schema };
              if (e.target.value) next.description = e.target.value;
              else delete next.description;
              onChange(next);
            }}
          />
        </label>
        {!["object", "array"].includes(typeOf(schema)) && (
          <EnumEditor
            value={schema.enum}
            onValidityChange={onValidityChange}
            onChange={(value) => {
              const next = { ...schema };
              if (value === undefined) delete next.enum;
              else next.enum = value;
              onChange(next);
            }}
          />
        )}
      </div>
    </details>
  );
}
function ArrayItems({
  schema,
  onChange,
  strict,
  onValidityChange,
}: {
  schema: Schema;
  onChange: (schema: Schema) => void;
  strict: boolean;
  onValidityChange: DraftReporter;
}) {
  const type = typeOf(schema);
  return (
    <div className="schema-nested">
      <span className="schema-nested-label">Array items</span>
      <div className="schema-item-row">
        <TypeSelect schema={schema} onChange={onChange} label="Item type" />
        <label className="schema-check">
          <input
            type="checkbox"
            checked={Array.isArray(schema.type) && schema.type.includes("null")}
            onChange={(e) => onChange({ ...schema, type: e.target.checked ? [type, "null"] : type })}
          />
          Allow null
        </label>
      </div>
      <FieldSettings schema={schema} onChange={onChange} onValidityChange={onValidityChange} />
      {type === "object" && (
        <SchemaFields schema={schema} onChange={onChange} strict={strict} onValidityChange={onValidityChange} />
      )}
      {type === "array" && isObject(schema.items) && (
        <ArrayItems
          schema={schema.items}
          onChange={(items) => onChange({ ...schema, items })}
          strict={strict}
          onValidityChange={onValidityChange}
        />
      )}
    </div>
  );
}

export function strictReason(schema: Schema): string | null {
  const types = Array.isArray(schema.type) ? schema.type : [schema.type];
  if (types.includes("object")) {
    if (schema.additionalProperties !== false)
      return "Strict mode requires additionalProperties: false on each object.";
    const properties = isObject(schema.properties) ? schema.properties : {};
    const required = Array.isArray(schema.required) ? schema.required : [];
    if (Object.keys(properties).some((key) => !required.includes(key)))
      return "Strict mode requires every property. Mark optional values required and nullable.";
    for (const child of Object.values(properties))
      if (isObject(child)) {
        const reason = strictReason(child);
        if (reason) return reason;
      }
  }
  if (types.includes("array") && isObject(schema.items)) return strictReason(schema.items);
  return null;
}

function PropertyName({
  name,
  onCommit,
  isValid,
  onValidityChange,
}: {
  name: string;
  onCommit: (value: string) => boolean;
  isValid: (value: string) => boolean;
  onValidityChange: (id: string, valid: boolean) => void;
}) {
  const id = useId();
  useEffect(() => () => onValidityChange(id, true), [id, onValidityChange]);
  const [draft, setDraft] = useState(name);
  const [error, setError] = useState(false);
  return (
    <label>
      Field name
      <input
        value={draft}
        aria-invalid={error}
        onChange={(e) => {
          setDraft(e.target.value);
          onValidityChange(id, isValid(e.target.value));
        }}
        onBlur={() => {
          if (!onCommit(draft)) setError(true);
          else setError(false);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            e.currentTarget.blur();
          }
        }}
      />
      {error && <span className="field-error">Choose a unique, non-empty name.</span>}
    </label>
  );
}
function EnumEditor({
  value,
  onChange,
  onValidityChange,
}: {
  value: JsonValue | undefined;
  onChange: (value: JsonValue[] | undefined) => void;
  onValidityChange: (id: string, valid: boolean) => void;
}) {
  const id = useId();
  useEffect(() => () => onValidityChange(id, true), [id, onValidityChange]);
  const [draft, setDraft] = useState(value === undefined ? "" : JSON.stringify(value));
  const [error, setError] = useState(false);
  function commit() {
    try {
      if (!draft.trim()) {
        onChange(undefined);
        setError(false);
        return;
      }
      const parsed: unknown = JSON.parse(draft);
      if (!Array.isArray(parsed)) throw new Error();
      onChange(parsed);
      setError(false);
    } catch {
      setError(true);
    }
  }
  return (
    <label>
      Allowed values (JSON array)
      <input
        value={draft}
        aria-invalid={error}
        onChange={(e) => {
          setDraft(e.target.value);
          try {
            const v: unknown = e.target.value.trim() ? JSON.parse(e.target.value) : [];
            onValidityChange(id, Array.isArray(v));
          } catch {
            onValidityChange(id, false);
          }
        }}
        onBlur={commit}
        placeholder={'["low", "high"]'}
      />
      {error && <span className="field-error">Enter a valid JSON array.</span>}
    </label>
  );
}
