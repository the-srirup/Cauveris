"""
Finding the evidence bundle an incident refers to.

Several stages need the same answer to the same question: *where are the
files this incident actually shipped?*  - the analysis layer that calibrates
the model, the sandbox that branches, the patch forge that diffs, and the
verifier that checks the diff.

They all ask it the same way, so they all ask it here.  The search is by
incident id, never by a fixed path, so an incident uploaded as ``CAU-1234``
is found exactly the way ``CAU-0001`` is.

There are two kinds of answer, and the difference matters:

* an **explicit** path - one the caller passed, or one the incident itself
  declared.  It is trusted as given.
* a **guessed** path - one found by searching the working directory.  A guess
  is only accepted when the directory it names belongs to the incident that
  was asked about.  Accepting a guess that belongs to a *different* incident
  is how a synthetic incident ends up being simulated against the demo
  bundle, and how a patch is verified against files the incident never
  shipped.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable, List, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "resolve_bundle",
    "bundle_has_manifest",
    "bundle_candidates",
    "bundle_incident_id",
    "bundle_manifest_incident_id",
    "bundle_belongs_to",
    "normalise_incident_id",
]


def bundle_has_manifest(path: Path) -> bool:
    """Whether a directory looks like an incident bundle."""
    try:
        return path.is_dir() and (path / "manifest.yaml").exists()
    except OSError:
        return False


def normalise_incident_id(value: Any) -> str:
    """
    The incident id a name denotes.

    ``incident-CAU-0001``, ``CAU-0001`` and ``cau-0001`` all denote the same
    incident, so a comparison between a bundle's name and an incident's id is
    made on the normalised form.
    """
    text = str(value or "").strip()
    if text.lower().startswith("incident-"):
        text = text[len("incident-") :]
    return text.strip().upper()


#: Private alias for readability inside this module.
_normalise_incident_id = normalise_incident_id


def _manifest_incident_id(path: Path) -> str:
    """The incident id a bundle's own manifest declares."""
    manifest = Path(path) / "manifest.yaml"
    try:
        if not manifest.exists():
            return ""
        import yaml

        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    except Exception:
        return ""
    if isinstance(data, dict):
        return _normalise_incident_id(data.get("incident_id"))
    return ""


def bundle_manifest_incident_id(path: Path) -> str:
    """
    The incident id a bundle's manifest declares, or ``""``.

    Unlike :func:`bundle_incident_id` this never falls back to the directory
    name, so a caller that only wants what the bundle *says* about itself
    gets exactly that.
    """
    return _manifest_incident_id(path)


def bundle_incident_id(path: Path) -> str:
    """
    The incident a bundle directory belongs to.

    The manifest is the first answer, because it is the bundle's own
    declaration of which incident it is - and because a customer drops their
    bundle in a directory of their own naming, not one called
    ``incident-<id>``.  The directory name is the second answer, for a bundle
    that has no manifest or whose manifest does not name an incident.
    """
    declared = _manifest_incident_id(path)
    if declared:
        return declared
    try:
        return _normalise_incident_id(Path(path).name)
    except Exception:
        return ""


def bundle_belongs_to(path: Path, incident_id: Any) -> bool:
    """
    Whether a bundle directory is the one an incident refers to.

    A bundle that does not say which incident it belongs to is accepted: it
    was named outright, so its name is not evidence against it.
    """
    wanted = _normalise_incident_id(incident_id)
    if not wanted:
        return True
    owner = bundle_incident_id(path)
    if not owner:
        return True
    return owner == wanted


def _explicit_candidates(
    incident: Optional[Any], bundle_root: Optional[Any]
) -> List[Path]:
    """The paths the caller or the incident named outright."""
    candidates: List[Path] = []
    if bundle_root:
        candidates.append(Path(bundle_root))
    if incident is not None:
        raw = getattr(incident, "bundle_path", None)
        if raw:
            candidates.append(Path(raw))
        manifest = getattr(incident, "manifest", None)
        if isinstance(manifest, dict) and manifest.get("bundle_path"):
            candidates.append(Path(manifest["bundle_path"]))
    return candidates


def _incident_id_of(incident: Optional[Any]) -> str:
    """The id of the incident a bundle is being sought for, as it was written."""
    if incident is None:
        return ""
    return str(getattr(incident, "id", "") or "").strip()


