from pathlib import Path

import typer

from .clustering import cluster_tensions, scan_note_domains, scan_tensions

app = typer.Typer(
    name="tension-triage-dashboard",
    help="Read-only grouped view of pending vault tensions, for /rethink prep.",
    add_completion=False,
)


@app.command()
def scan(
    vault_path: Path = typer.Option(
        Path.home() / "vaults" / "Contexta",
        "--vault-path",
        help="Path to the vault root (expects ops/tensions/ and notes/ under it).",
    ),
):
    """Group unresolved tensions by shared note reference, falling back to domain."""
    tensions_dir = vault_path / "ops" / "tensions"
    notes_dir = vault_path / "notes"

    def _warn_skip(path: Path, error: Exception) -> None:
        typer.echo(f"  [skipped] {path.name}: {error}", err=True)

    tensions = scan_tensions(tensions_dir, on_error=_warn_skip)
    if not tensions:
        typer.echo(f"No unresolved tensions found under {tensions_dir}")
        return

    all_slugs = {n for t in tensions for n in t.notes}
    note_domains = scan_note_domains(notes_dir, all_slugs)

    clusters, standalones = cluster_tensions(tensions, note_domains)

    typer.echo(f"{len(tensions)} unresolved tensions, {len(clusters)} cluster(s)\n")

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


if __name__ == "__main__":
    app()
