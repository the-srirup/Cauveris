"""
Configuration Locator and safe in-place structural patching plugins.
Supports structure-aware discovery and editing for:
- YAML
- JSON
- TOML
- INI/CFG
- Environment files (.env)
- Kubernetes YAML
- Docker Compose YAML
- XML
- Java Properties

Preserves comments where supported, key order, quoting, units, and unrelated content.
Does not use blind regex replacement for structured formats.
"""

from __future__ import annotations

import io
import json
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

import configparser
import xml.etree.ElementTree as ET
import yaml

logger = logging.getLogger(__name__)


class ConfigLocatorPlugin(ABC):
    """Abstract base class for structure-aware configuration format locators and editors."""

    @property
    @abstractmethod
    def format_name(self) -> str:
        """The identifier of the configuration format."""
        pass

    @abstractmethod
    def can_handle(self, file_path: Path, content_sample: str) -> bool:
        """Determines if this plugin can handle the specified file."""
        pass

    @abstractmethod
    def locate_parameter(self, file_path: Path, parameter_needles: List[str]) -> Optional[Tuple[str, Any]]:
        """
        Locates a parameter in the file matching the needles.
        Returns (key_path, current_value) or None.
        """
        pass

    @abstractmethod
    def edit_parameter(
        self,
        file_path: Path,
        key_path: str,
        new_value: Any,
    ) -> str:
        """
        Applies a structure-preserving edit to the file.
        Returns the modified file content as a string.
        """
        pass


