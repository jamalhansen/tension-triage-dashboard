from pathlib import Path

import pytest

from tension_triage_dashboard.clustering import (
    Tension,
    cluster_tensions,
    scan_note_domains,
    scan_tensions,
)


def _write_tension(dir_: Path, slug: str, status: str, notes: list[str], title: str = "t") -> Path:
    path = dir_ / f"{slug}.md"
    notes_yaml = "\n".join(f"  - {n}" for n in notes)
    path.write_text(
        f"---\ntitle: {title}\ntype: tension\nstatus: {status}\ncreated: 2026-01-01\nnotes:\n{notes_yaml}\n---\n\nbody\n"
    )
    return path


class TestScanTensions:
    def test_includes_active_and_pending(self, tmp_path):
        d = tmp_path / "tensions"
        d.mkdir()
        _write_tension(d, "t1", "active", ["a", "b"])
        _write_tension(d, "t2", "pending", ["c", "d"])
        result = scan_tensions(d)
        assert {t.slug for t in result} == {"t1", "t2"}

    def test_excludes_resolved_and_dissolved(self, tmp_path):
        d = tmp_path / "tensions"
        d.mkdir()
        _write_tension(d, "t1", "resolved", ["a", "b"])
        _write_tension(d, "t2", "dissolved", ["c", "d"])
        _write_tension(d, "t3", "active", ["e", "f"])
        result = scan_tensions(d)
        assert [t.slug for t in result] == ["t3"]

    def test_missing_dir_returns_empty(self, tmp_path):
        assert scan_tensions(tmp_path / "nope") == []

    def test_malformed_frontmatter_is_skipped_not_fatal(self, tmp_path):
        d = tmp_path / "tensions"
        d.mkdir()
        # Unescaped quote followed by trailing text breaks YAML block mapping,
        # same real-world shape found in the vault during development.
        (d / "bad.md").write_text(
            '---\ntitle: "Quoted" trailing text breaks yaml\nstatus: active\nnotes:\n  - a\n---\nbody\n'
        )
        _write_tension(d, "good", "active", ["x", "y"])
        errors = []
        result = scan_tensions(d, on_error=lambda p, e: errors.append(p.name))
        assert [t.slug for t in result] == ["good"]
        assert errors == ["bad.md"]

    def test_handles_single_note_reference(self, tmp_path):
        d = tmp_path / "tensions"
        d.mkdir()
        _write_tension(d, "t1", "active", ["only-one"])
        result = scan_tensions(d)
        assert result[0].notes == ["only-one"]


class TestScanNoteDomains:
    def test_reads_domain_field(self, tmp_path):
        notes_dir = tmp_path / "notes"
        notes_dir.mkdir()
        (notes_dir / "note-a.md").write_text("---\ndomain: knowledge\n---\nbody\n")
        result = scan_note_domains(notes_dir, {"note-a"})
        assert result == {"note-a": "knowledge"}

    def test_missing_note_omitted(self, tmp_path):
        notes_dir = tmp_path / "notes"
        notes_dir.mkdir()
        result = scan_note_domains(notes_dir, {"does-not-exist"})
        assert result == {}

    def test_missing_dir_returns_empty(self, tmp_path):
        assert scan_note_domains(tmp_path / "nope", {"x"}) == {}


class TestClusterTensions:
    def test_groups_tensions_sharing_a_note(self, tmp_path):
        t1 = Tension(path=Path("t1.md"), title="t1", status="active", notes=["shared", "a"])
        t2 = Tension(path=Path("t2.md"), title="t2", status="active", notes=["shared", "b"])
        clusters, standalones = cluster_tensions([t1, t2])
        assert len(clusters) == 1
        assert len(clusters[0].tensions) == 2
        assert standalones == []

    def test_transitively_chains_shared_notes(self, tmp_path):
        t1 = Tension(path=Path("t1.md"), title="t1", status="active", notes=["a", "b"])
        t2 = Tension(path=Path("t2.md"), title="t2", status="active", notes=["b", "c"])
        t3 = Tension(path=Path("t3.md"), title="t3", status="active", notes=["c", "d"])
        clusters, standalones = cluster_tensions([t1, t2, t3])
        assert len(clusters) == 1
        assert len(clusters[0].tensions) == 3

    def test_no_shared_notes_are_standalone(self, tmp_path):
        t1 = Tension(path=Path("t1.md"), title="t1", status="active", notes=["a", "b"])
        t2 = Tension(path=Path("t2.md"), title="t2", status="active", notes=["c", "d"])
        clusters, standalones = cluster_tensions([t1, t2])
        assert clusters == []
        assert len(standalones) == 2

    def test_domain_fallback_groups_standalones(self, tmp_path):
        t1 = Tension(path=Path("t1.md"), title="t1", status="active", notes=["a"])
        t2 = Tension(path=Path("t2.md"), title="t2", status="active", notes=["b"])
        domains = {"a": "knowledge", "b": "knowledge"}
        clusters, standalones = cluster_tensions([t1, t2], domains)
        assert len(clusters) == 1
        assert clusters[0].key == "domain: knowledge"
        assert standalones == []

    def test_domain_fallback_only_applies_to_unclustered(self, tmp_path):
        t1 = Tension(path=Path("t1.md"), title="t1", status="active", notes=["shared"])
        t2 = Tension(path=Path("t2.md"), title="t2", status="active", notes=["shared"])
        t3 = Tension(path=Path("t3.md"), title="t3", status="active", notes=["other"])
        domains = {"shared": "knowledge", "other": "knowledge"}
        clusters, standalones = cluster_tensions([t1, t2, t3], domains)
        # t1/t2 already clustered by shared note; t3 has no domain-fallback partner
        assert len(clusters) == 1
        assert len(clusters[0].tensions) == 2
        assert len(standalones) == 1

    def test_single_unmatched_domain_stays_standalone(self, tmp_path):
        t1 = Tension(path=Path("t1.md"), title="t1", status="active", notes=["a"])
        domains = {"a": "knowledge"}
        clusters, standalones = cluster_tensions([t1], domains)
        assert clusters == []
        assert len(standalones) == 1

    def test_clusters_sorted_by_size_descending(self, tmp_path):
        t1 = Tension(path=Path("t1.md"), title="t1", status="active", notes=["a", "b"])
        t2 = Tension(path=Path("t2.md"), title="t2", status="active", notes=["b", "c"])
        t3 = Tension(path=Path("t3.md"), title="t3", status="active", notes=["x", "y"])
        t4 = Tension(path=Path("t4.md"), title="t4", status="active", notes=["y", "z"])
        t5 = Tension(path=Path("t5.md"), title="t5", status="active", notes=["z", "w"])
        clusters, _ = cluster_tensions([t1, t2, t3, t4, t5])
        assert len(clusters) == 2
        assert len(clusters[0].tensions) >= len(clusters[1].tensions)

    def test_empty_input(self):
        clusters, standalones = cluster_tensions([])
        assert clusters == []
        assert standalones == []
