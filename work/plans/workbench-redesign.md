# Evaluation Hub workbench redesign

Status: implementation complete. The bounded frontend audit is complete; real-worker end-to-end execution on this macOS host and actual browser-controlled 200% zoom remain unverified.

## Goal

Make the app attractive, understandable, and efficient for importing and inspecting evaluation datasets. A data scientist should recognize the next action, understand whether it affects one example or the whole dataset, and recover from mistakes without learning the implementation. Preserve existing processing, schema inference, tag assignment, import history, and dataset Trash behavior.

Success means a data scientist can find a dataset, inspect examples, add a child tag, preview an import, understand a failed job, and restore a dataset using a consistent interface in both themes.

## Constraints

- Preserve existing backend contracts, stored datasets, processing behavior, source-column segment selection, Python-defined custom segments, supplied conversations, import history, and Trash semantics.
- Preserve all current uncommitted changes. Do not reset or replace previous work while implementing the redesign.
- Keep React Router, local CSS, IBM Plex fonts, Lucide icons, and the current API boundary. No new UI framework, remote fonts, authentication, bulk operations, rename, drag-and-drop, or dashboard route.
- Light and dark ship together, including the Python editor, menus, dialogs, and feedback states. Keep keyboard shortcuts and deep links.
- This is the sole implementation contract. No previous chat or secondary design document is required. Existing design notes are historical; this plan takes precedence. All dimensions below are CSS pixels.

## Findings

- The React Router route list contains catalog, dataset inspector, import list/new/detail, and Trash routes. A dedicated Tags route does not exist yet.
- web/app/shell.tsx currently owns tag management and single-tag sidebar filtering. The root loader supplies the tag forest and active datasets together; query-only navigation does not reload the shared catalog.
- web/app/shared/catalog-view.ts owns subtree counts and single-tag dataset filtering. Matching uses exact paths or path-plus-slash descendants, so no backend filter API change is needed for multiple tags and name search.
- Tag creation, deletion impact, subtree deletion, and child promotion already have API clients. The shared hierarchical picker and floating menu are available for reuse.
- The inspector already separates example index, reader, and optional metadata. Its example search/facets operate on the current page, not the full dataset.
- The import wizard has four steps and a CodeMirror processor editor. Job history, cancellation/retry, and dataset Trash/restore/permanent deletion must survive restyling.
- docs/modules/workbench-design.md still prescribes the old light-only palette, 15px page titles, and 26–30px controls. It must be revised when implementation lands.
- ui-ux-pro-max provided applicable minimal-workspace, responsive-table, inline-validation, label-overflow and keyboard guidance. Its automatic landing-page recommendation was rejected after a narrower retry because it did not match this product.

## Decisions

Adopt a dense analyst workspace for data scientists doing repeated import, inspection and comparison. Prioritize information per screen, fast scanning, keyboard operation and contextual tools. Density comes from compact structure and fewer unnecessary wrappers, with readable labels, distinct regions and generous reading space where long content requires it.

Use IBM Plex Sans, IBM Plex Mono for technical values, Lucide icons, restrained neutral surfaces and teal selection/accent tokens. Keep primary actions obvious and destructive controls secondary. Do not add oversized metrics, decorative gradients, repeated nested cards, or a marketing-style dashboard. The earlier calm-workspace recommendation over-weighted the current visual crowding; the broken menus and weak hierarchy were implementation problems rather than evidence against an expert-oriented interface.

Light and dark are equal requirements. Define semantic surface, text, border, selection, focus, status and code-editor tokens in both themes; audit contrast independently. Use a neutral off-white frame in light mode and layered charcoal surfaces in dark mode, with teal adapted to each theme. Dark mode is not an inversion or a pure-black backdrop. A System / Light / Dark preference belongs in the navigation utility area, defaults to System, persists locally, follows system changes while System is chosen, and applies before first paint to avoid theme flash. Both themes include native controls, popovers, dialogs, code/JSON, syntax highlighting, selection, status labels, disabled and loading states. Use a labelled compact menu rather than three prominent header buttons.

