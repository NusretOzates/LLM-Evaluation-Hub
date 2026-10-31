# Tags management and dataset filtering

Status: revised design specification; implementation has not started.

## Goal and locked decisions

Give tag management its own page and keep dataset browsing focused. The sidebar contains Datasets, Imports, and Tags. Dataset filtering combines name search and multiple tags using match-all semantics. Parent tags include descendant assignments; selecting redundant ancestors and descendants keeps only the most recently selected path. Siblings may be selected together. Existing parent-only assignments remain valid.

## Design direction

Apply the local ui-ux-pro-max skill's applicable accessibility, label-overflow, navigation, and React guidance. Its design-system query returned an enterprise landing-page layout even after a narrower retry; discard that result rather than importing marketing-page patterns. Use the dense analyst-workspace direction and paired light/dark theme contract in workbench-redesign.md. Retain IBM Plex Sans, IBM Plex Mono for technical values, Lucide icons, neutral surfaces, and theme-appropriate teal selection/accent tokens. No font, framework, or animation-library replacement; extend the palette through semantic light/dark tokens.

Use flat, clearly separated workspace regions with subtle borders. Reserve shadows for floating surfaces. Teal identifies selection and the primary page action; red identifies destructive actions. Selection also has a checkbox, active navigation marker, or visible border, so color is not the only cue.

Use 8/16/24/32px spacing, 22px page headings, 14px explanatory/control/tree text, 16px long-form reading text, and 12px secondary metadata minimum. Verify both themes independently: normal text at 4.5:1 and meaningful control/focus boundaries at 3:1. Avoid the current faint gray helper text. Desktop gutters are 24px, reducing to 16px on narrow screens. Controls and tree rows have at least 44px hit targets without overlapping adjacent actions. Use 120–180ms opacity/color transitions and disable nonessential motion for reduced-motion users.

## Datasets page

The page header shows Datasets and its result count, a primary Add dataset action, and secondary Import jobs and Trash links. A distinct filter region below has visible labels Search datasets and Tags. Search accepts a case-insensitive trimmed name substring. The Tags trigger displays its selected count.

The Tags popover is a searchable hierarchy, 360px wide capped to viewport minus 32px, with internally scrollable results. It opens at the trigger without reflowing the table. Selections apply immediately and the panel stays open. Show the explanation “Match all selected tags” and a Manage tags link. Search preserves ancestor context and reveals matching branches. Collapse controls and checkboxes are separate accessible controls.

Below the toolbar, show full-path removable chips and Clear filters. Wrap the collection before truncating individual labels. For a path too long for one chip, show its shortened label plus a separate keyboard/touch-operable full-path disclosure; removing a chip remains a distinct labelled action. Never rely only on title tooltips. Announce the updated result count politely without moving focus.

Escape closes the popover and returns focus. Clicking elsewhere closes it without stealing focus from the clicked control. Below 768px, use a modal filter sheet with labelled title, Close button, focus containment, and focus return. On narrow screens, dataset rows become cards with name, source, rows kept, tags, a separate actions button, and an expandable section for retention, segments, and creation date; keep every existing table value available. The page itself must not scroll horizontally.

URL state is q plus repeated tag parameters. Name edits replace history immediately; tag edits and Clear push history, preserving unrelated parameters. Derive results from root-loaded active datasets and defer expensive rendering with React useDeferredValue only if needed; do not add effect-driven duplicate filter state. Existing single-tag URLs work. Unknown tags remain removable Unavailable chips and yield no matches. Zero-result states retain all controls and Clear filters.

## Tags page

Add /tags with Search tags and a primary New tag button. At widths of 900px and above, use a 280–360px hierarchy pane and a flexible detail pane. Below that, stack them, retaining tag selection in /tags?selected=<path>. Tree rows select management context rather than filtering datasets. Use nested lists and ordinary buttons unless implementing the full keyboard contract of ARIA tree widgets.

Tree rows show branch controls, leaf names, and a labelled branch dataset count. Hover/focus reveals a separate Add sub-tag plus; touch shows it persistently. Give each row action enough space instead of squeezing controls into the text. Search retains ancestry. The detail pane shows breadcrumb/full path, Directly tagged and In this branch counts of distinct active datasets, Add sub-tag, View datasets, and a secondary actions menu. Counts are compact labelled facts rather than oversized dashboard tiles.

New tag opens a styled dialog at top level. Add sub-tag preselects its parent and focuses the name. Show a visible Tag name label, parent breadcrumb, optional Change parent tree, Create, and Cancel. Controlled values survive parent changes and request failures. Show pending feedback, disable duplicate submission, and put errors beside their fields. On success, reveal and select the created node; on cancel, return focus to the initiator.

Deletion uses a styled confirmation showing the affected path/subtree and distinct dataset impact. Keep subtree deletion and grouping deletion with child promotion, collision feedback, and explicit reassurance that datasets remain intact. Focus Cancel initially. After successful deletion select the surviving parent or clear selection. Provide creation guidance when empty and a distinct no-search-matches state. Do not add rename, drag-and-drop, or tag Undo in this change.

## Implementation boundaries

Move management state and the creation action from shell/datasets to the Tags feature; migrate callers in the same change. Reuse root catalog data, tag APIs, the hierarchy picker, and shared floating-menu behavior. No backend schema/API changes or data migration. Preserve import-time tag selection, inspector tag assignment, Trash, and all existing uncommitted changes. View datasets links explicitly navigate to the matching single-tag URL.

## Acceptance checks

- Unit tests cover name plus AND tags, direct parent assignments, descendants, siblings, path boundaries, duplicate inputs, and unavailable paths.
- Browser tests cover deep links, back/forward, chip removal and full-value disclosure, search, Clear, popover/sheet focus and dismissal, and distinct zero states.
- Management tests cover top-level/child creation, changing parent without losing input, cancel/failure/pending states, impact counts, both deletion modes, collisions, selection afterward, and View datasets.
- Inspect populated screenshots at 375, 768, 1024, and 1440px with deep trees, long paths, many chips, open overlays, and empty results. Test 200% zoom, keyboard-only operation, reduced motion, and no horizontal page overflow. Verify focus is not obscured and count updates do not steal focus.
- Run web type checking, lint, unit tests, build, focused browser regressions, and update navigation/workflow documentation. Compilation alone is not visual acceptance.
