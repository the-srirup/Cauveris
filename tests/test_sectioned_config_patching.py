"""
Patching a robot whose parameters do not ship as YAML.

Reading a customer's configuration is only half the job.  A robot whose
settings live in ``robot.toml`` has to be *patched* in that file as well:
a diff against a YAML file the robot does not use is not a fix, and a
diagnosis the pipeline cannot turn into an edit is not a diagnosis the
customer can act on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cauveris.analysis.parameters import (
    find_parameter_in_tree,
    replace_sectioned_scalar,
    sectioned_config_entries,
)
from cauveris.verifier.workspace import read_workspace_config


def _bundle(tmp_path: Path, name: str = "robot.toml", body: str = "") -> Path:
    root = tmp_path / "incident-CAU-9101"
    root.mkdir()
    (root / name).write_text(body, encoding="utf-8")
    return root


# ------------------------------------------------------------------ reading


def test_a_toml_key_is_found_in_the_tree(tmp_path: Path) -> None:
    """A bundle whose parameters ship as TOML has a parameter to find."""
    root = _bundle(
        tmp_path,
        body="[resources]\nmemory_limit_mb = 512\n",
    )

    found = find_parameter_in_tree(root, "resource_limit_mb")

    assert found is not None
    relative, key, value = found
    assert relative == "robot.toml"
    assert key == "resources.memory_limit_mb"
    assert value == 512


def test_a_root_level_ini_key_is_found(tmp_path: Path) -> None:
    """Configuration beside the manifest is configuration."""
    root = _bundle(
        tmp_path,
        name="settings.ini",
        body="[dynamic_batching]\nbatching_window_ms = 90\n",
    )

    found = find_parameter_in_tree(root, "batching_window_ms")

    assert found is not None
    assert found[0] == "settings.ini"
    assert found[2] == 90


def test_the_section_decides_which_declaration_is_the_knob(tmp_path: Path) -> None:
    """Two sections may declare the same name; only the right one counts."""
    root = _bundle(
        tmp_path,
        body=(
            "[http]\nrequest_timeout_ms = 50\n\n"
            "[storage]\nlock_timeout_ms = 50\n"
        ),
    )

    found = find_parameter_in_tree(root, "lock_timeout_ms")

    assert found is not None
    assert found[1] == "storage.lock_timeout_ms"


def test_a_packaging_file_is_not_the_robots_configuration(tmp_path: Path) -> None:
    """``pyproject.toml`` configures the build, not the robot."""
    root = _bundle(
        tmp_path,
        name="pyproject.toml",
        body='[tool.robot]\nrequest_timeout_ms = 50\n',
    )

    assert find_parameter_in_tree(root, "request_timeout_ms") is None


def test_sectioned_entries_report_dotted_keys() -> None:
    """The keys are reported the way a YAML document reports them."""
    entries = dict(
        sectioned_config_entries(
            "[dynamic_batching]\nbatching_window_ms = 120\nmax_batch_size = 8\n"
        )
    )

    assert entries == {
        "dynamic_batching.batching_window_ms": 120,
        "dynamic_batching.max_batch_size": 8,
    }


# ------------------------------------------------------------------ writing


def test_a_toml_value_is_replaced_in_place() -> None:
    """The patch changes one number and leaves the rest of the file alone."""
    text = (
        "# the perception server\n"
        "[dynamic_batching]\n"
        "batching_window_ms = 120  # how long to wait for a batch\n"
        "max_batch_size = 8\n"
    )

    patched, previous = replace_sectioned_scalar(
        text, "dynamic_batching.batching_window_ms", 7.5
    )

    assert previous == 120
    assert patched == (
        "# the perception server\n"
        "[dynamic_batching]\n"
        "batching_window_ms = 7.5  # how long to wait for a batch\n"
        "max_batch_size = 8\n"
    )


def test_only_the_named_section_is_changed() -> None:
    """The same name under two sections means two different things."""
    text = (
        "[http]\ntimeout_ms = 50\n\n"
        "[storage]\ntimeout_ms = 50\n"
    )

    patched, previous = replace_sectioned_scalar(text, "storage.timeout_ms", 150)

    assert previous == 50
    assert "[http]\ntimeout_ms = 50\n" in patched
    assert "[storage]\ntimeout_ms = 150\n" in patched


def test_a_quoted_value_keeps_its_quotes() -> None:
    """A quoted number is still a number, and still a quoted number."""
    text = '[queue]\nqos_depth = "5"\n'

    patched, previous = replace_sectioned_scalar(text, "queue.qos_depth", 10)

    assert previous == 5
    assert patched == '[queue]\nqos_depth = "10"\n'


def test_an_absent_key_is_not_patched() -> None:
    """A file that does not declare the key is left untouched."""
    text = "[queue]\nqos_depth = 5\n"

    assert replace_sectioned_scalar(text, "queue.server_workers", 4) is None


# --------------------------------------------------------------- the verifier


def test_the_verifier_reads_a_patched_toml_file(tmp_path: Path) -> None:
    """The verifier sees the change the patch made."""
    root = tmp_path / "workspace"
    (root / "config").mkdir(parents=True)
    (root / "config" / "robot.toml").write_text(
        "[dynamic_batching]\nbatching_window_ms = 7.5\n", encoding="utf-8"
    )

    config = read_workspace_config(root)

    assert config["config/robot.toml"] == {"dynamic_batching.batching_window_ms": 7.5}


def test_the_verifier_reads_a_patched_ini_file(tmp_path: Path) -> None:
    """An INI file's booleans are booleans, not the text ``"true"``."""
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "robot.ini").write_text(
        "[safety]\nwatchdog_enabled = true\ncontrol_deadline_ms = 100\n",
        encoding="utf-8",
    )

    config = read_workspace_config(root)

    assert config["robot.ini"] == {
        "safety.watchdog_enabled": True,
        "safety.control_deadline_ms": 100,
    }


@pytest.mark.parametrize(
    "body",
    [
        "[resources]\nmemory_limit_mb = 512\n",
        "[resources]\r\nmemory_limit_mb = 512\r\n",
    ],
)
def test_line_endings_do_not_change_the_outcome(tmp_path: Path, body: str) -> None:
    """A file written on another platform is still the same file."""
    root = _bundle(tmp_path, body=body)

    found = find_parameter_in_tree(root, "resource_limit_mb")

    assert found is not None
    assert found[2] == 512
