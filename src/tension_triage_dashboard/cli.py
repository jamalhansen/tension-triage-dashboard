from pathlib import Path
from typing import Annotated

import typer
from local_first_common.config import get_setting

from .clustering import cluster_tensions, scan_note_domains, scan_tensions
from .map_health import (
    SMALL_SECTION_THRESHOLD,
    append_snapshot,
    build_areas_index,
    compute_provenance,
    compute_reciprocity,
    find_map_files,
    previous_snapshot,
    snapshot_row,
)

TOOL_NAME = "tension-triage-dashboard"

app = typer.Typer(
    name=TOOL_NAME,
    help="Read-only vault-health dashboards: tension clustering and map fragmentation/reciprocity.",
    add_completion=False,
)


def _warn_skip(path: Path, error: Exception) -> None:
    typer.echo(f"  [skipped] {path.name}: {error}", err=True)


def _default_vault_path() -> str:
    """Precedence: env var > ~/.config/local-first/tension-triage-dashboard.toml
    ('vault_path' key) > Contexta, matching every other tool in this ecosystem
    (see local_first_common.config.get_setting). Not hardcoded so this tool
    can be pointed at a different vault without a flag every time -- though
    see the README caveat: it only finds anything on a vault that adopts the
    same ops/tensions/ + notes/Areas: conventions Contexta uses."""
    return get_setting(
        TOOL_NAME, "vault_path",
        env_var="TENSION_DASHBOARD_VAULT_PATH",
        default=str(Path.home() / "vaults" / "Contexta"),
    )


def _default_db_path() -> str:
    return get_setting(
        TOOL_NAME, "db_path",
        env_var="TENSION_DASHBOARD_DB_PATH",
        default=str(Path.home() / "sync" / "tension-triage-dashboard" / "map-metrics.db"),
    )


_DEFAULT_VAULT_PATH = _default_vault_path()
_DEFAULT_DB_PATH = _default_db_path()


@app.command()
def tensions(
    vault_path: Annotated[
        Path,
        typer.Option(
            "--vault-path",
            help="Path to the vault root (expects ops/tensions/ and notes/ under it). "
            "Configurable via TENSION_DASHBOARD_VAULT_PATH or "
            "~/.config/local-first/tension-triage-dashboard.toml's vault_path key.",
        ),
    ] = _DEFAULT_VAULT_PATH,
):
    """Group unresolved tensions by shared note reference, falling back to domain."""
    tensions_dir = vault_path / "ops" / "tensions"
    notes_dir = vault_path / "notes"

    tension_list = scan_tensions(tensions_dir, on_error=_warn_skip)
    if not tension_list:
        typer.echo(f"No unresolved tensions found under {tensions_dir}")
        return

    all_slugs = {n for t in tension_list for n in t.notes}
    note_domains = scan_note_domains(notes_dir, all_slugs)

    clusters, standalones = cluster_tensions(tension_list, note_domains)

    typer.echo(f"{len(tension_list)} unresolved tensions, {len(clusters)} cluster(s)\n")

    for cluster in clusters:
        typer.echo(f"CLUSTER: {cluster.key} ({len(cluster.tensions)} tensions)")
        for t in cluster.tensions:
            notes_str = " <-> ".join(t.notes) if len(t.notes) > 1 else (t.notes[0] if t.notes else "")
            typer.echo(f"  - {t.path.name}  [{notes_str}]")
        typer.echo("")

    if standalones:
        typer.echo(f"STANDALONE ({len(standalones)} tension{'s' if len(standalones) != 1 else ''})")
        for t in standalones:
            typer.echo(f"  - {t.path.name}")


@app.command()
def maps(
    vault_path: Annotated[
        Path,
        typer.Option(
            "--vault-path",
            help="Path to the vault root (expects notes/*-map.md under it). "
            "Configurable via TENSION_DASHBOARD_VAULT_PATH or "
            "~/.config/local-first/tension-triage-dashboard.toml's vault_path key.",
        ),
    ] = _DEFAULT_VAULT_PATH,
    fragmenting_ratio: Annotated[
        float,
        typer.Option(
            "--fragmenting-ratio",
            help="Flag a map as fragmenting if its provenance-named-section ratio is at or above this.",
        ),
    ] = 0.2,
    no_snapshot: Annotated[
        bool,
        typer.Option(
            "--no-snapshot",
            help="Report only -- don't record this run.",
        ),
    ] = False,
    db_path: Annotated[
        Path,
        typer.Option(
            "--db-path",
            help="Where to record snapshots. Deliberately outside the vault, in "
            "~/sync/ (Syncthing), matching content-discovery-agent/vault-log/etc's "
            "convention -- so trend history follows you across machines instead of "
            "sitting only on whichever one happened to run the check. Configurable "
            "via TENSION_DASHBOARD_DB_PATH or the same TOML config's db_path key.",
        ),
    ] = _DEFAULT_DB_PATH,
):
    """Provenance ratio (theme sections vs. ingestion-batch sections) and
    claim/list reciprocity per map, with a trend against the last recorded run."""
    notes_dir = vault_path / "notes"

    map_files = find_map_files(notes_dir)
    if not map_files:
        typer.echo(f"No *-map.md files found under {notes_dir}")
        return

    areas_index = build_areas_index(notes_dir, on_error=_warn_skip)
    today = None

    for map_path in map_files:
        provenance = compute_provenance(map_path)
        reciprocity = compute_reciprocity(map_path, areas_index)
        row = snapshot_row(provenance, reciprocity)
        today = row["date"]

        flag = " [FRAGMENTING]" if provenance.ratio >= fragmenting_ratio else ""
        typer.echo(f"{provenance.map_name}{flag}")
        typer.echo(
            f"  sections: {provenance.total_sections} total, "
            f"{len(provenance.provenance_sections)} provenance-named, "
            f"{len(provenance.fragmenting_sections)} fragmenting "
            f"(provenance-named AND ≤{SMALL_SECTION_THRESHOLD} links) "
            f"({provenance.ratio:.0%})"
        )
        typer.echo(f"  reciprocity: {reciprocity.claiming} claim, {reciprocity.listed} listed, {reciprocity.gap} gap")

        prev = previous_snapshot(db_path, provenance.map_name, today)
        if prev:
            d_sections = row["total_sections"] - prev["total_sections"]
            d_gap = row["gap"] - prev["gap"]
            typer.echo(
                f"  trend since {prev['date']}: sections {d_sections:+d}, gap {d_gap:+d}"
            )
        else:
            typer.echo("  trend: no prior snapshot to compare against")

        if provenance.provenance_sections:
            typer.echo("  provenance-named sections (* = counted as fragmenting):")
            for s in sorted(provenance.provenance_sections, key=lambda s: s.link_count):
                marker = "*" if s in provenance.fragmenting_sections else " "
                typer.echo(f"   {marker}\"{s.heading}\" ({s.link_count} links)")

        typer.echo("")

        if not no_snapshot:
            append_snapshot(db_path, row)

    if not no_snapshot:
        typer.echo(f"Recorded {len(map_files)} snapshot(s) to {db_path}")


if __name__ == "__main__":
    app()
