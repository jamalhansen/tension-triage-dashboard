from tension_triage_dashboard.cli import app
from typer.testing import CliRunner

runner = CliRunner()


def _write_vault_with_map(tmp_path, map_content, note_areas=()):
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir(parents=True)
    (notes_dir / "some-map.md").write_text(map_content)
    for slug, maps in note_areas:
        areas_lines = "\n".join(f"- [[{m}]]" for m in maps)
        (notes_dir / f"{slug}.md").write_text(f"body\n\nAreas:\n{areas_lines}\n")
    return tmp_path


class TestMapsCommand:
    def test_no_maps_found(self, tmp_path):
        (tmp_path / "notes").mkdir()
        result = runner.invoke(app, ["maps", "--vault-path", str(tmp_path)])
        assert result.exit_code == 0
        assert "No *-map.md files found" in result.output

    def test_reports_provenance_and_reciprocity(self, tmp_path):
        vault = _write_vault_with_map(
            tmp_path,
            "## Theme A\n- [[n1]]\n\n## Batch (2026-09-07, Source)\n- [[n2]]\n",
            note_areas=[("n1", ["some-map"]), ("n2", ["some-map"]), ("n3", ["some-map"])],
        )
        result = runner.invoke(app, ["maps", "--vault-path", str(vault), "--no-snapshot"])
        assert result.exit_code == 0
        assert "some-map" in result.output
        assert "2 total" in result.output
        assert "1 provenance-named" in result.output
        assert "3 claim, 2 listed, 1 gap" in result.output

    def test_flags_fragmenting_map(self, tmp_path):
        vault = _write_vault_with_map(
            tmp_path,
            "## Batch One (2026-09-01)\n- [[n1]]\n\n## Batch Two (2026-09-02)\n- [[n2]]\n",
        )
        result = runner.invoke(
            app, ["maps", "--vault-path", str(vault), "--no-snapshot", "--fragmenting-ratio", "0.5"]
        )
        assert "[FRAGMENTING]" in result.output

    def test_no_snapshot_flag_does_not_write_db(self, tmp_path):
        vault = _write_vault_with_map(tmp_path, "## Theme\n- [[n1]]\n")
        runner.invoke(app, ["maps", "--vault-path", str(vault), "--no-snapshot"])
        assert not (vault / "ops" / "health" / "map-metrics.db").exists()

    def test_snapshot_recorded_by_default(self, tmp_path):
        vault = _write_vault_with_map(tmp_path, "## Theme\n- [[n1]]\n")
        result = runner.invoke(app, ["maps", "--vault-path", str(vault)])
        assert (vault / "ops" / "health" / "map-metrics.db").exists()
        assert "Recorded 1 snapshot" in result.output

    def test_second_run_shows_trend(self, tmp_path):
        vault = _write_vault_with_map(tmp_path, "## Theme\n- [[n1]]\n")
        from tension_triage_dashboard.map_health import append_snapshot

        db_path = vault / "ops" / "health" / "map-metrics.db"
        append_snapshot(db_path, {
            "date": "2026-09-01", "map": "some-map", "total_sections": 1,
            "provenance_sections": 0, "fragmenting_sections": 0, "fragmentation_ratio": 0.0,
            "claiming": 5, "listed": 1, "gap": 4,
        })
        result = runner.invoke(app, ["maps", "--vault-path", str(vault), "--no-snapshot"])
        assert "trend since 2026-09-01" in result.output
