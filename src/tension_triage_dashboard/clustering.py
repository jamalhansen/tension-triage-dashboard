"""Group unresolved vault tensions by shared note reference (fall back to domain).

Read-only by design -- this only groups an existing pending-tensions list into
clusters so a /rethink pass can tackle related tensions together instead of
hitting each one cold. It never writes, resolves, or dissolves anything.
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter

UNRESOLVED_STATUSES = {"active", "pending"}


@dataclass
class Tension:
    path: Path
    title: str
    status: str
    notes: list[str]

    @property
    def slug(self) -> str:
        return self.path.stem


@dataclass
class Cluster:
    key: str
    tensions: list[Tension] = field(default_factory=list)


def scan_tensions(tensions_dir: Path, on_error=None) -> list[Tension]:
    """Read every tension file, keep only unresolved (active/pending) ones.

    A file with malformed frontmatter is skipped, not fatal -- one bad file
    (e.g. an unescaped quote in a title breaking YAML) shouldn't take down a
    read-only report over everything else. ``on_error(path, exception)`` is
    called for each skip, if provided, so a caller can surface it.
    """
    if not tensions_dir.exists():
        return []

    tensions = []
    for path in sorted(tensions_dir.glob("*.md")):
        try:
            post = frontmatter.load(path)
        except Exception as e:  # noqa: BLE001
            if on_error:
                on_error(path, e)
            continue
        status = post.get("status", "")
        if status not in UNRESOLVED_STATUSES:
            continue
        notes = post.get("notes") or []
        tensions.append(
            Tension(
                path=path,
                title=post.get("title", path.stem),
                status=status,
                notes=list(notes),
            )
        )
    return tensions


def scan_note_domains(notes_dir: Path, slugs: set[str]) -> dict[str, str]:
    """Look up the `domain` frontmatter field for each referenced note slug.

    Only used for the domain-fallback grouping of tensions that share no
    exact note reference with any other tension. Missing notes/fields are
    silently omitted rather than erroring -- a dangling tension reference is
    a separate, already-tracked problem, not this tool's job to flag.
    """
    domains: dict[str, str] = {}
    if not notes_dir.exists():
        return domains
    for slug in slugs:
        note_path = notes_dir / f"{slug}.md"
        if not note_path.exists():
            continue
        try:
            post = frontmatter.load(note_path)
        except Exception as e:  # noqa: BLE001 - a hand-edited note can fail to parse in many ways; skip it, don't crash domain lookup
            print(f"  [skipped] {note_path.name}: {e}", file=sys.stderr)
            continue
        domain = post.get("domain")
        if domain:
            domains[slug] = domain
    return domains


def _union_find_by_shared_note(tensions: list[Tension]) -> list[list[Tension]]:
    """Group tensions that share at least one note reference (exact slug match)."""
    parent: dict[int, int] = {i: i for i in range(len(tensions))}

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    note_to_first_index: dict[str, int] = {}
    for i, t in enumerate(tensions):
        for note in t.notes:
            if note in note_to_first_index:
                union(i, note_to_first_index[note])
            else:
                note_to_first_index[note] = i

    groups: dict[int, list[Tension]] = {}
    for i, t in enumerate(tensions):
        groups.setdefault(find(i), []).append(t)
    return list(groups.values())


def cluster_tensions(
    tensions: list[Tension], note_domains: dict[str, str] | None = None
) -> tuple[list[Cluster], list[Tension]]:
    """Return (clusters, standalones).

    Primary grouping: exact shared note reference. Groups of size 1 are then
    given one more chance via domain fallback (grouping remaining singletons
    that reference notes in the same domain); anything still alone after
    that is a true standalone.
    """
    note_domains = note_domains or {}
    raw_groups = _union_find_by_shared_note(tensions)

    clusters: list[Cluster] = []
    leftover: list[Tension] = []
    for group in raw_groups:
        if len(group) > 1:
            key = " / ".join(sorted({n for t in group for n in t.notes})[:2])
            clusters.append(Cluster(key=key, tensions=group))
        else:
            leftover.extend(group)

    by_domain: dict[str, list[Tension]] = {}
    still_standalone: list[Tension] = []
    for t in leftover:
        domain = next((note_domains[n] for n in t.notes if n in note_domains), None)
        if domain:
            by_domain.setdefault(domain, []).append(t)
        else:
            still_standalone.append(t)

    for domain, group in by_domain.items():
        if len(group) > 1:
            clusters.append(Cluster(key=f"domain: {domain}", tensions=group))
        else:
            still_standalone.extend(group)

    clusters.sort(key=lambda c: len(c.tensions), reverse=True)
    return clusters, still_standalone
