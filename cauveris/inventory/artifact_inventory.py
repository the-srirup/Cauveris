"""
Artifact Inventory layer and content-based type detection for arbitrary incident bundles.
Does not execute any files during inspection.
"""

from __future__ import annotations

import configparser
import csv
import hashlib
import io
import json
import logging
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from cauveris.security import scan_for_secrets

logger = logging.getLogger(__name__)

# Try import tomllib (Python 3.11+) or tomli fallback
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]


@dataclass
class ArtifactEntry:
    """Detailed record for every artifact discovered in an incident package."""

    relative_path: str
    size_bytes: int
    checksum_sha256: str
    detected_type: str  # content-based format/MIME: json, jsonl, yaml, toml, ini, xml, csv, log, source, trace, metric, compressed, binary
    mime_type: str
    artifact_id: str = ""
    incident_id: Optional[str] = None
    extension_suggested_type: str = ""
    classification: str = "text"  # "text" | "binary"
    encoding: Optional[str] = "utf-8"
    parser_selected: Optional[str] = None
    parser_version: str = "1.0.0"
    parse_status: str = "SUPPORTED"  # SUPPORTED, PARTIALLY_SUPPORTED, UNSUPPORTED, MALFORMED, BINARY, ENCRYPTED, REJECTED, UNKNOWN
    record_count: Optional[int] = None
    warnings: List[str] = field(default_factory=list)
    safe_errors: List[str] = field(default_factory=list)
    sensitivity_flags: List[str] = field(default_factory=list)
    contributes_to_diagnosis: bool = False
    repair_relevance: str = "none"  # "high", "medium", "low", "none"
    is_editable: bool = False
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ContentTypeDetector:
    """
    Safe content-based inspection to determine file type without execution.
    Distinguishes:
    - JSON, JSONL, YAML, TOML, INI/CFG, XML, CSV, plain logs,
    - compressed files (ZIP, GZ, TAR),
    - source code (Python, C/C++, Rust, Go, JS/TS, Java, Shell),
    - traces (OTel, Jaeger, Perfetto, MCAP traces),
    - metrics (Prometheus, CSV metrics, JSON telemetry),
    - binary files.
    """

    MAGIC_NUMBERS = [
        (b"PK\x03\x04", "compressed/zip", "application/zip"),
        (b"\x1f\x8b", "compressed/gzip", "application/gzip"),
        (b"BZh", "compressed/bzip2", "application/x-bzip2"),
        (b"\xfd7zXZ\x00", "compressed/xz", "application/x-xz"),
        (b"\x89PNG\r\n\x1a\n", "image/png", "image/png"),
        (b"\xff\xd8\xff", "image/jpeg", "image/jpeg"),
        (b"%PDF", "document/pdf", "application/pdf"),
        (b"\x89MCAP", "recording/mcap", "application/octet-stream"),
        (b"ROSBAG", "recording/rosbag", "application/octet-stream"),
        (b"\x7fELF", "binary/executable", "application/x-executable"),
        (b"MZ", "binary/executable", "application/x-dosexec"),
    ]

    @classmethod
    def is_binary_content(cls, sample: bytes) -> bool:
        if not sample:
            return False
        # Null bytes or non-text control characters
        if b"\x00" in sample:
            return True
        text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7F})
        nontext = sample.translate(None, text_chars)
        return len(nontext) / len(sample) > 0.30

    @classmethod
    def detect(cls, file_path: Path, sample_bytes: Optional[bytes] = None) -> Tuple[str, str, Optional[str]]:
        """
        Returns: (detected_type, mime_type, encoding)
        Safe and non-executing.
        """
        try:
            if sample_bytes is None:
                with open(file_path, "rb") as f:
                    sample_bytes = f.read(65536)
        except Exception as e:
            logger.warning(f"Failed to read file for type detection {file_path}: {e}")
            return "unknown", "application/octet-stream", None

        # 1. Magic byte matching
        for magic, det_type, mime in cls.MAGIC_NUMBERS:
            if sample_bytes.startswith(magic):
                return det_type, mime, None

        # Tar check
        if len(sample_bytes) >= 262 and sample_bytes[257:262] in (b"ustar", b"GNUtar"):
            return "compressed/tar", "application/x-tar", None

        # 2. Check binary
        if cls.is_binary_content(sample_bytes):
            return "binary", "application/octet-stream", None

        # 3. Decode as text
        encoding = "utf-8"
        text = ""
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                text = sample_bytes.decode(enc)
                encoding = enc
                break
            except UnicodeDecodeError:
                continue

        if not text:
            return "binary", "application/octet-stream", None

        stripped = text.strip()

        # 4. JSON
        if (stripped.startswith("{") and stripped.endswith("}")) or (stripped.startswith("[") and stripped.endswith("]")):
            try:
                json.loads(text)
                # Check if trace or metric
                lowered = text[:2000].lower()
                if any(k in lowered for k in ("spans", "trace_id", "traceid", "resource_spans")):
                    return "trace/json", "application/json", encoding
                if any(k in lowered for k in ("metrics", "timeseries", "datapoints", "telemetry")):
                    return "metric/json", "application/json", encoding
                return "json", "application/json", encoding
            except Exception:
                pass

        # 5. JSONL
        lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
        if len(lines) >= 1 and all(ln.startswith("{") and ln.endswith("}") for ln in lines[:min(5, len(lines))]):
            is_all_json = True
            for ln in lines[:min(10, len(lines))]:
                try:
                    json.loads(ln)
                except Exception:
                    is_all_json = False
                    break
            if is_all_json:
                lowered = stripped[:2000].lower()
                if any(k in lowered for k in ("trace_id", "span_id")):
                    return "trace/jsonl", "application/x-jsonlines", encoding
                if any(k in lowered for k in ("metric", "timestamp", "value")):
                    return "metric/jsonl", "application/x-jsonlines", encoding
                return "jsonl", "application/x-jsonlines", encoding

        # Check for plain logs first before generic INI key/value check
        lowered = stripped[:4000].lower()
        if any(w in lowered for w in ("[info]", "[error]", "[warn]", "[debug]", "error:", "info:", "fatal:", "exception", "traceback")) or file_path.suffix.lower() == ".log":
            return "log", "text/plain", encoding

        # 6. XML
        if stripped.startswith("<?xml") or (stripped.startswith("<") and stripped.endswith(">")):
            try:
                ET.fromstring(text)
                return "xml", "application/xml", encoding
            except Exception:
                pass

        # 7. TOML (require .toml suffix or explicit toml headers)
        if tomllib is not None and file_path.suffix.lower() == ".toml":
            try:
                parsed = tomllib.loads(text)
                if isinstance(parsed, dict):
                    return "toml", "application/toml", encoding
            except Exception:
                pass

        # 8. INI / Properties
        if (file_path.suffix.lower() in (".ini", ".cfg", ".conf") or any(line.startswith("[") and "]" in line for line in lines[:5])):
            try:
                cp = configparser.ConfigParser()
                cp.read_string(text)
                if cp.sections():
                    return "ini", "text/x-ini", encoding
            except Exception:
                pass

        # Java properties check (key=value or key: value, lines start with comments # or !)
        if file_path.suffix.lower() in (".properties", ".prop") or (
            all(
                ln.startswith("#") or ln.startswith("!") or "=" in ln or ":" in ln
                for ln in lines[:min(10, len(lines))]
            )
            and len(lines) > 0
            and not any("{" in ln or "<" in ln for ln in lines[:5])
        ):
            if file_path.suffix.lower() == ".properties":
                return "java_properties", "text/x-java-properties", encoding

        # 9. YAML (Kubernetes / Compose / Generic)
        if (
            file_path.suffix.lower() in (".yaml", ".yml")
            or ":" in stripped
            or stripped.startswith("---")
        ):
            try:
                parsed_yaml = yaml.safe_load(text)
                if isinstance(parsed_yaml, dict):
                    if "apiVersion" in parsed_yaml and "kind" in parsed_yaml:
                        return "yaml/kubernetes", "text/yaml", encoding
                    if "services" in parsed_yaml or "version" in parsed_yaml and ("networks" in parsed_yaml or "volumes" in parsed_yaml):
                        return "yaml/docker-compose", "text/yaml", encoding
                    return "yaml", "text/yaml", encoding
                elif isinstance(parsed_yaml, list):
                    return "yaml", "text/yaml", encoding
            except Exception:
                pass

        # 10. CSV
        if "," in stripped or "\t" in stripped or ";" in stripped:
            try:
                sniffer = csv.Sniffer()
                dialect = sniffer.sniff(text[:4096])
                reader = csv.reader(io.StringIO(text[:4096]), dialect)
                row_lens = [len(r) for r in reader if r]
                if len(row_lens) >= 2 and row_lens[0] > 1 and len(set(row_lens)) == 1:
                    lowered = stripped[:1000].lower()
                    if any(m in lowered for m in ("cpu", "mem", "latenc", "loss", "queue", "rate", "throughput", "wait", "time")):
                        return "metric/csv", "text/csv", encoding
                    return "csv", "text/csv", encoding
            except Exception:
                pass

        # 11. Source Code detection
        suffix = file_path.suffix.lower()
        source_map = {
            ".py": "source/python",
            ".cpp": "source/cpp",
            ".cc": "source/cpp",
            ".cxx": "source/cpp",
            ".c": "source/c",
            ".h": "source/cpp",
            ".hpp": "source/cpp",
            ".rs": "source/rust",
            ".go": "source/go",
            ".js": "source/javascript",
            ".ts": "source/typescript",
            ".tsx": "source/typescript",
            ".jsx": "source/javascript",
            ".java": "source/java",
            ".sh": "source/shell",
            ".bash": "source/shell",
            ".ps1": "source/powershell",
        }
        if suffix in source_map:
            return source_map[suffix], "text/x-source", encoding

        # Content heuristics for source
        if any(w in text for w in ("def ", "import sys", "class ")) and suffix != ".log":
            return "source/python", "text/x-python", encoding
        if any(w in text for w in ("#include <", "int main(", "std::")):
            return "source/cpp", "text/x-c", encoding

        # 12. Logs / Metrics / Plain text
        lowered = stripped[:4000].lower()
        if any(w in lowered for w in ("error", "warn", "info", "debug", "trace", "exception", "failed", "fatal")):
            return "log", "text/plain", encoding
        if any(w in lowered for w in ("# help", "# type", "node_cpu_seconds_total", "http_requests_total")):
            return "metric/prometheus", "text/plain", encoding

        return "text/plain", "text/plain", encoding


