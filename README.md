# tension-triage-dashboard

Read-only vault-health dashboards: unresolved-tension clustering, and map
fragmentation/reciprocity tracking.

Built from the specs at `~/vaults/BrainSync/projects/knowledge/tools/04-tension-triage-dashboard.md`
(tensions) and a 2026-09-07 brainstorm (maps).

## Install

```bash
uv tool install /path/to/tension-triage-dashboard
```

## Configuration

Both commands' `--vault-path` default (and `maps`' `--db-path` default)
resolve via this ecosystem's standard precedence -- CLI flag > env var >
`~/.config/local-first/tension-triage-dashboard.toml` > hardcoded fallback:

```toml
# ~/.config/local-first/tension-triage-dashboard.toml
vault_path = "~/vaults/SomeOtherVault"
db_path = "~/sync/tension-triage-dashboard/map-metrics.db"
```

or via environment variables `TENSION_DASHBOARD_VAULT_PATH` /
`TENSION_DASHBOARD_DB_PATH`. Defaults to `~/vaults/Contexta` if nothing is
set.

**Caveat:** pointing this at a different vault only works if that vault uses
the same conventions Contexta does -- an `ops/tensions/*.md` directory with
`status`/`notes:` frontmatter for `tensions`, and an `Areas:` footer
(`- [[map-name]]`) on notes plus `notes/*-map.md` files for `maps`. This is
Contexta's own schema, parameterized for path -- not a generic "any Obsidian
vault" tool. Pointed at a vault without these conventions, both commands
just report nothing found.

`maps`' snapshot history defaults to `~/sync/tension-triage-dashboard/map-metrics.db`
-- deliberately outside the vault, in the same `~/sync/` (Syncthing) location
this ecosystem already uses for cross-machine tool state (content-discovery-
agent, vault-log, etc.), so trend history follows you across machines instead
of sitting only on whichever one happened to run the check.

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

Every run records one row per map to `--db-path` (SQLite, default
`~/sync/tension-triage-dashboard/map-metrics.db`) unless `--no-snapshot` is
passed. This is the only thing either command writes -- never a note or map
file itself.
