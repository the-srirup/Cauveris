"""
Ingestion controller for processing incident bundles.
"""
import logging
import zipfile
import json
import yaml
from pathlib import Path
from typing import List
import mimetypes
import shutil
from cauveris.schemas.incident import Incident, EvidenceItem
from cauveris.security import scan_for_secrets, compute_file_hash, validate_file_type, validate_file_size
from cauveris.config import get_settings

logger = logging.getLogger(__name__)


class IngestionController:
    """Controls the ingestion of incident bundles."""

    def __init__(self):
        self.settings = get_settings()
        self.temp_dir = Path("./temp_ingestion")
        self.temp_dir.mkdir(exist_ok=True)

    async def process(self, incident: Incident) -> Incident:
        """
        Process an incident bundle: validate, sanitize, checksum, and inventory evidence.

        Args:
            incident: Incident with raw evidence items (file paths from ZIP upload)

        Returns:
            Incident with validated and enriched evidence items
        """
        logger.info(f"Processing incident: {incident.id}")

        # Clear previous temp directory
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        self.temp_dir.mkdir(exist_ok=True)

        # Process each evidence item
        for evidence in incident.evidence_items:
            try:
                await self._process_evidence_item(evidence)
            except Exception as e:
                logger.warning(f"Failed to process evidence {evidence.file_path}: {e}")
                evidence.validation_errors.append(str(e))
                evidence.status = "VALIDATION_FAILED"

        # Update incident evidence counts
        incident.update_counts()
        logger.info(f"Ingestion complete for incident {incident.id}")
        return incident

    async def _process_evidence_item(self, evidence: EvidenceItem):
        """Process a single evidence item."""
        # For the golden incident demo, we'll look for files in the generated bundle
        bundle_path = Path("./incident-CAU-0001")

        if bundle_path.exists():
            # Look for the file in the golden incident bundle
            file_path = bundle_path / evidence.file_path
            if file_path.exists():
                await self._process_existing_file(evidence, file_path)
                return

        # If we don't find the file, mark as missing
        evidence.status = "MISSING"
        if not evidence.validation_errors:
            evidence.validation_errors.append("File not found in bundle")

    async def _process_existing_file(self, evidence: EvidenceItem, file_path: Path):
        """Process an existing file."""
        try:
            # Validate file type
            if not validate_file_type(file_path, evidence.file_type):
                evidence.validation_errors.append(f"Invalid file type for {evidence.file_path}")
                evidence.status = "VALIDATION_FAILED"
                return

            # Validate file size
            if not validate_file_size(str(file_path), self.settings.max_upload_size):
                evidence.validation_errors.append(f"File size exceeds limits for {evidence.file_path}")
                evidence.status = "VALIDATION_FAILED"
                return

            # Compute actual checksum
            checksum = compute_file_hash(str(file_path))
            evidence.checksum_sha256 = checksum

            # Get actual file size
            evidence.size_bytes = file_path.stat().st_size

            # Scan for secrets
            try:
                with open(str(file_path), 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                secrets_found = scan_for_secrets(content, str(file_path))
            except Exception:
                # If we can't read as text, skip secret scanning
                secrets_found = []
            if secrets_found:
                evidence.validation_errors.append(f"Potential secrets detected: {', '.join(secrets_found)}")
                evidence.status = "SECRETS_DETECTED"
                # For demo, we'll still process it but flag it
                # In production, we might redact or reject

            # Update file type based on actual content if needed
            detected_type = self._detect_file_type(file_path)
            if detected_type:
                evidence.file_type = detected_type

            # Set status based on validation
            if not evidence.validation_errors:
                evidence.status = "OBSERVED"
            else:
                evidence.status = "VALIDATION_FAILED"

            logger.debug(f"Processed evidence {evidence.file_path}: {evidence.status}")

        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            evidence.validation_errors.append(f"Processing error: {str(e)}")
            evidence.status = "PROCESSING_ERROR"

    def _detect_file_type(self, file_path: Path) -> str:
        """Detect file type from content."""
        try:
            # Read first few bytes to detect type
            with open(file_path, 'rb') as f:
                header = f.read(16)

            # Check for common file signatures
            if header.startswith(b'\x89PNG\r\n\x1a\n'):
                return "image/png"
            elif header.startswith(b'\xff\xd8\xff'):
                return "image/jpeg"
            elif header.startswith(b'%PDF'):
                return "application/pdf"
            elif header.startswith(b'\x89MCAP'):
                return "application/octet-stream"  # MCAP
            elif header.startswith(b'PK\x03\x04'):
                return "application/zip"
            elif file_path.suffix.lower() in ['.yaml', '.yml']:
                # Try to parse as YAML to verify
                try:
                    with open(file_path, 'r') as f:
                        yaml.safe_load(f)
                    return "text/yaml"
                except Exception:
                    pass
            elif file_path.suffix.lower() == '.json':
                # Try to parse as JSON
                try:
                    with open(file_path, 'r') as f:
                        json.load(f)
                    return "application/json"
                except Exception:
                    pass
            elif file_path.suffix.lower() == '.csv':
                # Try to parse as CSV
                try:
                    with open(file_path, 'r') as f:
                        # Just check if it looks like CSV
                        first_line = f.readline()
                        if ',' in first_line or '\t' in first_line:
                            return "text/csv"
                except Exception:
                    pass

        except Exception:
            pass

        # Fallback to extension-based detection
        mime_type, _ = mimetypes.guess_type(str(file_path))
        return mime_type or "application/octet-stream"


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

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        for member in zip_ref.namelist():
            # Prevent path traversal
            member_path = Path(member)
            if member_path.is_absolute() or '..' in member_path.parts:
                raise ValueError(f"Invalid path in ZIP: {member}")

            # Construct safe extraction path
            safe_path = extract_to / member_path

            # Ensure the path is still within extract_to
            try:
                safe_path.resolve().relative_to(extract_to.resolve())
            except ValueError:
                raise ValueError(f"Path traversal attempt detected: {member}")

            # Create parent directories if needed
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            # Extract the file
            with zip_ref.open(member) as source, open(safe_path, 'wb') as target:
                target.write(source.read())

            extracted_files.append(safe_path)

    return extracted_files