- Navigation: Datasets, Imports, Tags. Put Trash in a quiet utility position at the bottom of the sidebar. Keep Dataset import history accessible from Imports and avoid repeating it as a prominent action on every page. Desktop navigation collapses to a labelled icon rail; narrow screens use a dismissible navigation drawer.
- Page anatomy: breadcrumb when useful, readable page title, one sentence of context only when needed, one primary action, secondary actions, then task-specific toolbar and content. Preserve browser history and deep links.
- One coherent component family for buttons, inputs, search fields, chips, menus, dialogs, status labels, validation, empty states, and skeletons. Prefer local components/CSS and native dialog/popover behavior; adding a UI framework is not required.
- Type: 22px page titles, 16–18px section headings, 14px controls/table/tree labels, 12px minimum secondary metadata, and 16px conversation prose with a comfortable reading measure. Technical strings use mono selectively. Do not apply a global font-size change that enlarges code, tabs, or dense lists indiscriminately.
- Spacing: 8/16/24/32px rhythm, 24px desktop and 16px narrow-screen gutters, restrained 6–10px corner radii. Forms use a readable bounded width; editor and inspector workspaces can use available width.
- Interaction: 44px tree/list rows and control hit areas, compact 52px catalog rows, visible keyboard focus, readable secondary text, 4.5:1 normal-text contrast, and 3:1 meaningful control/state boundaries. Separate row navigation from row actions. Labels remain visible after typing. Confirmation dialogs identify exact scope and focus Cancel initially.
- Feedback: pending actions prevent duplicate submission and retain labels. Failures preserve user input and show a clear next action. Success feedback is brief and accessible. Never invent progress percentages from row counts that are not a known total.
- Motion: short color/opacity transitions only; no decorative entrance effects, bouncing badges, table movement, or changing row height when a menu opens. Respect reduced motion.

The user chose multi-tag match-all filtering, name search, a compact Tags popover, and a dedicated Tags page with a tree plus detail panel. Keep parent-only assignments valid. The concrete values below are design defaults for implementation; do not replace them with another visual direction.

### Handoff entry point and ownership

Repository: the current LLM-Evaluation-Hub checkout. Start by reading applicable AGENTS.md, `web/package.json`, `docs/architecture/code-map.md`, and the current files named below. The workspace is intentionally dirty with working import, tagging, and deletion features. Establish a baseline diff and preserve those changes. This task authorizes frontend implementation, tests, and documentation only. Do not change API/database behavior or mutate the user's actual catalog for demonstrations. Use the temporary test catalog.

The five implementation units below run in dependency order. Keep each unit runnable before starting the next. The following new paths are proposed ownership boundaries, not claims that they exist already:

- `web/app/shared/theme.tsx`: theme preference/context, storage and system listener; expose `ThemePreference = "system" | "light" | "dark"`, `resolvedTheme`, and `setPreference`. `web/app/root.tsx` owns early theme initialization and the provider.
- `web/app/shared/feedback.tsx`: move `CatalogAlert` out of `shell.tsx` and migrate route/feature imports so navigation does not own shared failure UI.
- `web/app/shared/dialog.tsx`: shared native-dialog wrapper for creation, confirmation and mobile sheets. Props cover title, description, open state, onClose and children. Consumers own form values, requests and mutation errors. Keep existing `shared/action-menu.tsx` for nonmodal menus and improve its focus/positioning behavior in place.
- `web/app/routes/tags.tsx` and `web/app/features/tags/`: route loading/action boundaries plus tree, details and controlled creation/deletion state. `routes.ts` registers `/tags`. Move tag-management code out of `shell.tsx`; move create action out of `routes/datasets.tsx`. Update or remove `TagActionData` imports and every form action targeting `/datasets` for creation.
- `web/app/features/dataset-catalog/`: toolbar, filter popover/sheet, responsive dataset results. Keep `routes/datasets.tsx` as the route adapter. Extend `shared/catalog-view.ts` with `filterDatasets(datasets, { query, tags }, availableTagPaths)`; keep subtree counting there. Migrate callers/tests and remove any filtering helper made obsolete.
- `web/app/shared/tag-picker.tsx`: shared nested-list renderer. Consumers own selected paths and single/multiple selection. Retain path-boundary-aware ancestor/descendant normalization. Do not implement selection separately in the import form, filter toolbar and Tags page.
- Keep inspector ownership in `features/dataset-inspector/` and import ownership in `features/dataset-imports/`. Reuse shared controls rather than moving domain logic into the shell.

Update CSS by owner: semantic variables/base controls in `styles/base.css`; navigation in `shell.css`; catalog in `catalog.css`; inspector in `inspector.css`; imports in `imports.css`; theme-aware menus in `action-menu.css`; hierarchy in `tag-picker.css`; add `tags.css` for the management workspace. `app.css` remains the import entry point. Eliminate conflicting old declarations in the same change. Do not append a global override for every symptom.

### Visual tokens and shared controls

