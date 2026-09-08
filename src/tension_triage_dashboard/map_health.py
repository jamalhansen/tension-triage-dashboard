"""Two map-health checks, both read-only against vault content.

1. Provenance ratio: what fraction of a map's `##` sections are named after
   an ingestion batch (a date or bare year in the heading) instead of a
   theme. This is the root cause tonight's /architect pass found behind
   ai-tools-map/knowledge-map's bloat -- section *count* only trips a
   threshold after fragmentation has already compounded for weeks; this
   catches the fragmentation itself, earlier.
2. Reciprocity trend: how many notes claim a map via their `Areas:` footer
   vs. how many the map actually lists back. A single run only shows the
   current gap; this appends a timestamped snapshot to a log so a later run
   can show whether the gap is closing or widening -- tonight's own
   /architect pass found it had *widened* overnight, which a one-time count
   can't reveal on its own.

The snapshot history is the only thing this module ever writes, and only to
its own dedicated SQLite database (default `ops/health/map-metrics.db`
under the vault) -- never to a note or map file itself. SQLite over a flat
log file to match this ecosystem's existing pattern for exactly this shape
of data (content-discovery-agent's store.db): small structured rows
accumulating over time, where real queries (trend over N runs, which map's
gap is growing fastest) matter more than raw volume ever will here.
"""
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

PROVENANCE_RE = re.compile(r"\((?:[^)]*?(\d{4}-\d{2}-\d{2})[^)]*?|[^)]*?\b(19|20)\d{2}\b[^)]*?)\)")
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)")


@dataclass
class Section:
    heading: str
    link_count: int

    @property
    def is_provenance_named(self) -> bool:
        return bool(PROVENANCE_RE.search(self.heading))


SMALL_SECTION_THRESHOLD = 3  # matches the /architect finding this metric is built from


@dataclass
class ProvenanceReport:
    map_name: str
    sections: list[Section] = field(default_factory=list)

    @property
    def total_sections(self) -> int:
        return len(self.sections)

    @property
    def provenance_sections(self) -> list[Section]:
        """All sections whose heading names a source/date -- naming-convention
        signal only. A large, coherent cluster can be provenance-*named*
        without being fragmentary; see fragmenting_sections for the real
        structural signal."""
        return [s for s in self.sections if s.is_provenance_named]

    @property
    def fragmenting_sections(self) -> list[Section]:
        """Provenance-named AND small (<= SMALL_SECTION_THRESHOLD links) --
        this is the actual fragmentation signal /architect found: growth by
        batch produces many near-empty sections, not one big provenance-
        named one. A 47-link provenance-named section just needs a rename,
        not a split."""
        return [s for s in self.provenance_sections if s.link_count <= SMALL_SECTION_THRESHOLD]

    @property
    def ratio(self) -> float:
        """Fragmentation ratio, based on fragmenting_sections (not just
        provenance-named count) -- this is what should drive a FRAGMENTING
        flag."""
        if not self.sections:
            return 0.0
        return len(self.fragmenting_sections) / len(self.sections)


@dataclass
class ReciprocityReport:
    map_name: str
    claiming: int
    listed: int

    @property
    def gap(self) -> int:
        return self.claiming - self.listed


def find_map_files(notes_dir: Path) -> list[Path]:
    if not notes_dir.exists():
        return []
    return sorted(notes_dir.glob("*-map.md"))


def parse_sections(map_path: Path) -> list[Section]:
    """Split a map file on `## ` headings, count `- [[...]]` links under each."""
    if not map_path.exists():
        return []
    lines = map_path.read_text().split("\n")

    sections: list[Section] = []
    current_heading: str | None = None
    current_links = 0

    def _flush():
        if current_heading is not None:
            sections.append(Section(heading=current_heading, link_count=current_links))

    for line in lines:
        if line.startswith("## "):
            _flush()
            current_heading = line[3:].strip()
            current_links = 0
        elif current_heading is not None and line.strip().startswith("- [["):
            current_links += 1
    _flush()
    return sections