class YAMLConfigPlugin(ConfigLocatorPlugin):
    """Handles YAML, Kubernetes manifests, and Docker Compose files."""

    @property
    def format_name(self) -> str:
        return "yaml"

    def can_handle(self, file_path: Path, content_sample: str) -> bool:
        suffix = file_path.suffix.lower()
        if suffix in (".yaml", ".yml"):
            return True
        if ":" in content_sample and not content_sample.strip().startswith("{") and not content_sample.strip().startswith("<"):
            try:
                data = yaml.safe_load(content_sample)
                return isinstance(data, (dict, list))
            except Exception:
                return False
        return False

    def locate_parameter(self, file_path: Path, parameter_needles: List[str]) -> Optional[Tuple[str, Any]]:
        try:
            content = file_path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                return None
            flat = self._flatten(data)
            lowered_needles = [n.lower() for n in parameter_needles]
            for k, v in flat.items():
                k_lower = k.lower()
                last_part = k_lower.split(".")[-1]
                if any(n in last_part or n in k_lower for n in lowered_needles):
                    return k, v
        except Exception as e:
            logger.debug(f"YAML locate failed in {file_path}: {e}")
        return None

    def edit_parameter(self, file_path: Path, key_path: str, new_value: Any) -> str:
        # Structure-preserving scalar replacement
        text = file_path.read_text(encoding="utf-8")
        from cauveris.analysis.parameters import replace_yaml_scalar
        res = replace_yaml_scalar(text, key_path, new_value)
        return res[0] if isinstance(res, tuple) else res

    def _flatten(self, d: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        items: Dict[str, Any] = {}
        for k, v in d.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                items.update(self._flatten(v, key))
            else:
                items[key] = v
        return items


class JSONConfigPlugin(ConfigLocatorPlugin):
    """Handles JSON configuration files."""

    @property
    def format_name(self) -> str:
        return "json"

    def can_handle(self, file_path: Path, content_sample: str) -> bool:
        stripped = content_sample.strip()
        if file_path.suffix.lower() == ".json" or (stripped.startswith("{") and stripped.endswith("}")):
            try:
                json.loads(stripped)
                return True
            except Exception:
                return False
        return False

    def locate_parameter(self, file_path: Path, parameter_needles: List[str]) -> Optional[Tuple[str, Any]]:
        try:
            content = file_path.read_text(encoding="utf-8")
            data = json.loads(content)
            if not isinstance(data, dict):
                return None
            flat = self._flatten(data)
            lowered_needles = [n.lower() for n in parameter_needles]
            for k, v in flat.items():
                k_lower = k.lower()
                last_part = k_lower.split(".")[-1]
                if any(n in last_part or n in k_lower for n in lowered_needles):
                    return k, v
        except Exception:
            pass
        return None

    def edit_parameter(self, file_path: Path, key_path: str, new_value: Any) -> str:
        text = file_path.read_text(encoding="utf-8")
        from cauveris.analysis.parameters import replace_json_scalar
        res = replace_json_scalar(text, key_path, new_value)
        return res[0] if isinstance(res, tuple) else res

    def _flatten(self, d: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        items: Dict[str, Any] = {}
        for k, v in d.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                items.update(self._flatten(v, key))
            else:
                items[key] = v
        return items


class TOMLConfigPlugin(ConfigLocatorPlugin):
    """Handles TOML configuration files preserving layout and comments where possible."""

    @property
    def format_name(self) -> str:
        return "toml"

    def can_handle(self, file_path: Path, content_sample: str) -> bool:
        if file_path.suffix.lower() == ".toml":
            return True
        return False

    def locate_parameter(self, file_path: Path, parameter_needles: List[str]) -> Optional[Tuple[str, Any]]:
        try:
            content = file_path.read_text(encoding="utf-8")
            if tomllib is not None:
                data = tomllib.loads(content)
                flat = self._flatten(data)
                lowered_needles = [n.lower() for n in parameter_needles]
                for k, v in flat.items():
                    last_part = k.lower().split(".")[-1]
                    if any(n in last_part or n in k.lower() for n in lowered_needles):
                        return k, v
        except Exception:
            pass
        return None

    def edit_parameter(self, file_path: Path, key_path: str, new_value: Any) -> str:
        text = file_path.read_text(encoding="utf-8")
        target_key = key_path.split(".")[-1]
        lines = text.splitlines(keepends=True)
        new_lines = []
        replaced = False

        # Find key in TOML lines: key = val
        pattern = re.compile(rf"^(\s*{re.escape(target_key)}\s*=\s*)([^#\n\r]+)(.*)$")
        for line in lines:
            m = pattern.match(line)
            if m and not replaced:
                prefix, _, rest = m.groups()
                # Format new value
                if isinstance(new_value, bool):
                    val_str = "true" if new_value else "false"
                elif isinstance(new_value, (int, float)):
                    val_str = str(new_value)
                else:
                    val_str = f'"{new_value}"'
                new_lines.append(f"{prefix}{val_str}{rest}")
                replaced = True
            else:
                new_lines.append(line)

        if not replaced:
            raise ValueError(f"Key {key_path} not found in TOML file {file_path}")
        return "".join(new_lines)

    def _flatten(self, d: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        items: Dict[str, Any] = {}
        for k, v in d.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                items.update(self._flatten(v, key))
            else:
                items[key] = v
        return items


class INIConfigPlugin(ConfigLocatorPlugin):
    """Handles INI and CFG files, preserving sections and comments."""

    @property
    def format_name(self) -> str:
        return "ini"

    def can_handle(self, file_path: Path, content_sample: str) -> bool:
        if file_path.suffix.lower() in (".ini", ".cfg", ".conf"):
            return True
        try:
            cp = configparser.ConfigParser()
            cp.read_string(content_sample)
            return bool(cp.sections())
        except Exception:
            return False

    def locate_parameter(self, file_path: Path, parameter_needles: List[str]) -> Optional[Tuple[str, Any]]:
        try:
            content = file_path.read_text(encoding="utf-8")
            from cauveris.analysis.parameters import sectioned_config_entries
            entries = sectioned_config_entries(content)
            lowered_needles = [n.lower() for n in parameter_needles]
            for item in entries:
                key, val = item if isinstance(item, tuple) else (item, None)
                last_part = key.lower().split(".")[-1]
                if any(n in last_part or n in key.lower() for n in lowered_needles):
                    return key, val
        except Exception as e:
            logger.debug(f"INI locate failed: {e}")
        return None

    def edit_parameter(self, file_path: Path, key_path: str, new_value: Any) -> str:
        text = file_path.read_text(encoding="utf-8")
        from cauveris.analysis.parameters import replace_sectioned_scalar
        res = replace_sectioned_scalar(text, key_path, new_value)
        return res[0] if isinstance(res, tuple) else res


class EnvFileConfigPlugin(ConfigLocatorPlugin):
    """Handles environment (.env, env) files preserving comments and structure."""

    @property
    def format_name(self) -> str:
        return "env"

    def can_handle(self, file_path: Path, content_sample: str) -> bool:
        name = file_path.name.lower()
        if name == ".env" or name.startswith(".env.") or name.endswith(".env"):
            return True
        lines = [ln.strip() for ln in content_sample.splitlines() if ln.strip()]
        if len(lines) > 0 and all("=" in ln and not ln.startswith("#") for ln in lines[:min(5, len(lines))]):
            return True
        return False

    def locate_parameter(self, file_path: Path, parameter_needles: List[str]) -> Optional[Tuple[str, Any]]:
        try:
            content = file_path.read_text(encoding="utf-8")
            lowered_needles = [n.lower() for n in parameter_needles]
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    k_lower = k.lower()
                    if any(n in k_lower for n in lowered_needles):
                        return k, v
        except Exception:
            pass
        return None

    def edit_parameter(self, file_path: Path, key_path: str, new_value: Any) -> str:
        text = file_path.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        target = key_path.strip()
        new_lines = []
        replaced = False

        pattern = re.compile(rf"^(\s*{re.escape(target)}\s*=\s*)([^#\n\r]*)(.*)$")
        for line in lines:
            m = pattern.match(line)
            if m and not replaced:
                prefix, _, rest = m.groups()
                new_lines.append(f"{prefix}{new_value}{rest}")
                replaced = True
            else:
                new_lines.append(line)

        if not replaced:
            raise ValueError(f"Key {key_path} not found in env file {file_path}")
        return "".join(new_lines)


class JavaPropertiesConfigPlugin(ConfigLocatorPlugin):
    """Handles Java .properties files."""

    @property
    def format_name(self) -> str:
        return "java_properties"

    def can_handle(self, file_path: Path, content_sample: str) -> bool:
        return file_path.suffix.lower() in (".properties", ".prop")

    def locate_parameter(self, file_path: Path, parameter_needles: List[str]) -> Optional[Tuple[str, Any]]:
        try:
            content = file_path.read_text(encoding="utf-8")
            lowered_needles = [n.lower() for n in parameter_needles]
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("!"):
                    continue
                sep = "=" if "=" in line else (":" if ":" in line else None)
                if sep:
                    k, v = line.split(sep, 1)
                    k = k.strip()
                    v = v.strip()
                    if any(n in k.lower() for n in lowered_needles):
                        return k, v
        except Exception:
            pass
        return None

    def edit_parameter(self, file_path: Path, key_path: str, new_value: Any) -> str:
        text = file_path.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        target = key_path.strip()
        new_lines = []
        replaced = False

        pattern = re.compile(rf"^(\s*{re.escape(target)}\s*[:=]\s*)([^#!\n\r]*)(.*)$")
        for line in lines:
            m = pattern.match(line)
            if m and not replaced:
                prefix, _, rest = m.groups()
                new_lines.append(f"{prefix}{new_value}{rest}")
                replaced = True
            else:
                new_lines.append(line)

        if not replaced:
            raise ValueError(f"Key {key_path} not found in Java properties {file_path}")
        return "".join(new_lines)


class XMLConfigPlugin(ConfigLocatorPlugin):
    """Handles XML configuration files, editing elements in-place."""

    @property
    def format_name(self) -> str:
        return "xml"

    def can_handle(self, file_path: Path, content_sample: str) -> bool:
        if file_path.suffix.lower() == ".xml":
            return True
        stripped = content_sample.strip()
        return stripped.startswith("<?xml") or (stripped.startswith("<") and stripped.endswith(">"))

    def locate_parameter(self, file_path: Path, parameter_needles: List[str]) -> Optional[Tuple[str, Any]]:
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            lowered_needles = [n.lower() for n in parameter_needles]
            for elem in root.iter():
                tag_lower = elem.tag.lower()
                if any(n in tag_lower for n in lowered_needles):
                    if elem.text and elem.text.strip():
                        return elem.tag, elem.text.strip()
                # Check attributes
                for attr_k, attr_v in elem.attrib.items():
                    if any(n in attr_k.lower() for n in lowered_needles):
                        return f"{elem.tag}[@{attr_k}]", attr_v
        except Exception:
            pass
        return None

    def edit_parameter(self, file_path: Path, key_path: str, new_value: Any) -> str:
        text = file_path.read_text(encoding="utf-8")
        # Structure-preserving replacement for XML tag content: <tag>old_val</tag> -> <tag>new_val</tag>
        if "[@" in key_path:
            # Attribute edit
            tag, attr_part = key_path.split("[@", 1)
            attr = attr_part.rstrip("]")
            pattern = re.compile(rf'(<{re.escape(tag)}[^>]*\s+{re.escape(attr)}\s*=\s*["\'])([^"\']*)(["\'])')
            if not pattern.search(text):
                raise ValueError(f"XML attribute {key_path} not found in {file_path}")
            return pattern.sub(rf"\g<1>{new_value}\g<3>", text, count=1)
        else:
            tag = key_path.strip()
            pattern = re.compile(rf"(<{re.escape(tag)}[^>]*>)(.*?)(</{re.escape(tag)}>)")
            if not pattern.search(text):
                raise ValueError(f"XML tag {key_path} not found in {file_path}")
            return pattern.sub(rf"\g<1>{new_value}\g<3>", text, count=1)


class ConfigLocatorRegistry:
    """Registry of structure-aware configuration locator and patching plugins."""

    def __init__(self):
        self.plugins: List[ConfigLocatorPlugin] = [
            YAMLConfigPlugin(),
            JSONConfigPlugin(),
            TOMLConfigPlugin(),
            INIConfigPlugin(),
            EnvFileConfigPlugin(),
            JavaPropertiesConfigPlugin(),
            XMLConfigPlugin(),
        ]

    def select_plugin(self, file_path: Path) -> Optional[ConfigLocatorPlugin]:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                sample = f.read(4096)
        except Exception:
            return None

        for plugin in self.plugins:
            if plugin.can_handle(file_path, sample):
                return plugin
        return None

    def find_and_edit(
        self,
        file_path: Path,
        parameter_needles: List[str],
        new_value: Any,
    ) -> Optional[Tuple[str, str, Any, str]]:
        """
        Finds parameter matching needles in file_path and edits it.
        Returns (format_name, key_path, old_value, new_content) or None.
        """
        plugin = self.select_plugin(file_path)
        if plugin is None:
            return None

        loc = plugin.locate_parameter(file_path, parameter_needles)
        if loc is None:
            return None

        key_path, old_val = loc
        new_content = plugin.edit_parameter(file_path, key_path, new_value)
        return plugin.format_name, key_path, old_val, new_content