Use these initial semantic colors, and verify contrast on the rendered result. Adjust a pair only if its measured contrast fails; record the adjustment rather than improvising another palette.

- Light: canvas `#F6F8FA`, sidebar `#EEF2F5`, surface/elevated `#FFFFFF`, text `#18232D`, secondary text `#52616E`, subtle divider `#D8E0E5`, strong control border `#8796A2`, accent `#087E82`, accent text `#FFFFFF`, selected surface `#E0F2F0`, danger `#B42338`, danger surface `#FCECEF`.
- Dark: canvas `#10161C`, sidebar `#151D25`, surface `#1B242D`, elevated `#23303B`, text `#E8EEF3`, secondary text `#A9B7C4`, subtle divider `#344452`, strong control border `#607888`, accent `#60D5CD`, accent text `#09201F`, selected surface `#193D3E`, danger `#FF9AA8`, danger surface `#3A242D`.
- Status chips use a word and icon. Success uses the accent pair, failure/cancel errors use danger, active progress uses neutral with a spinner, queued/cancelled use neutral. Do not introduce animated percentages or colors without text. Cancelled is not itself a processing error.
- Base UI font is IBM Plex Sans 14/1.5. Titles 22/1.3 semibold, section headings 16/1.4 semibold, helper/metadata 12/1.5, prose 16/1.6, code 13/1.6 IBM Plex Mono. Text and controls do not shrink below these at mobile widths.
- Buttons/inputs are 44px high, border radius 6px, icons 16px with consistent stroke. Icon-only targets are 44px square. Primary button uses accent fill/on-accent text. Secondary uses surface/strong border. Quiet buttons have no resting border. Danger actions use danger text; only final destructive confirmation uses a filled danger treatment with a contrast-checked foreground.
- Panel radius 8px. Dialog radius 10px. Spacing multiples of 8px, with 12px allowed inside compact table cells. Focus is a 2px accent outline with 2px offset. Surface dividers may be subtle; interactive boundaries must remain identifiable.

Theme storage key is `evaluation-hub.theme`. Missing/invalid/blocked storage uses System in memory. Apply `data-theme="light|dark"` and matching `color-scheme` on `<html>` before rendering the body; no server-rendered default-light assumption that flashes in dark mode. Follow matchMedia changes only while preference is System. Handle listener cleanup and hydration without warnings. CodeMirror uses a Compartment for theme/highlighting reconfiguration: switching themes must not recreate EditorView, lose document/selection/undo history, or invalidate an otherwise current preview. Map code strings, comments, numbers and keywords to contrast-checked theme colors. Native controls, tool/JSON blocks, selection, gutters, diagnostics and loading states must also switch.

### Shell and responsive geometry

Use `height: 100dvh` for the desktop shell. Sidebar width 224px, collapsed rail 56px. Header 64px, or 56px in the inspector. Primary navigation order is Datasets, Imports, Tags. Bottom utilities are Trash and Appearance. No tag hierarchy or management form remains in the shell. Datasets is the landing route; no new dashboard. Imports remains active for all `/dataset-imports/*` routes. Tags is active for `/tags`. Rail controls keep accessible names and focus/hover labels.

Breakpoints: desktop >=1200px; intermediate 768–1199px; narrow <768px. Desktop gutters 24px, intermediate/narrow 16px. Under 768px the sidebar becomes a modal drawer, initially closed, opened by a labelled Menu button. Closing with Escape or Close restores focus; selecting a destination closes it. Preserve the current desktop collapse preference and inspector-specific default collapse behavior. Do not let drawer state overwrite the desktop preference.

Headers contain title/breadcrumb left and one primary action right. Search/filter controls belong in a second region below, not crammed into the title row. Main content owns scrolling; toolbars remain visible within their region. No double page-height scrolling or sticky controls hiding focus. On narrow screens the title/action region can wrap; it must never clip titles or push actions offscreen.

### Datasets screen and filter-state contract

Screen order is header (Datasets, count, Add dataset), filter toolbar, optional selected-filter row, results. Imports/Trash access is in navigation, not repeated header buttons. Toolbar has a visible Search datasets label and input plus a Tags button showing count. Search input flexes, capped at 480px. Selected filters wrap below it with “Match all selected tags”, Clear filters, and an `aria-live="polite"` results count. No count announcement on unchanged data.

