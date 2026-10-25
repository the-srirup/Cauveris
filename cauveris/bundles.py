"""
Finding the evidence bundle an incident refers to.

Several stages need the same answer to the same question: *where are the
files this incident actually shipped?*  - the analysis layer that calibrates
the model, the sandbox that branches, the patch forge that diffs, and the
verifier that checks the diff.

They all ask it the same way, so they all ask it here.  The search is by
incident id, never by a fixed path, so an incident uploaded as ``CAU-1234``
is found exactly the way ``CAU-0001`` is.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable, List, Optional

logger = logging.getLogger(__name__)

__all__ = ["resolve_bundle", "bundle_has_manifest", "bundle_candidates"]


def bundle_has_manifest(path: Path) -> bool:
    """Whether a directory looks like an incident bundle."""
    try:
        return path.is_dir() and (path / "manifest.yaml").exists()
    except OSError:
        return False


def bundle_candidates(
    incident: Optional[Any] = None,
    bundle_root: Optional[Any] = None,
    *,
    evidence_store_path: Optional[Any] = None,
    search_roots: Optional[Iterable[Path]] = None,
) -> List[Path]:
    """
    Every place the incident's bundle could be, most specific first.
    """
    candidates: List[Path] = []

    if bundle_root:
        candidates.append(Path(bundle_root))

    incident_id = ""
    if incident is not None:
        raw = getattr(incident, "bundle_path", None)
        if raw:
            candidates.append(Path(raw))
        manifest = getattr(incident, "manifest", None)
        if isinstance(manifest, dict) and manifest.get("bundle_path"):
            candidates.append(Path(manifest["bundle_path"]))
        incident_id = str(getattr(incident, "id", "") or "").strip()

    if incident_id:
        if evidence_store_path:
            candidates.append(Path(evidence_store_path) / incident_id)
        candidates.append(Path(f"./incident-{incident_id}"))

    roots = list(search_roots or [Path(".")])
    for root in roots:
        if incident_id:
            try:
                candidates.extend(sorted(root.glob(f"incident-{incident_id}")))
                candidates.extend(sorted(root.glob(f"*/incident-{incident_id}")))
            except OSError:
                pass
        try:
            candidates.extend(sorted(root.glob("incident-*")))
        except OSError:
            pass
        try:
            candidates.extend(sorted(root.glob("golden_incident/incident-*")))
        except OSError:
            pass

    if evidence_store_path:
        try:
            candidates.extend(sorted(Path(evidence_store_path).glob("*")))
        except OSError:
            pass

    return candidates


def resolve_bundle(
    incident: Optional[Any] = None,
    bundle_root: Optional[Any] = None,
    *,
    evidence_store_path: Optional[Any] = None,
    search_roots: Optional[Iterable[Path]] = None,
) -> Optional[Path]:
    """
    Locate the incident bundle.

    Returns:
        The bundle directory, or ``None`` when no bundle can be found.  A
        caller that gets ``None`` has to say so rather than invent an
        incident to work against.
    """
    seen = set()
    for candidate in bundle_candidates(
        incident,
        bundle_root,
        evidence_store_path=evidence_store_path,
        search_roots=search_roots,
    ):
        try:
            key = str(candidate.resolve())
        except OSError:
            key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if bundle_has_manifest(candidate):
            logger.info(f"Using the incident bundle at {candidate}")
            return candidate
    return None
