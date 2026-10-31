---
type: Reference
title: Workbench design
description: Theme, layout, and shared controls for the catalog workbench.
tags: [workbench, design]
generated: { by: process:codex-refactor, at: 2026-10-31T00:00:00+03:00 }
status: stable
---

# Workbench design

The workbench is a dense analyst workspace with light and dark themes. [Workbench](workbench.md) describes routes and behavior. `web/app/app.css` imports the styles owned by the shell, catalog, inspector, imports, tags, and shared controls.

## Layout and typography

The desktop shell fills the viewport. The sidebar is 224px wide, with a 56px collapsed rail. Below 768px, a Menu button opens a modal navigation drawer. The Datasets and Tags pages use a toolbar below the title. The dataset inspector gives the reader the remaining width after its example index and optional metadata pane; narrower workspaces use modal sheets for panes that cannot fit.

IBM Plex Sans is the interface font and IBM Plex Mono is used for technical values. Body text is 14px with 1.5 line height; page titles are 22px. Conversation prose uses 16px text with 1.6 line height. Controls and tree rows target 44px, with a visible 2px accent focus outline.

## Themes

Appearance is available in the navigation utility area. System follows the operating system; Light and Dark are explicit choices. The preference is stored under `evaluation-hub.theme` when storage is available. An early script applies the resolved theme before the application renders. The processor editor changes its CodeMirror theme without recreating the editor.

The light palette uses off-white framing, white surfaces, dark slate text, and teal selection. The dark palette uses layered charcoal surfaces, light slate text, and a lighter teal. Semantic tokens in `styles/base.css` supply text, surfaces, borders, focus, selection, and danger colors. Native controls inherit the resolved color scheme. Any new state must remain legible in both themes and identify status with text as well as color.

## Interaction and motion

Shared controls in `web/app/shared/controls.tsx`, `dialog.tsx`, and `action-menu.tsx` provide consistent fields, buttons, chips, feedback, modal dialogs, and menus. Dialogs block dismissal while a submitted mutation is pending. Menu positioning uses the measured panel and trigger; scrolling outside or resizing closes the menu. Row links and row actions have separate targets.

Motion is limited to short state transitions. Reduced-motion preferences disable animation and transitions. Avoid moving table rows or changing their height when menus open. Check populated screens, long content, keyboard focus, overlays, and narrow layouts in both themes when changing visual behavior.

## Inference workspace

Connections store endpoint and model configuration, with API keys referenced by server environment variable name. The inference setup selects datasets directly or by tag, configures generation and execution limits, and reviews a credential-free compiled request. Testing an example is an explicit network operation. Runs freeze the selected dataset identities and effective settings; results retain responses, validation details, usage and timing. Source inputs remain available while the dataset is retained and are marked unavailable after purge.

Dataset output settings and per-run overrides share a JSON Schema editor. The visual editor presents fields in compact rows, with nested object fields and array items, nullable and required controls, and expandable field settings for descriptions and allowed values. An optional collapsed section describes the whole output. Unsupported schema constructs remain in JSON and disable visual editing. Strict mode requires every property and `additionalProperties: false` recursively; optional values can be represented with nullable types. Schema validation does not establish compatibility with every endpoint.