Desktop table column order: Dataset (28%), Source (20%), Rows kept (10%), Retention (12%), Segments (12%), Tags (remaining), Actions (56px). Row height 52px minimum. Dataset name is the actual link; clicking free row space may navigate, but must not cover controls with a stretched pseudo-element. Full processor id and Created timestamp are available in the dataset metadata pane; remove the competing hash line and Created column from this compact catalog. Keep source split/config/revision as one secondary line. Show up to two tag/segment labels then an operable “+N” disclosure exposing the full collection. Truncated names/paths expose full text by focus/click disclosure, not title-only hover.

At widths below 1000px, use dataset cards rather than a minimum-width table that overflows. Each card shows name/link and separate actions, source, rows kept and two tag labels. A labelled Details disclosure contains retention, segments, all tags, creation timestamp and processor id. Desktop and card renderers use the same data and deletion actions.

URL parsing uses `q` and `searchParams.getAll("tag")`. Trim q for matching, compare case-insensitively, ignore empty tag parameters, and deduplicate tags retaining order. Existing manually supplied ancestor-plus-descendant URLs may be evaluated redundantly but must not be silently rewritten on load. Interactive toggles use the confirmed normalization rule below. Each requested tag must exist in the current forest and match some exact dataset assignment or `tag + "/"` descendant. Apply `every` across tags. Unknown tags remain labelled Unavailable and force zero matches. Parent-only dataset assignments remain valid. Toggling a tag removes itself if selected; otherwise remove selected ancestors/descendants and add it. Siblings survive.

Name input updates q using history replace without resetting focus. Tag selection/removal and Clear filters use history push. Omit empty q/tag parameters. Preserve unrelated params. Clear removes q and all tag params; it does not change routes. Back/forward/reload derive visible state from the URL. No debounce timer may overwrite a later tag edit. Derived filtering is render-time, not a setState-in-effect mirror. Keep the root's query-only no-refetch behavior; explicit mutations still revalidate.

Desktop filter panel: anchored 360px wide, maximum viewport minus 32px, maximum height min(480px, available viewport space), search then hierarchical results then Manage tags link. Changes apply immediately; no Apply button. Selected chips stay outside the panel. Below 768px use a full-width modal sheet with Search tags and Done/Close. A chip's remove button and full-value disclosure are separate controls. Empty catalog offers Add dataset. No results retains filters and offers Clear filters. Loading/error must not masquerade as an empty catalog.

### Tags screen and mutation state contract

Use `/tags?selected=<full-path>&q=<tree-search>`. Tree search updates q via history replace; selecting a row pushes selected and preserves q. View datasets uses `/datasets?tag=<encoded-path>`. Tree selection never filters datasets. Search retains ancestors and forces matches open without permanently changing stored expand/collapse choices. Do not clear a valid selected detail simply because search hides its row.

Header: Tags, total tag-node count, New tag. Below: Search tags, then a single bordered workspace. At >=900px, tree pane 320px and detail pane fills the rest with a 24px gutter/padding and a divider. Below 900px stack tree then details; selecting a row scrolls its detail heading into view and focuses it only for explicit row selection. Tree has nested lists, 20px indentation, 44px rows, leading expansion control, leaf-name selection button and right-aligned branch count. Add sub-tag + is a separate trailing action, visible on hover/focus and always on touch. Do not put delete buttons on every row.

Detail order: breadcrumb/full path, leaf name, Directly tagged count, In this branch count, Add sub-tag, View datasets, secondary actions menu. Count distinct active datasets; a dataset tagged to two descendants counts once in the branch. Parent can have direct assignments. No selection shows “Select a tag to manage it”. Invalid selected path shows “This tag no longer exists”, with Clear selection. No tags shows Create your first tag; no search matches is a distinct state with Clear search.

Creation dialog is 480px wide capped at viewport minus 32px. Header “New tag” or “Add sub-tag”; visible Tag name input, parent breadcrumb, optional Change parent tree, inline error, Cancel and Create tag footer. New tag always defaults to no parent. Add sub-tag defaults to row/selected-node path. Changing parent must preserve the typed name and input selection where possible. Reject blank/slash names using existing validation. Keep controlled form values during pending/error. Disable duplicate submit; show Creating… without shifting button width. On success await catalog revalidation, select the returned/constructed path, clear tree q, expand its ancestry, close dialog and focus the selected row. Before submission, Cancel changes nothing; it is unavailable while a mutation request is pending.

