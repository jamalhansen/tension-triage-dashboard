# tension-triage-dashboard

Read-only vault-health dashboards: unresolved-tension clustering, and map
fragmentation/reciprocity tracking.

Built from the specs at `~/vaults/BrainSync/projects/knowledge/tools/04-tension-triage-dashboard.md`
(tensions) and a 2026-09-07 brainstorm (maps).

## Install

```bash
uv tool install /path/to/tension-triage-dashboard
```

## `tensions` — unresolved-tension clustering

```bash
tension-dashboard tensions --vault-path ~/vaults/Contexta
```

Scans `ops/tensions/*.md` for `status: active` or `status: pending` tensions,
groups them by shared note reference (exact match), then falls back to
grouping remaining singletons by shared note `domain` (looked up from
`notes/*.md`). Prints clusters and standalones. Writes nothing — triage
decisions still go through `/rethink`.

## `maps` — provenance ratio and reciprocity trend

```bash
tension-dashboard maps --vault-path ~/vaults/Contexta
```

For every `notes/*-map.md` file:

- **Provenance ratio**: what fraction of its `##` sections are named after an
  ingestion batch (a date or bare year in the heading, e.g. `## Foo
  (2026-09-07, Some Source)`) instead of a theme. High ratio means the map is
  fragmenting -- growing by batch, not by idea -- which section-count alone
  won't show until it's already tripped a threshold. Flags a map
  `[FRAGMENTING]` at or above `--fragmenting-ratio` (default 0.2).
- **Reciprocity**: how many notes claim the map via their `Areas:` footer vs.
  how many the map actually lists back, plus the gap.
- **Trend**: compares this run against the most recent prior snapshot for
  that map, so a widening gap or growing section count shows up even though
  either metric alone is just a snapshot.

Every run records one row per map to `ops/health/map-metrics.db` (SQLite,
matching this ecosystem's convention for this shape of data) unless
`--no-snapshot` is passed. This is the only thing either command writes --
never a note or map file itself.
