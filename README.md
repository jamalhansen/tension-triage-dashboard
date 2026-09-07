# tension-triage-dashboard

Read-only grouped view of unresolved vault tensions, for prep before running `/rethink`.

Built from the spec at `~/vaults/BrainSync/projects/knowledge/tools/04-tension-triage-dashboard.md`.

## Install

```bash
uv tool install /path/to/tension-triage-dashboard
```

## Usage

```bash
tension-dashboard --vault-path ~/vaults/Contexta
```

Scans `ops/tensions/*.md` for `status: active` or `status: pending` tensions,
groups them by shared note reference (exact match), then falls back to
grouping remaining singletons by shared note `domain` (looked up from
`notes/*.md`). Prints clusters and standalones. Writes nothing — triage
decisions still go through `/rethink`.