Deletion menu offers “Delete tag and sub-tags” and, only when children exist, “Delete grouping and keep sub-tags”. Fetch tagImpact before showing confirmation. Show the full affected path, number of sub-tags and distinct affected datasets. Promotion text explicitly states that children move to the deleted tag's parent and direct assignments to the removed grouping disappear. Dataset records remain. Focus Cancel initially. Fetch/submit errors remain in context; a destination collision never closes the dialog or pretends success. On success revalidate and select nearest surviving parent, or clear selection. Do not silently retarget old dataset-filter URLs after promotion; they remain Unavailable until removed. No undo is promised.

### Inspector screen contract

Desktop header: Datasets breadcrumb/name, compact loaded/kept summary, Row list toggle, Dataset details toggle, dataset action menu. Example controls are in the reader toolbar, not this header. The inspector pane grid is edge-to-edge inside main and has no external horizontal gutter or gap. Pane padding and 1px separators are included in each column's border-box width. Define available width as the grid's measured content-box width after navigation and any parent padding/borders, not viewport width. Use a container query or measured container width for these thresholds.

At viewport widths >=768px, available width >=1048px permits a 264px example index, reader of at least 480px, and optional 304px inline metadata pane (264 + 480 + 304 = 1048, separators included). Between 704px and 1047px available width, use a 224px index plus reader of at least 480px, and open metadata as a 320px modal side sheet capped at viewport minus 32px. Below 704px available width put both index and metadata in separate modal sheets so expanding navigation cannot compress the reader. If a pane is hidden, give its width to the reader. Do not add the general page gutter outside this grid; use internal pane padding instead.

Below 768px viewport width the reader always occupies the workspace regardless of desktop preferences; Examples and Dataset details open separate modal sheets. Selecting an example closes Examples, returns to the reader and focuses its heading. Narrow-screen sheet state is local and must not overwrite persisted desktop pane flags.

Index order: current page range/total; visible Search this page label; search or row-number input; segment-key selector and values; example list; pagination footer. Preserve current page-only search/facet semantics. New page data resets page-local facets as today. j/k navigation and existing bracket/pane shortcuts keep working outside editable controls.

Reader toolbar: “Example N of total”, previous/next labelled buttons, Rendered/JSON segmented choice, Copy. Segment assignments wrap in a compact row below. Conversation reading measure max 80ch, centered within the available reader, 16/1.6 prose. Each message has a role label and restrained bordered region; expand/collapse existing system/thinking details as today. Tools and expected output are distinctly headed sections. Technical values wrap or scroll inside their own blocks rather than widening the viewport. Empty string expected output remains distinguishable from missing output. Metadata pane shows dataset tags/assignment controls then source, processor, dates and segment schema. Preserve exact source messages and existing multimodal rendering.

### Import, jobs, and Trash screen contracts

Wizard header is Add dataset plus breadcrumb, followed by Details / Source / Processor / Review stepper. Completed steps can be revisited; future steps remain disabled until existing guards pass. Form width max 880px for Details/Source/Review, with 24px section gaps; Processor uses full workspace width. Stable footer has Back left and Continue/Import dataset right. Do not hide required errors behind advanced disclosures.

Source essentials are repository and split; Advanced source settings contains config, revision, row limit. Summary always displays changed values. Load sample stays visible outside Advanced. After sampling show pinned revision, expiry, column list, source-column segment checkboxes and raw-row preview. Retain selected-column replacement confirmation behavior for edited code.

Processor at >=1100px uses 40% input / 60% code columns, with preview results below. Under 1100px use Input / Processor / Preview tabs; Processor is initial, and completing Run preview selects Preview. Keep one editor mounted so tab/theme switches preserve undo and selection. The template menu and its replace-code warning sit in the editor header. Run preview is the primary footer action; Continue to review becomes available only on a current valid preview. Keep custom-segment instructions and exact same-key/string-value requirements visible. Execution restrictions can be in a disclosure. Focus the failed diagnostic/summary only after an explicit failed run, never while typing. Review summarizes source, tags, inferred segments, row limit and preview counts with Edit links. Final submit says Import dataset, pending says Starting import….

Jobs list: Dataset, Status/phase, Rows loaded/kept/skipped, Updated, with no prominent raw job UUID. Job detail: name/status, phase, actual counts, safe diagnostic with source row/line, applicable Cancel/Retry/Open dataset action, then collapsed Import specification. Preserve the existing polling cadence and terminal-state behavior. Never show a completion percentage unless known to be accurate. Same-state polls neither announce nor move focus.