class ArtifactInventory:
    """Inventories all files in an incident bundle safely."""

    def __init__(self, bundle_root: Path, incident_id: Optional[str] = None):
        self.bundle_root = Path(bundle_root)
        self.incident_id = incident_id

    def scan(self) -> List[ArtifactEntry]:
        """Scans the bundle root and returns an inventory of all discovered artifacts."""
        entries: List[ArtifactEntry] = []
        if not self.bundle_root.exists() or not self.bundle_root.is_dir():
            return entries

        for p in sorted(self.bundle_root.rglob("*")):
            if not p.is_file():
                continue
            entry = self.inspect_file(p)
            entries.append(entry)
        return entries

    def inspect_file(self, file_path: Path) -> ArtifactEntry:
        rel_path = str(file_path.relative_to(self.bundle_root)).replace("\\", "/")
        try:
            stat = file_path.stat()
            size = stat.st_size
        except Exception:
            size = 0

        # Compute sha256
        h = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                while chunk := f.read(65536):
                    h.update(chunk)
            checksum = h.hexdigest()
        except Exception:
            checksum = ""

        # Content type detection
        detected_type, mime_type, encoding = ContentTypeDetector.detect(file_path)

        # Warnings, secrets, editability & contributor checks
        warnings: List[str] = []
        sensitivity_flags: List[str] = []
        parser_selected: Optional[str] = None
        parse_status = "unparsed"
        record_count: Optional[int] = None
        contributes_to_diag = False
        is_editable = False

        # Secret scanning for text files
        if not detected_type.startswith("binary") and not detected_type.startswith("compressed"):
            try:
                content = file_path.read_text(encoding=encoding or "utf-8", errors="ignore")
                found_secrets = scan_for_secrets(content, str(file_path))
                if found_secrets:
                    for s in found_secrets:
                        sec_label = s[0] if isinstance(s, (list, tuple)) else str(s)
                        sensitivity_flags.append(sec_label)
            except Exception as e:
                warnings.append(f"Secret scan failed: {e}")

        # Determine parser, record count, and parsing status safely
        if detected_type.startswith("jsonl") or detected_type.endswith("/jsonl"):
            parser_selected = "jsonlines"
            try:
                with open(file_path, "r", encoding=encoding or "utf-8", errors="ignore") as f:
                    count = sum(1 for line in f if line.strip())
                record_count = count
                parse_status = "parsed"
                contributes_to_diag = True
            except Exception as e:
                parse_status = "failed"
                warnings.append(f"JSONL parse failed: {e}")
        elif detected_type == "json" or detected_type.endswith("/json"):
            parser_selected = "json"
            try:
                with open(file_path, "r", encoding=encoding or "utf-8", errors="ignore") as f:
                    data = json.load(f)
                record_count = len(data) if isinstance(data, (list, dict)) else 1
                parse_status = "parsed"
                contributes_to_diag = True
                is_editable = isinstance(data, dict)
            except Exception as e:
                parse_status = "failed"
                warnings.append(f"JSON parse failed: {e}")
        elif detected_type.startswith("yaml"):
            parser_selected = "pyyaml"
            try:
                with open(file_path, "r", encoding=encoding or "utf-8", errors="ignore") as f:
                    data = yaml.safe_load(f)
                record_count = len(data) if isinstance(data, (list, dict)) else 1
                parse_status = "parsed"
                contributes_to_diag = True
                is_editable = isinstance(data, dict)
            except Exception as e:
                parse_status = "failed"
                warnings.append(f"YAML parse failed: {e}")
        elif detected_type == "toml":
            parser_selected = "tomllib"
            try:
                if tomllib is not None:
                    with open(file_path, "rb") as f:
                        data = tomllib.load(f)
                    record_count = len(data) if isinstance(data, dict) else 1
                    parse_status = "parsed"
                    is_editable = True
                    contributes_to_diag = True
                else:
                    parse_status = "unsupported"
                    warnings.append("No TOML parser available in environment")
            except Exception as e:
                parse_status = "failed"
                warnings.append(f"TOML parse failed: {e}")
        elif detected_type in ("ini", "java_properties"):
            parser_selected = "configparser" if detected_type == "ini" else "properties_parser"
            parse_status = "parsed"
            is_editable = True
            contributes_to_diag = True
        elif detected_type == "xml":
            parser_selected = "xml.etree.ElementTree"
            try:
                tree = ET.parse(file_path)
                record_count = len(list(tree.iter()))
                parse_status = "parsed"
                contributes_to_diag = True
                is_editable = True
            except Exception as e:
                parse_status = "failed"
                warnings.append(f"XML parse failed: {e}")
        elif detected_type.startswith("csv") or detected_type.startswith("metric/csv"):
            parser_selected = "csv"
            try:
                with open(file_path, "r", encoding=encoding or "utf-8", errors="ignore") as f:
                    record_count = sum(1 for _ in f)
                parse_status = "parsed"
                contributes_to_diag = True
            except Exception as e:
                parse_status = "failed"
                warnings.append(f"CSV read failed: {e}")
        elif detected_type == "log":
            parser_selected = "line_log"
            try:
                with open(file_path, "r", encoding=encoding or "utf-8", errors="ignore") as f:
                    record_count = sum(1 for _ in f)
                parse_status = "parsed"
                contributes_to_diag = True
            except Exception:
                parse_status = "failed"
        elif detected_type.startswith("source/"):
            parser_selected = "source_reader"
            parse_status = "parsed"
            contributes_to_diag = True
            is_editable = True
        elif detected_type.startswith("binary") or detected_type.startswith("compressed"):
            parser_selected = None
            parse_status = "skipped_binary"
            contributes_to_diag = False
            is_editable = False
        else:
            parser_selected = "generic_text"
            parse_status = "parsed"
            contributes_to_diag = ("config" in rel_path.lower() or "log" in rel_path.lower())

        # Determine canonical parse_status
        if detected_type.startswith("binary") or detected_type.startswith("compressed"):
            canonical_status = "BINARY"
        elif parse_status == "failed":
            canonical_status = "MALFORMED"
        elif parse_status == "unsupported":
            canonical_status = "UNSUPPORTED"
        elif warnings:
            canonical_status = "PARTIALLY_SUPPORTED"
        elif parse_status == "parsed":
            canonical_status = "SUPPORTED"
        else:
            canonical_status = "UNKNOWN"

        artifact_id = f"art_{hashlib.sha256(rel_path.encode()).hexdigest()[:12]}"
        classification = "binary" if canonical_status == "BINARY" else "text"
        ext_suggested = file_path.suffix.lower()

        repair_relevance = "none"
        if is_editable:
            if any(k in rel_path.lower() for k in ("config", "setting", "param", "worker.yaml", "limits")):
                repair_relevance = "high"
            else:
                repair_relevance = "medium"
        elif contributes_to_diag:
            repair_relevance = "low"

        return ArtifactEntry(
            relative_path=rel_path,
            size_bytes=size,
            checksum_sha256=checksum,
            detected_type=detected_type,
            mime_type=mime_type,
            artifact_id=artifact_id,
            incident_id=getattr(self, "incident_id", None),
            extension_suggested_type=ext_suggested,
            classification=classification,
            encoding=encoding,
            parser_selected=parser_selected,
            parser_version="1.0.0",
            parse_status=canonical_status,
            record_count=record_count,
            warnings=warnings,
            safe_errors=[w for w in warnings if "failed" in w.lower()],
            sensitivity_flags=sensitivity_flags,
            contributes_to_diagnosis=contributes_to_diag,
            repair_relevance=repair_relevance,
            is_editable=is_editable,
            limitations=[f"Non-editable format {detected_type}"] if not is_editable else [],
        )
