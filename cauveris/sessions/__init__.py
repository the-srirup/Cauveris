"""
Cauveris session packages — the round-trippable snapshot of an investigation.

A session package captures one whole workspace: the evidence bundle, the
pipeline stage history, the append-only event log, the incident report and
any repair packages already built for it.  It is saved as a
``cauveris-session/v1`` archive and reloaded through the workspace launcher.

The module is deliberately split the same way ``cauveris/packaging/`` is:

* :mod:`cauveris.sessions.models` — the data model and the format constants
* :mod:`cauveris.sessions.manifest` — the versioned manifest and checksum table
* :mod:`cauveris.sessions.builder` — assembles an archive from live state
* :mod:`cauveris.sessions.storage` — the metadata index and the archives on disk
* :mod:`cauveris.sessions.restore` — rehydrates an archive into a workspace
* :mod:`cauveris.sessions.api_router` — the HTTP surface
"""

from cauveris.sessions.builder import SessionBuilder
from cauveris.sessions.manifest import (
    build_session_manifest,
    checksum_blob,
    manifest_to_yaml,
    parse_checksums,
    parse_manifest,
)
from cauveris.sessions.models import (
    SESSION_MANIFEST_FORMAT,
    SESSION_SCHEMA_VERSION,
    SessionBuildOutcome,
    SessionChecksumError,
    SessionError,
    SessionFormatError,
    SessionImportSummary,
    SessionManifest,
    SessionManifestEntry,
    SessionNotFoundError,
    SessionRecord,
    random_session_id,
)
from cauveris.sessions.restore import SessionRestorer, restore_session
from cauveris.sessions.storage import SessionStore

__all__ = [
    "SESSION_MANIFEST_FORMAT",
    "SESSION_SCHEMA_VERSION",
    "SessionBuildOutcome",
    "SessionBuilder",
    "SessionChecksumError",
    "SessionError",
    "SessionFormatError",
    "SessionImportSummary",
    "SessionManifest",
    "SessionManifestEntry",
    "SessionNotFoundError",
    "SessionRecord",
    "SessionRestorer",
    "SessionStore",
    "build_session_manifest",
    "checksum_blob",
    "manifest_to_yaml",
    "parse_checksums",
    "parse_manifest",
    "random_session_id",
    "restore_session",
]