Trash header: Trash and active trash count. Table/cards show dataset name, rows kept, Restore, and quiet Delete permanently. Restore is pending-disabled and revalidates on success. Confirm permanent deletion with dataset name, row count and irreversible stored-snapshot removal; Cancel receives initial focus. Keep the row on failure and expose the error next to its actions. Names remain reserved while trashed. Show “Trash is empty” when appropriate. Do not imply tag deletion, source-repository deletion or import-history deletion.

### Overlay, error, and compatibility rules

Use native `<dialog>` with showModal for modal flows/sheets and native popover for nonmodal filters/menus. Modal opening stores the invoker, contains focus and prevents background interaction; Escape equals Cancel before submission or after failure. While any mutation request is pending, including creation, disable Cancel, ignore Escape and prevent dialog dismissal until the request resolves. Do not claim that closing a dialog aborts a server operation. Restore focus to the invoker if present, otherwise to the surviving parent heading/action. Outside clicks dismiss only nonmodal panels. Do not close a creation/destructive dialog from an accidental backdrop click.

Menus expose labelled triggers, expanded state, arrow-key item navigation, Escape/Tab dismissal and focus return. Position from measured trigger/panel bounds so they flip/clamp within the viewport; handle resize/scroll by closing nonmodal panels rather than leaving detached overlays. Never use a hardcoded 120px presumed menu height. If focus leaves by pointer selection of another control, preserve that control's focus.

Mutations remain consumer-owned async operations with finally-based pending cleanup and no automatic retry of destructive calls. Use the existing API client errors. Local-storage failures keep preferences usable in memory. Before showing a data-dependent empty state distinguish loading, failed load, zero catalog items, and zero matches. Dialog validation uses inline messages; multi-field submit failures have a focusable linked error summary. All behavior changes must preserve legacy dataset name routes, dataset id routes and existing position queries.



### Shared control interfaces

Keep native buttons and links separate. Button variants are primary/secondary/quiet/danger, with loading, disabled and normal native button props; loading preserves width and accessible name. Field takes a stable id, visible label, hint/error and the native input/select as its child, wiring described-by and invalid state. SearchField is a controlled text input with a separately labelled Clear button. FilterChip exposes distinct label-disclosure and remove controls. StatusLabel takes the existing domain status and renders its text plus decorative icon. EmptyState takes title, description and optional action. Skeleton reserves the final region's bounds and is hidden from assistive technology.

Dialog takes open, title, description, onClose and content; ConfirmDialog adds confirmLabel, pending, error and async onConfirm. It does not own API calls or retry. Native cancel calls onClose only when not pending. Tag creation uses a controlled model `{name, parent, pending, error}` independent of dialog mounting. No hook/component should need router or catalog access just to render a button, field, chip or dialog.

### Concrete acceptance fixtures

Use a temporary active catalog with Alpha tagged Benchmarks/Reasoning and Language/English, Beta tagged Benchmarks/Tool use and Language/English, Gamma tagged Benchmarks only, and Delta tagged Language/Turkish. Add a trashed dataset tagged Benchmarks/Reasoning. Tree has Benchmarks with Reasoning/Tool use and Language with English/Turkish.

- `/datasets?tag=Benchmarks` yields Alpha/Beta/Gamma and excludes Trash. `?tag=Benchmarks/Reasoning&tag=Language/English` yields Alpha. Adding `q=ALP` still yields Alpha; `q=Beta` yields no matches. BenchmarksX never matches Benchmarks.
- Selecting Benchmarks then Reasoning replaces the parent chip. Selecting Tool use next retains both sibling chips and requires datasets with both assignments. An obsolete `tag=Deleted` yields no matches and a removable Unavailable chip. Back restores the prior filter set exactly.
- Tags details for Benchmarks show Directly tagged = 1 and In this branch = 3. Creating Math under Benchmarks selects Benchmarks/Math, without navigating to Datasets. With new tag directly attached nowhere, its counts are zero.
- Deleting Benchmarks with promotion removes Gamma's Benchmarks assignment, retains Alpha/Beta records and their child assignments at promoted paths, and exposes any path collision without partial success. Deleting the whole subtree removes labels but leaves all datasets. Use separate isolated fixtures for each destructive test.
- Type Python, move the cursor, undo an edit, change theme and switch Processor/Input tabs. Content, cursor/undo and diagnostics survive; theme changes alone never invalidate the preview. Cancelling a replacement or deletion before confirming changes no code or stored data. After any mutation is submitted, its dialog cannot be cancelled until success or failure is reconciled.

### Plan review and rationale record

