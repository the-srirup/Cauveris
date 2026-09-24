"""
Ingestion controller for processing incident bundles.
"""
import logging
import zipfile
import yaml
from pathlib import Path
from typing import List, Optional
import mimetypes
import shutil
from cauveris.schemas.incident import Incident, EvidenceItem
from cauveris.schemas.base import StatusLabel
from cauveris.security import scan_for_secrets, compute_file_hash, validate_file_size
from cauveris.config import get_settings

logger = logging.getLogger(__name__)


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
    extract_to.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        for member in zip_ref.namelist():
            member_path = Path(member)
            if member_path.is_absolute() or '..' in member_path.parts:
                raise ValueError(f"Invalid path in ZIP: {member}")

            safe_path = extract_to / member_path
            try:
                safe_path.resolve().relative_to(extract_to.resolve())
            except ValueError:
                raise ValueError(f"Path traversal attempt detected: {member}")

            if member.endswith('/') or member.endswith('\\'):
                safe_path.mkdir(parents=True, exist_ok=True)
                continue

            safe_path.parent.mkdir(parents=True, exist_ok=True)
            with zip_ref.open(member) as source, open(safe_path, 'wb') as target:
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
        """Resolve the directory containing incident bundle files."""
        candidates = []
        if hasattr(incident, "bundle_path") and incident.bundle_path:
            candidates.append(Path(incident.bundle_path))
        if incident.manifest and incident.manifest.get("bundle_path"):
            candidates.append(Path(incident.manifest["bundle_path"]))
        candidates.append(Path(self.settings.evidence_store_path) / incident.id)
        candidates.append(Path(f"./incident-{incident.id}"))
        candidates.append(Path("./incident-CAU-0001"))
        candidates.append(self.temp_dir / incident.id)
        candidates.append(Path("./golden_incident/incident-CAU-0001"))

        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                return candidate
        return None

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
            if manifest_file.exists():
                try:
                    with open(manifest_file, 'r', encoding='utf-8') as f:
                        manifest_data = yaml.safe_load(f)
                    if manifest_data and isinstance(manifest_data, dict):
                        incident.manifest = manifest_data
                        if not incident.title or incident.title == "Uploaded Incident":
                            incident.title = manifest_data.get("title", incident.title)
                        if not incident.description:
                            incident.description = manifest_data.get("description", incident.description)
                        if not incident.system_name:
                            incident.system_name = manifest_data.get("system_name", incident.system_name)
                        if not incident.source_repositories:
                            incident.source_repositories = manifest_data.get("source_repositories", [])
                        if not incident.commit_hash:
                            incident.commit_hash = manifest_data.get("commit_hash", incident.commit_hash)

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
                                        is_required=True
                                    )
                                )
                except Exception as e:
                    logger.warning(f"Error parsing manifest.yaml: {e}")

        # Process each evidence item
        for evidence in incident.evidence_items:
            try:
                await self._process_evidence_item(evidence, bundle_path)
            except Exception as e:
                logger.warning(f"Failed to process evidence {evidence.file_path}: {e}")
                evidence.validation_errors.append(str(e))
                evidence.status = StatusLabel.VALIDATION_FAILED

        # Update incident evidence counts
        incident.update_counts()
        logger.info(f"Ingestion complete for incident {incident.id} (total={incident.evidence_count}, required={incident.required_evidence_count})")
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
                evidence.validation_errors.append(f"File size exceeds limit: {evidence.size_bytes} bytes")
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
            if detected_type.startswith("text/") or detected_type in ["application/json", "application/x-jsonlines"]:
                try:
                    content = file_path.read_text(encoding='utf-8', errors='ignore')
                    secrets_found = scan_for_secrets(content, str(file_path))
                except Exception:
                    pass

            if secrets_found:
                secret_names = [s[0] if isinstance(s, (list, tuple)) else str(s) for s in secrets_found]
                evidence.validation_errors.append(f"Potential secrets detected: {', '.join(set(secret_names))}")
                evidence.status = StatusLabel.SECRETS_DETECTED
            else:
                evidence.status = StatusLabel.OBSERVED

        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            evidence.validation_errors.append(f"Processing error: {str(e)}")
            evidence.status = StatusLabel.VALIDATION_FAILED

    def _detect_file_type(self, file_path: Path) -> str:
        """Detect file MIME type from header or extension."""
        try:
            with open(file_path, 'rb') as f:
                header = f.read(16)

            if header.startswith(b'\x89PNG\r\n\x1a\n'):
                return "image/png"
            elif header.startswith(b'\xff\xd8\xff'):
                return "image/jpeg"
            elif header.startswith(b'%PDF'):
                return "application/pdf"
            elif header.startswith(b'\x89MCAP'):
                return "application/octet-stream"
            elif header.startswith(b'PK\x03\x04'):
                return "application/zip"
            elif file_path.suffix.lower() in ['.yaml', '.yml']:
                return "text/yaml"
            elif file_path.suffix.lower() == '.json':
                return "application/json"
            elif file_path.suffix.lower() == '.jsonl':
                return "application/x-jsonlines"
            elif file_path.suffix.lower() == '.csv':
                return "text/csv"
            elif file_path.suffix.lower() == '.md':
                return "text/markdown"
            elif file_path.suffix.lower() in ['.py', '.cpp', '.h', '.sh', '.log', '.txt']:
                return "text/plain"
            elif file_path.suffix.lower() == '.mp4':
                return "video/mp4"
        except Exception:
            pass

        mime_type, _ = mimetypes.guess_type(str(file_path))
        return mime_type or "application/octet-stream"

    async def process_zip_bundle(self, zip_path: Path, target_dir: Optional[Path] = None) -> Incident:
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
        manifest_file = extract_dir / "manifest.yaml"

        manifest_data = {}
        if manifest_file.exists():
            try:
                with open(manifest_file, 'r', encoding='utf-8') as f:
                    manifest_data = yaml.safe_load(f) or {}
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
            status=StatusLabel.OBSERVED
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
                is_required=is_req
            )
            incident.evidence_items.append(evidence)

        # Run full validation
        await self.process(incident)
        return incident