def compute_provenance(map_path: Path) -> ProvenanceReport:
    return ProvenanceReport(map_name=map_path.stem, sections=parse_sections(map_path))


def build_areas_index(notes_dir: Path, on_error=None) -> dict[str, set[str]]:
    """slug -> set of map names claimed via that note's `Areas:` footer."""
    index: dict[str, set[str]] = {}
    if not notes_dir.exists():
        return index

    for path in notes_dir.glob("*.md"):
        try:
            content = path.read_text()
        except Exception as e:  # noqa: BLE001
            if on_error:
                on_error(path, e)
            continue
        areas = _parse_areas_footer(content)
        if areas:
            index[path.stem] = areas
    return index


def _parse_areas_footer(content: str) -> set[str]:
    lines = content.split("\n")
    areas: set[str] = set()
    in_areas = False
    for line in lines:
        stripped = line.strip()
        if stripped == "Areas:":
            in_areas = True
            continue
        if not in_areas:
            continue
        if stripped.startswith("- [["):
            m = WIKILINK_RE.search(stripped)
            if m:
                areas.add(m.group(1))
        elif stripped:
            break  # a non-bullet, non-blank line ends the footer block
    return areas


def compute_reciprocity(map_path: Path, areas_index: dict[str, set[str]]) -> ReciprocityReport:
    map_name = map_path.stem
    claiming_slugs = {slug for slug, maps in areas_index.items() if map_name in maps}

    map_content = map_path.read_text() if map_path.exists() else ""
    listed_slugs = {
        slug for slug in claiming_slugs
        if f"[[{slug}]]" in map_content or f"[[{slug}|" in map_content
    }
    return ReciprocityReport(map_name=map_name, claiming=len(claiming_slugs), listed=len(listed_slugs))


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS map_snapshots (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    date                 TEXT    NOT NULL,
    map                  TEXT    NOT NULL,
    total_sections       INTEGER NOT NULL,
    provenance_sections  INTEGER NOT NULL,
    fragmenting_sections INTEGER NOT NULL,
    fragmentation_ratio  REAL    NOT NULL,
    claiming             INTEGER NOT NULL,
    listed               INTEGER NOT NULL,
    gap                  INTEGER NOT NULL
)
"""


def snapshot_row(provenance: ProvenanceReport, reciprocity: ReciprocityReport) -> dict:
    return {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "map": provenance.map_name,
        "total_sections": provenance.total_sections,
        "provenance_sections": len(provenance.provenance_sections),
        "fragmenting_sections": len(provenance.fragmenting_sections),
        "fragmentation_ratio": round(provenance.ratio, 3),
        "claiming": reciprocity.claiming,
        "listed": reciprocity.listed,
        "gap": reciprocity.gap,
    }


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(_CREATE_TABLE)


def append_snapshot(db_path: Path, row: dict) -> None:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO map_snapshots
                (date, map, total_sections, provenance_sections, fragmenting_sections, fragmentation_ratio, claiming, listed, gap)
            VALUES (:date, :map, :total_sections, :provenance_sections, :fragmenting_sections, :fragmentation_ratio, :claiming, :listed, :gap)
            """,
            row,
        )


def load_snapshots(db_path: Path, map_name: str | None = None) -> list[dict]:
    if not db_path.exists():
        return []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if map_name:
            rows = conn.execute(
                "SELECT * FROM map_snapshots WHERE map = ? ORDER BY date", (map_name,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM map_snapshots ORDER BY date").fetchall()
    return [dict(r) for r in rows]


def previous_snapshot(db_path: Path, map_name: str, before_date: str) -> dict | None:
    """Most recent snapshot for this map strictly before today's date, so a
    second run on the same day doesn't compare against itself."""
    if not db_path.exists():
        return None
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM map_snapshots WHERE map = ? AND date < ? ORDER BY date DESC LIMIT 1",
            (map_name, before_date),
        ).fetchone()
    return dict(row) if row else None
