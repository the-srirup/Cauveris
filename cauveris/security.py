"""
Security utilities for Cauveris.
Handles secret scanning, path traversal prevention, and safe operations.
"""
import re
import hashlib
import os
from pathlib import Path
from typing import List, Tuple, Set
import logging

logger = logging.getLogger(__name__)


# Common secret patterns
SECRET_PATTERNS = [
    # API keys
    (r'(?i)api[_-]?key[\s]*[:=][\s]*[\'"]([^\'"]{20,})[\'"]', 'API Key'),
    (r'(?i)access[_-]?token[\s]*[:=][\s]*[\'"]([^\'"]{20,})[\'"]', 'Access Token'),
    (r'(?i)secret[_-]?key[\s]*[:=][\s]*[\'"]([^\'"]{20,})[\'"]', 'Secret Key'),
    # AWS
    (r'AKIA[0-9A-Z]{16}', 'AWS Access Key ID'),
    (r'(?i)aws[_-]?secret[_-]?access[_-]?key[\s]*[:=][\s]*[\'"]([^\'"]{20,})[\'"]', 'AWS Secret Key'),
    # Database URLs
    (r'(?i)(postgres|postgresql|mysql|mongodb)://[^\s\'"]+', 'Database URL'),
    # Generic high-entropy strings that might be secrets
    (r'(?i)(password|passwd|pwd)[\s]*[:=][\s]*[\'"]([^\'"]{8,})[\'"]', 'Password'),
    (r'(?i)private[_-]?key[\s]*[:=]', 'Private Key'),
    (r'-----BEGIN [A-Z ]+PRIVATE KEY-----', 'Private Key Block'),
]


def scan_for_secrets(content: str, filepath: str = "") -> List[Tuple[str, str, int]]:
    """
    Scan content for potential secrets.

    Returns:
        List of (secret_type, matched_text, line_number) tuples
    """
    findings = []
    lines = content.split('\n')

    for i, line in enumerate(lines, 1):
        for pattern, secret_type in SECRET_PATTERNS:
            matches = re.finditer(pattern, line)
            for match in matches:
                # Extract the matched secret value
                if match.groups():
                    secret_value = match.group(1) if match.lastindex and match.lastindex >= 1 else match.group(0)
                else:
                    secret_value = match.group(0)

                findings.append((secret_type, secret_value, i))

    return findings


def redact_secrets(content: str) -> str:
    """
    Redact secrets from content by replacing them with [REDACTED].

    Returns:
        Content with secrets redacted
    """
    redacted = content
    for pattern, _ in SECRET_PATTERNS:
        # Replace with [REDACTED] but preserve formatting
        redacted = re.sub(pattern, '[REDACTED]', redacted, flags=re.IGNORECASE)
    return redacted


def safe_join(base: str, *paths: str) -> Path:
    """
    Safely join paths, preventing directory traversal attacks.

    Args:
        base: Base directory path
        *paths: Path components to join

    Returns:
        Path object resolved within base directory

    Raises:
        ValueError: If path traversal is attempted
    """
    base_path = Path(base).resolve()
    target_path = (base_path / Path(*paths)).resolve()

    # Ensure target is within base
    try:
        target_path.relative_to(base_path)
    except ValueError:
        raise ValueError(f"Path traversal attempt detected: {base} + {paths}")

    return target_path


def compute_file_hash(filepath: str, algorithm: str = "sha256") -> str:
    """
    Compute cryptographic hash of a file.

    Args:
        filepath: Path to file
        algorithm: Hash algorithm (sha256, md5, etc.)

    Returns:
        Hex digest of file hash
    """
    hash_obj = hashlib.new(algorithm)

    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_obj.update(chunk)

    return hash_obj.hexdigest()


def validate_file_type(filename: str, allowed_mime_types: Set[str]) -> bool:
    """
    Validate file type based on extension matching MIME types.

    Args:
        filename: Name of file to check
        allowed_mime_types: Set of allowed MIME types (e.g., {'text/yaml', 'application/json', 'text/csv'})

    Returns:
        True if file extension matches an allowed MIME type
    """
    # Map common extensions to MIME types for validation
    extension_to_mime = {
        '.yaml': 'text/yaml',
        '.yml': 'text/yaml',
        '.json': 'application/json',
        '.csv': 'text/csv',
        '.txt': 'text/plain',
        '.md': 'text/markdown',
        '.py': 'text/x-python',
        '.cpp': 'text/xc++src',
        '.dockerfile': 'text/dockerfile',
        '.mcap': 'application/octet-stream',
        '.mp4': 'video/mp4',
    }

    file_ext = Path(filename).suffix.lower()
    file_mime = extension_to_mime.get(file_ext)

    return file_mime is not None and file_mime in allowed_mime_types


def validate_file_size(filepath: str, max_size_bytes: int) -> bool:
    """
    Validate that file size is within limits.

    Args:
        filepath: Path to file
        max_size_bytes: Maximum allowed size in bytes

    Returns:
        True if file size is within limit
    """
    try:
        return os.path.getsize(filepath) <= max_size_bytes
    except OSError:
        return False
