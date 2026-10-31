"""
Ingestion controller for processing incident bundles.
"""

import json
import logging
import zipfile
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any
import mimetypes
import shutil
from cauveris.schemas.incident import Incident, EvidenceItem
from cauveris.schemas.base import StatusLabel
from cauveris.security import scan_for_secrets, compute_file_hash, validate_file_size
from cauveris.bundles import resolve_bundle
from cauveris.config import get_settings
from cauveris.inventory.artifact_inventory import ArtifactInventory, ContentTypeDetector
from cauveris.capability.planner import CapabilityPlanner
from cauveris.discovery.repo_discovery import RepositoryDiscovery

logger = logging.getLogger(__name__)


def _parse_datetime_value(value: Any) -> Optional[datetime]:
    """Parse a manifest timestamp (ISO-8601 string or epoch seconds) into a datetime."""
    if value is None or isinstance(value, datetime):
        return value if isinstance(value, datetime) else None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        text = str(value).strip()
        if not text:
            return None
        # YAML may already have parsed the value into a datetime
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            logger.warning(f"Could not parse approximate_time value: {value!r}")
            return None


def extract_zip_safely(zip_path: Path, extract_to: Path) -> List[Path]:
    """
    Safely extract a ZIP file preventing path traversal attacks.

    Args:
        zip_path: Path to the ZIP file
        extract_to: Directory to extract to

    Returns:
        List of extracted file paths
    """
    extracted_files = []
    settings = get_settings()
    extract_to.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        members = zip_ref.infolist()
        if not members:
            raise ValueError("ZIP archive is empty")
        if len(members) > settings.max_archive_members:
            raise ValueError("ZIP archive exceeds the member threshold")
        uncompressed_size = sum(max(0, int(member.file_size)) for member in members)
        if uncompressed_size > settings.max_archive_uncompressed_size:
            raise ValueError("ZIP archive exceeds the uncompressed-size threshold")
        max_file_size = getattr(settings, "max_archive_file_size", 50 * 1024 * 1024)
        for member_info in members:
            member = member_info.filename
            norm_member = member.replace("\\", "/")
            if norm_member.startswith("/") or ".." in norm_member.split("/"):
                raise ValueError(f"Path traversal attempt detected: {member}")

            # Reject symlinks to prevent symlink escape attacks
            is_symlink = (member_info.external_attr >> 16) & 0o170000 == 0o120000
            if is_symlink:
                raise ValueError(f"Symlinks are forbidden in archive: {member}")

            # Per-file size check
            if member_info.file_size > max_file_size:
                raise ValueError(f"File {member} exceeds maximum permitted size")

            member_path = Path(norm_member)
            if len(member_path.parts) > 15:
                raise ValueError(f"Directory nesting exceeds maximum permitted depth: {member}")
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(f"Invalid path in ZIP: {member}")

            safe_path = extract_to / member_path
            try:
                safe_path.resolve().relative_to(extract_to.resolve())
            except ValueError:
                raise ValueError(f"Path traversal attempt detected: {member}")

            if member.endswith("/") or member.endswith("\\"):
                safe_path.mkdir(parents=True, exist_ok=True)
                continue

            safe_path.parent.mkdir(parents=True, exist_ok=True)
            with zip_ref.open(member_info) as source, open(safe_path, "wb") as target:
                shutil.copyfileobj(source, target)

            extracted_files.append(safe_path)

    return extracted_files


