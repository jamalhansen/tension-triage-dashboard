from pathlib import Path

from tension_triage_dashboard.map_health import (
    Section,
    append_snapshot,
    build_areas_index,
    compute_provenance,
    compute_reciprocity,
    find_map_files,
    load_snapshots,
    parse_sections,
    previous_snapshot,
    snapshot_row,
)


class TestSection:
    def test_provenance_named_with_date(self):
        s = Section(heading="Foo (2026-09-07, Karlsson)", link_count=1)
        assert s.is_provenance_named

    def test_provenance_named_with_bare_year(self):
        s = Section(heading="Foo (Karpathy 2026)", link_count=1)
        assert s.is_provenance_named

    def test_not_provenance_named(self):
        s = Section(heading="Agent Memory Architecture", link_count=5)
        assert not s.is_provenance_named

    def test_not_fooled_by_a_number_that_isnt_a_year(self):
        s = Section(heading="Top 10 Patterns", link_count=3)
        assert not s.is_provenance_named


class TestFindMapFiles:
    def test_finds_map_suffixed_files(self, tmp_path):
        d = tmp_path / "notes"
        d.mkdir()
        (d / "ai-tools-map.md").write_text("# map")
        (d / "some-note.md").write_text("# note")
        result = find_map_files(d)
        assert [p.name for p in result] == ["ai-tools-map.md"]

    def test_missing_dir_returns_empty(self, tmp_path):
        assert find_map_files(tmp_path / "nope") == []


class TestParseSections:
    def test_splits_on_h2_headings(self, tmp_path):
        p = tmp_path / "m.md"
        p.write_text(
            "# Title\n\n## Section A\n- [[note-1]]\n- [[note-2]]\n\n"
            "## Section B\n- [[note-3]]\n"
        )
        sections = parse_sections(p)
        assert [s.heading for s in sections] == ["Section A", "Section B"]
        assert sections[0].link_count == 2
        assert sections[1].link_count == 1

    def test_ignores_links_before_first_heading(self, tmp_path):
        p = tmp_path / "m.md"
        p.write_text("# Title\n- [[stray-link]]\n\n## Real Section\n- [[note-1]]\n")
        sections = parse_sections(p)
        assert len(sections) == 1
        assert sections[0].link_count == 1

    def test_missing_file_returns_empty(self, tmp_path):
        assert parse_sections(tmp_path / "nope.md") == []

    def test_non_link_bullets_not_counted(self, tmp_path):
        p = tmp_path / "m.md"
        p.write_text("## Section\n- just a bullet, no link\n- [[real-link]]\n")
        sections = parse_sections(p)
        assert sections[0].link_count == 1


class TestComputeProvenance:
    def test_ratio_computed_correctly(self, tmp_path):
        p = tmp_path / "some-map.md"
        p.write_text(
            "## Theme A\n- [[n1]]\n\n## Batch (2026-09-07, Source)\n- [[n2]]\n\n"
            "## Theme B\n- [[n3]]\n\n## Another Batch (2026-01-01)\n- [[n4]]\n"
        )
        report = compute_provenance(p)
        assert report.map_name == "some-map"
        assert report.total_sections == 4
        assert len(report.provenance_sections) == 2
        assert report.ratio == 0.5

    def test_no_sections_ratio_is_zero(self, tmp_path):
        p = tmp_path / "empty-map.md"
        p.write_text("# just a title\n")
        report = compute_provenance(p)
        assert report.ratio == 0.0


class TestBuildAreasIndex:
    def test_finds_areas_footer(self, tmp_path):
        d = tmp_path / "notes"
        d.mkdir()
        (d / "n1.md").write_text("body\n\nAreas:\n- [[ai-tools-map]]\n- [[knowledge-map]]\n")
        index = build_areas_index(d)
        assert index["n1"] == {"ai-tools-map", "knowledge-map"}

    def test_notes_without_areas_omitted(self, tmp_path):
        d = tmp_path / "notes"
        d.mkdir()
        (d / "n1.md").write_text("just a body, no areas footer\n")
        index = build_areas_index(d)
        assert "n1" not in index

    def test_stops_at_first_non_bullet_line_after_areas(self, tmp_path):
        d = tmp_path / "notes"
        d.mkdir()
        (d / "n1.md").write_text(
            "Areas:\n- [[map-a]]\nSome trailing prose that is not a bullet\n- [[map-b]]\n"
        )
        index = build_areas_index(d)
        assert index["n1"] == {"map-a"}

    def test_missing_dir_returns_empty(self, tmp_path):
        assert build_areas_index(tmp_path / "nope") == {}

    def test_unreadable_file_skipped_via_on_error(self, tmp_path, monkeypatch):
        d = tmp_path / "notes"
        d.mkdir()
        bad = d / "bad.md"
        bad.write_text("Areas:\n- [[x]]\n")

        original_read_text = Path.read_text

        def _boom(self, *a, **kw):
            if self == bad:
                raise OSError("permission denied")
            return original_read_text(self, *a, **kw)

        monkeypatch.setattr(Path, "read_text", _boom)
        errors = []
        result = build_areas_index(d, on_error=lambda p, e: errors.append(p.name))
        assert result == {}
        assert errors == ["bad.md"]