def _guessed_candidates(
    incident_id: str,
    evidence_store_path: Optional[Any],
    search_roots: Optional[Iterable[Path]],
) -> List[Path]:
    """The paths a search of the working directory could turn up."""
    candidates: List[Path] = []

    if incident_id:
        if evidence_store_path:
            candidates.append(Path(evidence_store_path) / incident_id)
        candidates.append(Path(f"./incident-{incident_id}"))
        # The pipeline's own scratch store, where an uploaded bundle lands
        # before it is filed under its incident id.
        candidates.append(Path("./temp_ingestion") / incident_id)

    roots = list(search_roots or [Path(".")])
    for root in roots:
        if incident_id:
            try:
                candidates.extend(sorted(root.glob(f"incident-{incident_id}")))
                candidates.extend(sorted(root.glob(f"*/incident-{incident_id}")))
                candidates.extend(sorted(root.glob(f"*/{incident_id}")))
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


def bundle_candidates(
    incident: Optional[Any] = None,
    bundle_root: Optional[Any] = None,
    *,
    evidence_store_path: Optional[Any] = None,
    search_roots: Optional[Iterable[Path]] = None,
) -> List[Path]:
    """
    Every place the incident's bundle could be, most specific first.

    The explicit answers come first, then the guessed ones.  Only
    :func:`resolve_bundle` decides which of them may be *used*.
    """
    incident_id = _incident_id_of(incident)
    return [
        *_explicit_candidates(incident, bundle_root),
        *_guessed_candidates(incident_id, evidence_store_path, search_roots),
    ]


def _is_bundle(candidate: Path, require_manifest: bool) -> bool:
    """Whether a directory may be used as a bundle."""
    try:
        if not candidate.is_dir():
            return False
    except OSError:
        return False
    if not require_manifest:
        return True
    return bundle_has_manifest(candidate)


def resolve_bundle(
    incident: Optional[Any] = None,
    bundle_root: Optional[Any] = None,
    *,
    evidence_store_path: Optional[Any] = None,
    search_roots: Optional[Iterable[Path]] = None,
    require_manifest: bool = True,
) -> Optional[Path]:
    """
    Locate the incident bundle.

    An explicit path is used as given.  A path found by searching is used
    only when it belongs to the incident being asked about - or when there is
    no incident to ask about, in which case the search result is the best
    answer there is.

    Args:
        incident: The incident the bundle is being sought for.
        bundle_root: An explicit path, trusted as given.
        evidence_store_path: Where filed bundles are kept.
        search_roots: Directories to search for ``incident-*`` directories.
        require_manifest: Whether a bundle must carry a ``manifest.yaml``.
            Stages that read a manifest anyway ask for ``True``; stages that
            merely need the files ask for ``False``.

    Returns:
        The bundle directory, or ``None`` when no bundle can be found.  A
        caller that gets ``None`` has to say so rather than invent an
        incident to work against.
    """
    seen = set()

    def _fresh(candidate: Path) -> bool:
        try:
            key = str(candidate.resolve())
        except OSError:
            key = str(candidate)
        if key in seen:
            return False
        seen.add(key)
        return True

    for candidate in _explicit_candidates(incident, bundle_root):
        if not _fresh(candidate):
            continue
        if _is_bundle(candidate, require_manifest):
            logger.info(f"Using the incident bundle at {candidate}")
            return candidate

    incident_id = _incident_id_of(incident)
    rejected: List[Path] = []
    for candidate in _guessed_candidates(
        incident_id, evidence_store_path, search_roots
    ):
        if not _fresh(candidate):
            continue
        if not _is_bundle(candidate, require_manifest):
            continue
        if incident_id:
            owner = bundle_incident_id(candidate)
            if owner and owner != _normalise_incident_id(incident_id):
                logger.debug(
                    f"Ignoring the bundle at {candidate}: it belongs to incident "
                    f"{owner}, not to {incident_id}."
                )
                rejected.append(candidate)
                continue
        logger.info(f"Using the incident bundle at {candidate}")
        return candidate

    if rejected:
        # One line, not one per directory: an evidence store holds every
        # bundle every incident has ever shipped, and a customer who asks
        # about an incident that has none should get a clear answer rather
        # than a flood of refusals.
        logger.warning(
            f"No bundle found for incident {incident_id}: {len(rejected)} "
            f"candidate(s) belong to other incidents and were ignored."
        )
    return None