A fresh-context review of the earlier plan identified 11 missing decisions. This revision embeds the previously external filter contract, screen geometry, route/action migration, control interfaces, post-mutation state, overlay behavior and editor lifecycle. The review suggested independent parent/child filter toggles, but the user's already-confirmed ancestor/descendant replacement rule takes precedence. It suggested debounced typing; immediate replace-based URL updates avoid stale timer writes with the currently local dataset filtering. No broader backend search or design-library migration is implied. A second fresh-context review found only inspector width-accounting and pending-creation cancellation contradictions. The final contract measures the inner grid with border-box separators, and blocks dialog cancellation during every submitted mutation. Both were corrected before handoff.


## Plan

### Implementation unit: shared system, themes, and navigation

Depends on the repository baseline only. Establish the common interface before page-specific changes.

- [x] Implement semantic light/dark tokens, System / Light / Dark persistence and first-paint application, and theme-aware editor highlighting.
- [x] Consolidate buttons, fields, chips, popovers, dialogs, status labels, skeletons, and error/empty states. Replace superseded rules rather than adding another broad override layer.
- [x] Simplify the shell to Datasets, Imports, and Tags navigation, with Trash and theme preference in its utility area. Keep collapse/drawer behavior accessible.
- [x] Render representative populated Datasets, Tags, and inspector layouts in both themes and inspect desktop/narrow screenshots before propagating styles.

Verify theme persistence, system changes, no first-paint flash, keyboard focus, contrast, and editor diagnostics. Record implementation decisions and evidence using show-me-your-work during Build, outside Git by default; keep this plan's checklist current.

### Implementation unit: catalog filtering and Tags management

Depends on the shared system. Follow the self-contained screen and state contracts in Decisions below.

- [x] Add /tags with a searchable hierarchy and selected-node detail panel. Move management state and creation actions out of the shell/catalog and migrate all callers together.
- [x] Implement name search plus multi-tag AND filtering, URL/history behavior, visible removable chips, and the responsive filter popover/sheet.
- [x] Implement top-level/child creation dialogs, impact-confirmed deletion and promotion, labelled direct/branch counts, View datasets links, and predictable selection after mutations.
- [x] Rebalance catalog rows and implement narrow-screen cards while retaining access to every existing field.

Use the agreed dedicated Tags page and dataset filter bar. Name search and multiple tags combine with AND semantics; a parent matches direct and descendant assignments. Full paths remain available. Use the URL, selection, management, creation, deletion, and accessibility contracts in this plan.

Rebalance the catalog table around dataset name, source, row count, and classification. Keep actions in a dedicated narrow column. Make technical hashes secondary expandable details rather than visually competing with names. Long values have operable full-value disclosure rather than title-only recovery. At narrow widths use cards with expandable secondary metadata, retaining access to every current field. No horizontal page overflow.

Verify filtering, query-only navigation, mutation/revalidation, tag hierarchy, collision feedback, and no table movement or clipped menus.

### Implementation unit: dataset inspector

Depends on the shared system and catalog navigation.

- [x] Restyle the index, reading pane, example toolbar, segment facets, and metadata pane according to the behavior below.
- [x] Implement narrow-screen pane switching and clear search scope. Preserve JSON/copy, pagination, metadata editing, and keyboard navigation.

Prioritize reading one example. The desktop layout has a compact example index, a flexible reading pane, and a collapsible metadata pane. Keep example search, segment facets, keyboard hints and index/total discoverable. Persist pane visibility; use an overlay only when a third pane would compress reading width. The global navigation can collapse, while labels on the viewer's main actions remain understandable.

The reading pane visibly separates Conversation, Expected output, Available tools, and Extras. User/assistant/tool messages use clear role labels and restrained styling; preserve supplied system messages and never add synthetic ones. Show technical arguments/results in readable code blocks with independent overflow. Keep JSON view and copy near the example heading. Expose examples navigation, current index/total, and selected segments without squeezing everything into one header.

Distinguish dataset filters from example search and segment facets. Make the current page-only search/facet scope explicit; do not imply full-dataset search without backend support. Preserve page navigation and existing keyboard shortcuts without triggering them inside inputs/editors. On small screens show one primary pane at a time with explicit Examples and Dataset details controls.

Verify actual long and multimodal conversations, tool calls, technical output overflow, pane visibility, page-only facets, and shortcuts inside versus outside inputs/editors.

### Implementation unit: import wizard

Depends on the shared system and reusable tag selection.

- [x] Apply the shared form, step, advanced-settings, and validation patterns to Details, Source, Processor, and Review.
- [x] Implement responsive input/code/output layouts and make preview results, stale state, and code diagnostics clear.
- [x] Preserve source values, sample pinning/expiry, code edits, segment generation, preview invalidation, and submission protections.

