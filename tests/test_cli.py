from typer.testing import CliRunner

from tension_triage_dashboard.cli import app

runner = CliRunner()


def _write_vault(tmp_path, tensions=(), notes=()):
    tensions_dir = tmp_path / "ops" / "tensions"
    notes_dir = tmp_path / "notes"
    tensions_dir.mkdir(parents=True)
    notes_dir.mkdir(parents=True)
    for slug, status, note_refs in tensions:
        refs_yaml = "\n".join(f"  - {n}" for n in note_refs)
        (tensions_dir / f"{slug}.md").write_text(
            f"---\ntitle: {slug}\ntype: tension\nstatus: {status}\ncreated: 2026-01-01\nnotes:\n{refs_yaml}\n---\n\nbody\n"
        )
    for slug, domain in notes:
        (notes_dir / f"{slug}.md").write_text(f"---\ndomain: {domain}\n---\nbody\n")
    return tmp_path


class TestScanCommand:
    def test_reports_no_tensions_found(self, tmp_path):
        vault = _write_vault(tmp_path)
        result = runner.invoke(app, ["tensions", "--vault-path", str(vault)])
        assert result.exit_code == 0
        assert "No unresolved tensions found" in result.output

    def test_reports_cluster_and_standalone(self, tmp_path):
        vault = _write_vault(
            tmp_path,
            tensions=[
                ("t1", "active", ["shared", "a"]),
                ("t2", "active", ["shared", "b"]),
                ("t3", "pending", ["unrelated"]),
            ],
        )
        result = runner.invoke(app, ["tensions", "--vault-path", str(vault)])
        assert result.exit_code == 0
        assert "3 unresolved tensions, 1 cluster(s)" in result.output
        assert "CLUSTER" in result.output
        assert "t1.md" in result.output
        assert "t2.md" in result.output
        assert "STANDALONE (1 tension)" in result.output
        assert "t3.md" in result.output

    def test_excludes_resolved_tensions(self, tmp_path):
        vault = _write_vault(
            tmp_path,
            tensions=[("t1", "resolved", ["a", "b"])],
        )
        result = runner.invoke(app, ["tensions", "--vault-path", str(vault)])
        assert result.exit_code == 0
        assert "No unresolved tensions found" in result.output
