import assert from "node:assert/strict";
import test from "node:test";
import { strictReason, visualReason } from "../app/features/inference/output-editor";

test("visual editor preserves unsupported constructs and does not inspect enum data", () => {
  assert.match(
    visualReason({ type: "object", properties: { item: { type: "string", pattern: "x" } } }) ?? "",
    /pattern/,
  );
  assert.equal(
    visualReason({ type: "object", properties: { value: { type: "string", enum: [{ pattern: "data" }] } } }),
    null,
  );
  assert.equal(
    visualReason(
      JSON.parse(
        '{"type":"object","properties":{"__proto__":{"type":"string"},"constructor":{"type":"string"},"名字":{"type":"string"}},"required":[]}',
      ),
    ),
    null,
  );
});
test("strict schemas require properties recursively without changing them", () => {
  const schema = { type: "object", properties: { a: { type: "string" } }, required: [], additionalProperties: false };
  assert.match(strictReason(schema) ?? "", /every property/);
  assert.deepEqual(schema.required, []);
  assert.equal(strictReason({ ...schema, required: ["a"] }), null);
});