class TestComputeReciprocity:
    def test_counts_claiming_and_listed(self, tmp_path):
        map_path = tmp_path / "ai-tools-map.md"
        map_path.write_text("## Section\n- [[n1]]\n")
        areas_index = {"n1": {"ai-tools-map"}, "n2": {"ai-tools-map"}, "n3": {"other-map"}}
        report = compute_reciprocity(map_path, areas_index)
        assert report.claiming == 2  # n1, n2
        assert report.listed == 1  # only n1 actually appears in the map
        assert report.gap == 1

    def test_handles_aliased_links(self, tmp_path):
        map_path = tmp_path / "ai-tools-map.md"
        map_path.write_text("## Section\n- [[n1|Display Text]]\n")
        areas_index = {"n1": {"ai-tools-map"}}
        report = compute_reciprocity(map_path, areas_index)
        assert report.listed == 1

    def test_missing_map_file_treated_as_empty(self, tmp_path):
        map_path = tmp_path / "does-not-exist-map.md"
        areas_index = {"n1": {"does-not-exist-map"}}
        report = compute_reciprocity(map_path, areas_index)
        assert report.claiming == 1
        assert report.listed == 0


class TestSnapshotPersistence:
    def test_append_and_load(self, tmp_path):
        db_path = tmp_path / "map-metrics.db"
        row = {
            "date": "2026-09-07", "map": "ai-tools-map", "total_sections": 44,
            "provenance_sections": 13, "fragmenting_sections": 8, "fragmentation_ratio": 0.182,
            "claiming": 698, "listed": 260, "gap": 438,
        }
        append_snapshot(db_path, row)
        loaded = load_snapshots(db_path, map_name="ai-tools-map")
        assert len(loaded) == 1
        assert loaded[0]["gap"] == 438

    def test_load_filters_by_map(self, tmp_path):
        db_path = tmp_path / "map-metrics.db"
        append_snapshot(db_path, {
            "date": "2026-09-07", "map": "map-a", "total_sections": 1,
            "provenance_sections": 0, "fragmenting_sections": 0, "fragmentation_ratio": 0.0,
            "claiming": 1, "listed": 1, "gap": 0,
        })
        append_snapshot(db_path, {
            "date": "2026-09-07", "map": "map-b", "total_sections": 2,
            "provenance_sections": 0, "fragmenting_sections": 0, "fragmentation_ratio": 0.0,
            "claiming": 1, "listed": 1, "gap": 0,
        })
        assert len(load_snapshots(db_path, map_name="map-a")) == 1
        assert len(load_snapshots(db_path)) == 2

    def test_load_missing_db_returns_empty(self, tmp_path):
        assert load_snapshots(tmp_path / "nope.db") == []

    def test_previous_snapshot_excludes_same_day(self, tmp_path):
        db_path = tmp_path / "map-metrics.db"
        append_snapshot(db_path, {
            "date": "2026-09-07", "map": "map-a", "total_sections": 1,
            "provenance_sections": 0, "fragmenting_sections": 0, "fragmentation_ratio": 0.0,
            "claiming": 1, "listed": 1, "gap": 0,
        })
        assert previous_snapshot(db_path, "map-a", "2026-09-07") is None

    def test_previous_snapshot_finds_most_recent_prior(self, tmp_path):
        db_path = tmp_path / "map-metrics.db"
        for d in ["2026-09-01", "2026-09-05"]:
            append_snapshot(db_path, {
                "date": d, "map": "map-a", "total_sections": 1,
                "provenance_sections": 0, "fragmenting_sections": 0, "fragmentation_ratio": 0.0,
                "claiming": 1, "listed": 1, "gap": 0,
            })
        prev = previous_snapshot(db_path, "map-a", "2026-09-07")
        assert prev["date"] == "2026-09-05"

    def test_previous_snapshot_missing_db_returns_none(self, tmp_path):
        assert previous_snapshot(tmp_path / "nope.db", "map-a", "2026-09-07") is None


class TestSnapshotRow:
    def test_shape(self, tmp_path):
        p = tmp_path / "some-map.md"
        p.write_text("## Theme\n- [[n1]]\n")
        provenance = compute_provenance(p)
        reciprocity = compute_reciprocity(p, {"n1": {"some-map"}})
        row = snapshot_row(provenance, reciprocity)
        assert row["map"] == "some-map"
        assert row["total_sections"] == 1
        assert row["claiming"] == 1
        assert row["listed"] == 1
        assert row["gap"] == 0
        assert "date" in row
