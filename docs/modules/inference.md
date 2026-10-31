---
type: Reference
title: Inference runs
description: Connection settings, request compilation, execution, and recovery for inference runs.
tags: [inference]
status: stable
---

# Inference runs

A connection profile names an OpenAI-compatible Chat Completions base URL, model, optional server environment variable containing the API key, supported reasoning controls and maximum-token field. Profiles contain the variable name, never the key value. Configure the variable in the API process environment. The endpoint receives the selected conversation and row tools; expected output, extras and segment values are not sent. Media and historical thinking inputs are unsupported and rejected during preflight. Tool calls are recorded, not executed.

Choose either Effort levels or Thinking on/off for reasoning controls. Both offer Server default, which omits the parameter. Removed profile modes are rejected; there is no migration or fallback for previous configurations.

Runs select datasets directly or through tags. The resolved dataset identities, names, snapshot versions, connection and generation settings and output formats are frozen at creation. The defaults are four concurrent requests, 60 attempts per minute, a 120-second timeout, two retries and all retained rows. Attempts share the rate and concurrency limits across datasets. Connection failures, timeouts, HTTP 429 and 5xx are retried with bounded backoff and Retry-After support. Authentication failures interrupt the run. A test example is an explicit endpoint request and cannot run concurrently with inference work.

Dataset output metadata is independent of immutable snapshots and defaults to text. The import wizard’s Review step lets users choose this default before submission; it is published atomically with the dataset and can be edited from the dataset detail page later. JSON object mode requests an object; JSON Schema mode validates an object-root Draft 2020-12 schema locally. Strict schemas require each object property and `additionalProperties: false`, including nested objects; use nullable values for optional data. Local validity does not establish provider support. Remote schema references are rejected. Results retain the raw response, content and tool calls, parsed JSON, validation errors, finish reason, usage, latency and attempts. Refusals, truncation, malformed JSON, schema mismatches and tool-call-only responses have distinct statuses; none causes answer regeneration.

Only one inference runner may own a catalog. Results are committed row by row. Shutdown or restart marks unfinished work interrupted; it does not automatically send requests. Explicit resume skips committed rows, but an in-flight request may be sent again after a crash. Cancellation stops dispatch and active requests and retains completed results. Trashing a dataset leaves its selected inputs available. Permanent deletion is blocked while an unfinished run depends on it; after completion or cancellation, deletion preserves the frozen dataset identity and results while inputs become unavailable.

The inference API is served by `api/inference_routes.py`; contracts are in `inference/contracts.py`, compilation in `inference/compiler.py`, persistence in `inference/store.py`, and transport and scheduling in `inference/transport.py` and `inference/runner.py`. The API has no authentication: restrict access to trusted users because creating a run sends requests to the configured endpoint.