Keep four steps: Details, Source, Processor, Review. Use a clear step indicator and stable Back/Continue navigation. Mark completed and current steps with text/icon cues as well as color. Keep source-column segment selection and define custom segments in Python.

Details: dataset name and optional tags. Source: essential coordinates first; put revision/configuration and limits in a clearly labelled advanced section, showing non-default settings in its summary. Preserve all current values and pinned-source behavior. Explain Load sample and show sample freshness in user-facing terms.

Processor: put the editable processor beside sampled input at desktop widths; use labelled tabs for input/code/output at narrow widths. Keep template replacement separate from execution and state explicitly that it replaces code. Make Run preview the primary action here. Explain custom segment entries with a small example. Move sandbox/contract details into a labelled disclosure while retaining essential output requirements beside the editor. Show preview success/failure, row outcomes, and code-location diagnostics close to the affected region.

Review: show concise source, segment, tag, row-limit and preview summaries with Edit links. Require a current valid preview and at least one retained sample row. Use a clear final Import dataset action and readable full-import failure expectations. Never hide constraints required to make an informed submission.

Verify a full sample-to-preview-to-review journey plus validation failures, expired samples, code replacement confirmation, edited form values, and custom segments. No processor or import execution rules change.

### Implementation unit: jobs, Trash, and final consistency

Depends on shared components and the preceding page migrations.

- [x] Restyle job list/detail, real progress counts, failures, cancellation/retry, and specification disclosure.
- [x] Restyle Trash, restore, permanent-deletion confirmation, reserved-name feedback, and empty state.
- [x] Run a bounded final-build route audit in both themes at 375/768/1024/1440px, checking core actions and page overflow; verify representative loading, error and empty states, and remove superseded shell styles.
- [x] Update docs/modules/workbench-design.md, route/workflow documentation, and the code map around the final implementation.

Jobs: a scan-friendly list with dataset name, text-labelled state, phase, row counts, update time, and contextual action. A job detail page emphasizes current phase, real counts and the next available action. Keep full execution specification behind a disclosure. Failures identify the source row/code location when known and offer a clearly labelled retry. Polling must not move focus or repeatedly announce unchanged status.

Trash: use a styled list/table rather than raw buttons. Show name, row count, and Restore; keep Delete permanently a secondary destructive action with explicit confirmation. Explain reserved names contextually. Preserve shared tags and job history. Empty Trash should look like an intentional completed state.

Verify polling does not steal focus, job history handles trashed/purged datasets, and cancelled destructive actions leave data unchanged.

## Verification

- [x] Unit-test name plus AND tags, direct/descendant paths, sibling selections, path boundaries, unknown tags, and duplicate URL parameters.
- [x] Browser-test URL reload/back/forward, query changes, Clear, chip removal/full-path disclosure, management selection, creation, both deletion modes, collisions, and View datasets.
- [x] Verify find/open/read, tag-child creation, deterministic sample/preview/review, failed-job recovery, and Trash/restore with focused browser checks; smoke their routes in both themes.
- [ ] Complete the real-worker sample/preview/import journey in both themes. The isolated sample request returned HTTP 422 with “The isolated operation failed.” A disposable subprocess confirmed that worker isolation calls Linux `prctl`, which is unavailable on this Darwin host; intercepted UI checks do not prove worker execution.
- [x] Smoke populated routes at 375/768/1024/1440px in both themes; inspect representative long-name, deep-tree, code/conversation and open-overlay outputs, plus reduced motion and a 200%-equivalent viewport.
- [ ] Confirm actual browser-controlled 200% zoom. Headless Chromium did not respond to zoom shortcuts; CSS scaling and a 720px viewport at device scale 2 were checked as substitutes.
- [x] Verify representative computed normal-text and control-boundary contrast, 18 keyboard focus targets, modal containment and return in both themes, pending-dialog dismissal, separate row actions, full-path disclosure, and no page overflow in the bounded route smoke. These checks are sampled rather than an exhaustive state audit.
- [x] Verify both explicit theme choices, System changes, reload and first frame, computed editor syntax colors, editor selection/undo and diagnostic/preview state in both themes.
- [x] Run final web type checking, lint, unit tests, build, and focused real API/browser regressions. The real isolated worker journey remains separately unverified above.
- [x] Record visual evidence separately from automated results. Do not mark a unit complete based on compilation or screenshots of empty pages alone.