class IngestionController:
    """Controls the ingestion and validation of incident bundles."""

    def __init__(self):
        self.settings = get_settings()
        self.temp_dir = Path("./temp_ingestion")
        self.temp_dir.mkdir(exist_ok=True)

    def locate_bundle_path(self, incident: Incident) -> Optional[Path]:
        """
        Resolve the directory containing incident bundle files.

        A path the incident names outright - ``bundle_path``, or the path the
        manifest declares - is trusted as given.  Everything else is a guess,
        and a guess is only accepted when the directory it names belongs to
        *this* incident.

        That distinction is the whole point of the guard.  Without it, an
        incident that shipped no bundle of its own was handed the demo
        bundle's files, and every later stage - the model, the timeline, the
        timeline's evidence - was calibrated on evidence the incident never
        had.  The pipeline would have produced a confident report about
        somebody else's robot.
        """
        return resolve_bundle(
            incident,
            evidence_store_path=self.settings.evidence_store_path,
            require_manifest=False,
        )

    async def process(self, incident: Incident) -> Incident:
        """
        Process an incident bundle: validate, sanitize, checksum, and inventory evidence.

        Args:
            incident: Incident with raw evidence items

        Returns:
            Incident with validated and enriched evidence items
        """
        logger.info(f"Processing incident ingestion: {incident.id}")

        bundle_path = self.locate_bundle_path(incident)
        if bundle_path:
            logger.info(f"Using bundle path: {bundle_path}")
            manifest_file = bundle_path / "manifest.yaml"
            if not manifest_file.exists():
                for alt_name in ("manifest.yml", "manifest.json"):
                    alt_path = bundle_path / alt_name
                    if alt_path.exists():
                        manifest_file = alt_path
                        break

            if manifest_file.exists():
                try:
                    with open(manifest_file, "r", encoding="utf-8") as f:
                        if manifest_file.suffix.lower() == ".json":
                            manifest_data = json.load(f)
                        else:
                            manifest_data = yaml.safe_load(f)
                    if manifest_data and isinstance(manifest_data, dict):
                        # Preserve existing bundle_path / package_sha256 if present
                        if incident.manifest and isinstance(incident.manifest, dict):
                            for k in ("bundle_path", "package_sha256", "uploaded_filename"):
                                if k in incident.manifest and k not in manifest_data:
                                    manifest_data[k] = incident.manifest[k]
                        incident.manifest = manifest_data
                        if not incident.title or incident.title in ("Uploaded Incident", "New Incident"):
                            incident.title = manifest_data.get("title", incident.title)
                        if not incident.description or incident.description in (
                            "Uploaded incident bundle",
                            "Incident uploaded via API",
                        ):
                            incident.description = manifest_data.get(
                                "description", incident.description
                            )
                        # "unknown-system" is a placeholder, not a real value: the
                        # manifest's system_name must win over it so an uploaded
                        # package's real target system propagates everywhere.
                        if not incident.system_name or incident.system_name == "unknown-system":
                            manifest_system = manifest_data.get("system_name")
                            if manifest_system:
                                incident.system_name = manifest_system
                        if not incident.approximate_time:
                            approx_parsed = _parse_datetime_value(
                                manifest_data.get("approximate_time")
                            )
                            if approx_parsed is not None:
                                incident.approximate_time = approx_parsed
                        if not incident.source_repositories:
                            incident.source_repositories = manifest_data.get(
                                "source_repositories", []
                            )
                        if not incident.commit_hash:
                            incident.commit_hash = manifest_data.get(
                                "commit_hash", incident.commit_hash
                            )

                        # Check for required evidence in manifest
                        existing_paths = {item.file_path for item in incident.evidence_items}
                        for req_path in manifest_data.get("required_evidence", []):
                            if req_path not in existing_paths:
                                incident.evidence_items.append(
                                    EvidenceItem(
                                        file_path=req_path,
                                        file_type="application/octet-stream",
                                        size_bytes=0,
                                        checksum_sha256="",
                                        status=StatusLabel.OBSERVED,
                                        is_required=True,
                                    )
                                )
                except Exception as e:
                    logger.warning(f"Error parsing manifest file: {e}")
            else:
                # PHASE 4: SUPPORT ZIP PACKAGES WITHOUT MANIFEST.YAML
                # Detect configuration roots and source roots
                config_roots: List[str] = []
                source_roots: List[str] = []
                for p in bundle_path.rglob("*"):
                    if p.is_file():
                        rel = p.relative_to(bundle_path)
                        parts = rel.parts
                        if len(parts) > 1:
                            root_dir = str(parts[0])
                            ext = p.suffix.lower()
                            if ext in (".yaml", ".yml", ".json", ".toml", ".ini", ".conf", ".cfg"):
                                if root_dir not in config_roots:
                                    config_roots.append(root_dir)
                            elif ext in (".py", ".cpp", ".c", ".h", ".hpp", ".rs", ".go", ".ts", ".js", ".sh"):
                                if root_dir not in source_roots:
                                    source_roots.append(root_dir)

                # Title resolution order:
                # 1. Explicit title provided during upload
                # 2. Uploaded manifest title (checked above, not present here)
                # 3. ZIP filename without extension
                # 4. Incident plus a short backend ID
                resolved_title = None
                if incident.title and incident.title not in ("Uploaded Incident", "New Incident"):
                    resolved_title = incident.title
                elif incident.manifest and incident.manifest.get("uploaded_filename"):
                    raw_fn = incident.manifest.get("uploaded_filename", "")
                    stem = Path(raw_fn).stem
                    if stem:
                        resolved_title = stem.replace("-", " ").replace("_", " ").title()

                if not resolved_title:
                    short_id = incident.id[:8] if incident.id else "0000"
                    resolved_title = f"Incident {short_id}"

                incident.title = resolved_title

                package_sha = getattr(incident, "package_sha256", "") or (
                    incident.manifest.get("package_sha256", "") if incident.manifest else ""
                )
                uploaded_fn = getattr(incident, "_uploaded_filename", None) or (
                    incident.manifest.get("uploaded_filename", "") if incident.manifest else ""
                )

                internal_manifest: Dict[str, Any] = {
                    "incident_id": incident.id,
                    "title": resolved_title,
                    "uploaded_filename": uploaded_fn,
                    "package_sha256": package_sha,
                    "extraction_timestamp": datetime.now(timezone.utc).isoformat(),
                    "detected_configuration_roots": config_roots,
                    "detected_source_roots": source_roots,
                    "warnings": ["Manifest file (manifest.yaml) not found in bundle; internal ingestion manifest generated."],
                    "bundle_path": str(bundle_path),
                }
                incident.manifest = internal_manifest

                # Discover any files on disk not already in evidence_items
                existing_paths = {item.file_path for item in incident.evidence_items}
                for fpath in bundle_path.rglob("*"):
                    if fpath.is_file():
                        rel_path = str(fpath.relative_to(bundle_path)).replace("\\", "/")
                        if rel_path not in existing_paths:
                            incident.evidence_items.append(
                                EvidenceItem(
                                    file_path=rel_path,
                                    file_type=self._detect_file_type(fpath),
                                    size_bytes=fpath.stat().st_size,
                                    checksum_sha256=compute_file_hash(str(fpath)),
                                    status=StatusLabel.OBSERVED,
                                    is_required=False,
                                )
                            )

        # Persist a canonical manifest.yaml into bundles that live in the
        # evidence store, so the incident can be rehydrated from disk after a
        # backend restart even when the uploaded ZIP shipped no manifest of its
        # own (previously the synthesized manifest lived only in memory and the
        # incident 404'd after restart).  Bundles outside the store (e.g. repo
        # demo packages) are treated as read-only and never written to.
        if bundle_path and bundle_path.exists() and isinstance(incident.manifest, dict):
            try:
                store_root = Path(self.settings.evidence_store_path).resolve()
                inside_store = bundle_path.resolve().is_relative_to(store_root)
            except Exception:
                inside_store = False
            if inside_store:
                canonical = bundle_path / "manifest.yaml"
                if not canonical.exists():
                    try:
                        canonical.write_text(
                            yaml.safe_dump(incident.manifest, sort_keys=False, default_flow_style=False),
                            encoding="utf-8",
                        )
                        logger.info(f"Persisted canonical manifest.yaml for incident {incident.id}")
                    except Exception as e:
                        logger.warning(f"Could not persist synthesized manifest for {incident.id}: {e}")
                # Persist ownership in a sidecar (never mutating an original
                # manifest that shipped inside the ZIP) so a rehydrated
                # incident after a backend restart keeps its owner and is not
                # filtered out of list_incidents by the ownership check.
                owner_user = getattr(incident, "_owner_user_id", None)
                owner_org = getattr(incident, "_owner_org_id", None)
                if owner_user is not None or owner_org is not None:
                    try:
                        (bundle_path / ".cauveris-owner.json").write_text(
                            json.dumps(
                                {k: v for k, v in (("owner_user_id", owner_user), ("owner_org_id", owner_org)) if v is not None},
                                indent=2,
                            ),
                            encoding="utf-8",
                        )
                    except Exception as e:
                        logger.warning(f"Could not persist owner sidecar for {incident.id}: {e}")

        # Process each evidence item
        for evidence in incident.evidence_items:
            try:
                await self._process_evidence_item(evidence, bundle_path)
            except Exception as e:
                logger.warning(f"Failed to process evidence {evidence.file_path}: {e}")
                evidence.validation_errors.append(str(e))
                evidence.status = StatusLabel.VALIDATION_FAILED

        # Build dynamic artifact inventory, capability report, and repo discovery if bundle_path exists
        if bundle_path and bundle_path.exists():
            try:
                inventory = ArtifactInventory(bundle_path, incident_id=incident.id)
                entries = inventory.scan()
                incident.artifact_inventory = [e.to_dict() for e in entries]

                # Capability planner
                planner = CapabilityPlanner()
                cap_report = planner.evaluate_bundle(bundle_path, inventory_entries=entries)
                incident.capability_report = cap_report.to_dict()

                # Dynamic repo discovery
                repo_disc = RepositoryDiscovery(bundle_path)
                discovered_repo = repo_disc.discover()
                incident.discovered_repository = discovered_repo.to_dict()
            except Exception as e:
                logger.warning(f"Failed to build artifact inventory / capability report: {e}")

        # Update incident evidence counts
        incident.update_counts()
        logger.info(
            f"Ingestion complete for incident {incident.id} (total={incident.evidence_count}, required={incident.required_evidence_count})"
        )
        return incident

    async def _process_evidence_item(self, evidence: EvidenceItem, bundle_path: Optional[Path]):
        """Process a single evidence item."""
        if bundle_path and bundle_path.exists():
            file_path = bundle_path / evidence.file_path
            if file_path.exists():
                await self._process_existing_file(evidence, file_path)
                return

        # If not found, mark as missing
        evidence.status = StatusLabel.MISSING
        if not evidence.validation_errors:
            evidence.validation_errors.append(f"File not found in bundle: {evidence.file_path}")

    async def _process_existing_file(self, evidence: EvidenceItem, file_path: Path):
        """Process and validate an existing file."""
        try:
            # Update file size
            evidence.size_bytes = file_path.stat().st_size

            # Validate file size
            if not validate_file_size(str(file_path), self.settings.max_upload_size):
                evidence.validation_errors.append(
                    f"File size exceeds limit: {evidence.size_bytes} bytes"
                )
                evidence.status = StatusLabel.VALIDATION_FAILED
                return

            # Compute actual checksum
            evidence.checksum_sha256 = compute_file_hash(str(file_path))

            # Detect and validate file type
            detected_type = self._detect_file_type(file_path)
            if detected_type:
                evidence.file_type = detected_type

            # Scan for secrets in text-based evidence
            secrets_found = []
            if detected_type.startswith("text/") or detected_type in [
                "application/json",
                "application/x-jsonlines",
            ]:
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    secrets_found = scan_for_secrets(content, str(file_path))
                except Exception:
                    pass

            if secrets_found:
                secret_names = [
                    s[0] if isinstance(s, (list, tuple)) else str(s) for s in secrets_found
                ]
                evidence.validation_errors.append(
                    f"Potential secrets detected: {', '.join(set(secret_names))}"
                )
                evidence.status = StatusLabel.SECRETS_DETECTED
            else:
                evidence.status = StatusLabel.OBSERVED

        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            evidence.validation_errors.append(f"Processing error: {str(e)}")
            evidence.status = StatusLabel.VALIDATION_FAILED

    def _detect_file_type(self, file_path: Path) -> str:
        """Detect file MIME type from header or extension safely using ContentTypeDetector."""
        try:
            detected_type, mime_type, _ = ContentTypeDetector.detect(file_path)
            return mime_type or "application/octet-stream"
        except Exception:
            mime_type, _ = mimetypes.guess_type(str(file_path))
            return mime_type or "application/octet-stream"

    async def process_zip_bundle(
        self, zip_path: Path, target_dir: Optional[Path] = None
    ) -> Incident:
        """
        Extract an incident ZIP bundle, build an Incident object, and validate evidence.

        Args:
            zip_path: Path to the uploaded ZIP file
            target_dir: Destination directory for extracted evidence

        Returns:
            Validated Incident object
        """
        if target_dir is None:
            extract_dir = Path(self.settings.evidence_store_path) / zip_path.stem
        else:
            extract_dir = target_dir

        extracted_files = extract_zip_safely(zip_path, extract_dir)

        manifest_data = {}
        for manifest_name in ("manifest.yaml", "manifest.yml", "manifest.json"):
            manifest_file = extract_dir / manifest_name
            if manifest_file.exists():
                try:
                    with open(manifest_file, "r", encoding="utf-8") as f:
                        if manifest_name.endswith(".json"):
                            manifest_data = json.load(f) or {}
                        else:
                            manifest_data = yaml.safe_load(f) or {}
                    break
                except Exception as e:
                    logger.warning(f"Failed to parse manifest: {e}")

        incident_id = manifest_data.get("incident_id", zip_path.stem)
        incident = Incident(
            id=incident_id,
            title=manifest_data.get("title", f"Incident {incident_id}"),
            description=manifest_data.get("description", "Uploaded incident bundle"),
            system_name=manifest_data.get("system_name", "unknown-system"),
            approximate_time=manifest_data.get("approximate_time"),
            source_repositories=manifest_data.get("source_repositories", []),
            commit_hash=manifest_data.get("commit_hash", ""),
            manifest=manifest_data,
            status=StatusLabel.OBSERVED,
        )

        for file_path in extracted_files:
            rel_path = str(file_path.relative_to(extract_dir)).replace("\\", "/")
            is_req = rel_path in manifest_data.get("required_evidence", [])
            evidence = EvidenceItem(
                file_path=rel_path,
                file_type=self._detect_file_type(file_path),
                size_bytes=file_path.stat().st_size,
                checksum_sha256=compute_file_hash(str(file_path)),
                status=StatusLabel.OBSERVED,
                is_required=is_req,
            )
            incident.evidence_items.append(evidence)

        # Run full validation
        await self.process(incident)
        return incident

    async def load_incident_from_store(self, incident_id: str, store_path: Path) -> Incident:
        """
        Load an incident from an existing evidence store directory.

        Args:
            incident_id: The incident ID to load
            store_path: Path to the extracted evidence store directory

        Returns:
            Validated Incident object
        """
        manifest_data = {}
        for manifest_name in ("manifest.yaml", "manifest.yml", "manifest.json"):
            manifest_file = store_path / manifest_name
            if manifest_file.exists():
                try:
                    with open(manifest_file, "r", encoding="utf-8") as f:
                        if manifest_name.endswith(".json"):
                            manifest_data = json.load(f) or {}
                        else:
                            manifest_data = yaml.safe_load(f) or {}
                    break
                except Exception as e:
                    logger.warning(f"Failed to parse manifest: {e}")

        incident = Incident(
            id=incident_id,
            title=manifest_data.get("title", f"Incident {incident_id}"),
            description=manifest_data.get("description", "Loaded from evidence store"),
            system_name=manifest_data.get("system_name", "unknown-system"),
            approximate_time=manifest_data.get("approximate_time"),
            source_repositories=manifest_data.get("source_repositories", []),
            commit_hash=manifest_data.get("commit_hash", ""),
            manifest=manifest_data,
            bundle_path=str(store_path),
            status=StatusLabel.OBSERVED,
        )

        # Build evidence items from all files in the store
        for file_path in store_path.rglob("*"):
            if file_path.is_file() and file_path.name not in ("manifest.yaml", "manifest.yml", "manifest.json", ".cauveris-owner.json"):
                rel_path = str(file_path.relative_to(store_path)).replace("\\", "/")
                is_req = rel_path in manifest_data.get("required_evidence", [])
                evidence = EvidenceItem(
                    file_path=rel_path,
                    file_type=self._detect_file_type(file_path),
                    size_bytes=file_path.stat().st_size,
                    checksum_sha256=compute_file_hash(str(file_path)),
                    status=StatusLabel.OBSERVED,
                    is_required=is_req,
                )
                incident.evidence_items.append(evidence)

        # Run full validation
        await self.process(incident)
        return incident
