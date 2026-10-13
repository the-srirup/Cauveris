"""Evidence provenance for holographic reconstructions — Phase 1.

The defect under test is the silent synthetic fallback. When an incident's
evidence bundle could not be found, the pipeline substituted a synthetic
scenario and the payload carried no indication that it had done so: a
plausible-looking causal graph describing a system that did not exist.

The fix is a provenance record on every payload. These tests pin its two
load-bearing properties:

1. **A payload can never be ambiguous about whether it is real.** Absent an
   explicit record, ``default_provenance`` reports synthetic — the failure mode
   degrades into a visible warning, never a silent falsehood.
2. **A sparse bundle is not a synthetic one.** Missing evidence and fabricated
   evidence are different claims and drive different severities; conflating
   them either panics an engineer over a real bundle or reassures them about a
   fake one.

The second point extends to the missing/undeclared split, which an earlier
revision got wrong by deriving "missing" from the 7-value ``BoundaryLayer``
enum complement. That told a system modelling only logs and metrics that it had
five missing layers — a fabricated deficiency on a complete bundle.
"""

import pytest

from cauveris.holographic.heu import BoundaryLayer
from cauveris.holographic.visualization import (
    DATA_SOURCE_SYNTHETIC,
    DATA_SOURCE_VERIFIED,
    SPARSE_TIMELINE_EVENT_THRESHOLD,
    build_provenance,
    default_provenance,
    scoped_boundary_layer_gaps,
    summarize_boundary_coverage,
)

ALL_LAYERS = [layer.value for layer in BoundaryLayer]


def codes(record):
    """Warning codes on a provenance record, in order."""
    return [w["code"] for w in record["provenance_warnings"]]


def warning(record, code):
    """The single warning with ``code``; fails the test if it is absent."""
    matches = [w for w in record["provenance_warnings"] if w["code"] == code]
    assert len(matches) == 1, f"expected exactly one {code}, got {len(matches)}"
    return matches[0]


class _FakeReconstruction:
    """Minimal stand-in: the provenance helpers read these by ``getattr``.

    Deliberately not a real ``HolographicReconstruction`` — these functions are
    total over any object exposing the attributes, and building a full
    reconstruction to test a list diff would obscure what is being tested.
    """

    def __init__(self, observed_layers=None, observed_heus=None, missing=None):
        if observed_layers is not None:
            self.observed_layers = observed_layers
        if observed_heus is not None:
            self.observed_heus = observed_heus
        if missing is not None:
            self.missing_boundary_layers = missing


# ---------------------------------------------------------------------------
# default_provenance: the call site that forgot to pass a record
# ---------------------------------------------------------------------------


class TestDefaultProvenance:
    def test_reports_synthetic(self):
        record = default_provenance()
        assert record["data_source"] == DATA_SOURCE_SYNTHETIC
        assert record["bundle_found"] is False
        assert record["bundle_path"] is None

    def test_is_not_mute(self):
        """An empty warning list would render as a fabricated graph with
        nothing for a warnings-only consumer to read."""
        record = default_provenance()
        assert record["provenance_warnings"], "default provenance must speak"
        entry = warning(record, "PROVENANCE_NOT_RECORDED")
        assert entry["severity"] == "critical"

    def test_states_what_happened_rather_than_a_search_that_never_ran(self):
        record = default_provenance()
        entry = warning(record, "PROVENANCE_NOT_RECORDED")
        assert "without an evidence record" in entry["message"]
        # No bundle was looked for, so no search path may be implied.
        assert record["bundle_search_paths"] == []
        assert "search" not in entry["message"].lower()

    def test_names_the_defect_as_server_side(self):
        entry = warning(default_provenance(), "PROVENANCE_NOT_RECORDED")
        assert "server-side defect" in entry["remediation"]

    def test_every_modelled_layer_is_undeclared_but_none_is_missing(self):
        record = default_provenance()
        assert record["observed_boundary_layers"] == []
        assert record["undeclared_boundary_layers"] == sorted(ALL_LAYERS)
        assert record["missing_boundary_layers"] == []


# ---------------------------------------------------------------------------
# summarize_boundary_coverage: observed vs never-observed
# ---------------------------------------------------------------------------


class TestSummarizeBoundaryCoverage:
    def test_reads_the_per_component_layer_index(self):
        reconstruction = _FakeReconstruction(
            observed_layers={
                "payment-svc": [BoundaryLayer.APPLICATION_LOG],
                "auth-svc": [BoundaryLayer.METRICS_EXPORT, BoundaryLayer.APPLICATION_LOG],
            }
        )
        observed, undeclared = summarize_boundary_coverage(reconstruction)
        assert observed == ["application_log", "metrics_export"]
        assert "application_log" not in undeclared
        assert "metrics_export" not in undeclared
        assert len(undeclared) == len(ALL_LAYERS) - 2

    def test_second_element_is_the_enum_complement_not_a_deficiency_list(self):
        """A never-observed layer is a coverage fact. Nothing here may be read
        as 'the bundle failed to deliver this'."""
        reconstruction = _FakeReconstruction(
            observed_layers={"svc": [BoundaryLayer.APPLICATION_LOG]}
        )
        _, undeclared = summarize_boundary_coverage(reconstruction)
        assert undeclared == sorted(set(ALL_LAYERS) - {"application_log"})

    def test_falls_back_to_heu_groups(self):
        class _Heu:
            def __init__(self, layer):
                self.boundary_layer = layer

        reconstruction = _FakeReconstruction(
            observed_heus={"svc": [_Heu(BoundaryLayer.DISTRIBUTED_TRACE)]}
        )
        observed, _ = summarize_boundary_coverage(reconstruction)
        assert observed == ["distributed_trace"]

    def test_prefers_the_index_over_the_heu_fallback(self):
        class _Heu:
            boundary_layer = BoundaryLayer.NETWORK_FLOW

        reconstruction = _FakeReconstruction(
            observed_layers={"svc": [BoundaryLayer.APPLICATION_LOG]},
            observed_heus={"svc": [_Heu()]},
        )
        observed, _ = summarize_boundary_coverage(reconstruction)
        assert observed == ["application_log"]

    def test_an_empty_reconstruction_declares_everything_and_observes_nothing(self):
        observed, undeclared = summarize_boundary_coverage(_FakeReconstruction())
        assert observed == []
        assert undeclared == sorted(ALL_LAYERS)


# ---------------------------------------------------------------------------
# scoped_boundary_layer_gaps: the genuine deficiency signal
# ---------------------------------------------------------------------------


class TestScopedBoundaryLayerGaps:
    def test_returns_the_declared_but_undelivered_layers(self):
        reconstruction = _FakeReconstruction(
            missing=["payment-svc.network_flow", "auth-svc.config_state"]
        )
        assert scoped_boundary_layer_gaps(reconstruction) == [
            "auth-svc.config_state",
            "payment-svc.network_flow",
        ]

    def test_is_empty_when_nothing_was_declared(self):
        """Without a declaration there is no way to tell an undelivered layer
        from one that was never expected, and inventing a deficiency would be
        worse than reporting none."""
        assert scoped_boundary_layer_gaps(_FakeReconstruction()) == []

    def test_is_empty_when_the_declaration_was_fully_delivered(self):
        assert scoped_boundary_layer_gaps(_FakeReconstruction(missing=[])) == []


# ---------------------------------------------------------------------------
# build_provenance: bundle not found
# ---------------------------------------------------------------------------


class TestBundleNotFound:
    def test_is_synthetic_and_critical(self):
        record = build_provenance(bundle_found=False)
        assert record["data_source"] == DATA_SOURCE_SYNTHETIC
        entry = warning(record, "BUNDLE_NOT_FOUND")
        assert entry["severity"] == "critical"

    def test_says_the_graph_is_not_the_engineers_system(self):
        entry = warning(build_provenance(bundle_found=False), "BUNDLE_NOT_FOUND")
        assert "NOT the" in entry["message"]
        assert "synthetic" in entry["message"].lower()

    def test_records_every_path_that_was_probed(self):
        record = build_provenance(
            bundle_found=False,
            bundle_search_paths=["/data/incidents/CAU-1", "/mnt/evidence/CAU-1"],
        )
        assert record["bundle_search_paths"] == [
            "/data/incidents/CAU-1",
            "/mnt/evidence/CAU-1",
        ]

    def test_carries_the_synthetic_scenario_identity(self):
        record = build_provenance(
            bundle_found=False, synthetic_seed=7, synthetic_incident_type="cascade"
        )
        assert record["synthetic_seed"] == 7
        assert record["synthetic_incident_type"] == "cascade"


# ---------------------------------------------------------------------------
# build_provenance: bundle found, evidence incomplete
# ---------------------------------------------------------------------------


class TestSparseBundle:
    def test_a_found_bundle_is_never_reported_as_synthetic(self):
        """The core Phase 1 distinction."""
        record = build_provenance(
            bundle_found=True,
            timeline_event_count=3,
            observed_boundary_layers=["application_log"],
            missing_boundary_layers=["payment-svc.network_flow"],
        )
        assert record["data_source"] == DATA_SOURCE_VERIFIED
        assert "BUNDLE_NOT_FOUND" not in codes(record)

    def test_an_empty_timeline_is_critical(self):
        record = build_provenance(bundle_found=True, timeline_event_count=0)
        assert warning(record, "BUNDLE_HAS_NO_TIMELINE")["severity"] == "critical"

    def test_a_thin_timeline_is_a_warning_naming_the_count(self):
        record = build_provenance(bundle_found=True, timeline_event_count=12)
        entry = warning(record, "BUNDLE_TIMELINE_SPARSE")
        assert entry["severity"] == "warning"
        assert "12" in entry["message"]

    def test_the_sparse_threshold_boundary(self):
        below = build_provenance(
            bundle_found=True, timeline_event_count=SPARSE_TIMELINE_EVENT_THRESHOLD - 1
        )
        at = build_provenance(
            bundle_found=True, timeline_event_count=SPARSE_TIMELINE_EVENT_THRESHOLD
        )
        assert "BUNDLE_TIMELINE_SPARSE" in codes(below)
        assert "BUNDLE_TIMELINE_SPARSE" not in codes(at)

    def test_a_missing_layer_escalates_when_nothing_was_observed(self):
        """Nothing read at all means the inversion rests on the declared
        topology alone, which is a different claim from a partial read."""
        partial = build_provenance(
            bundle_found=True,
            timeline_event_count=100,
            observed_boundary_layers=["application_log"],
            missing_boundary_layers=["svc.network_flow"],
        )
        total = build_provenance(
            bundle_found=True,
            timeline_event_count=100,
            observed_boundary_layers=[],
            missing_boundary_layers=["svc.network_flow"],
        )
        assert warning(partial, "BOUNDARY_LAYERS_MISSING")["severity"] == "warning"
        assert warning(total, "BOUNDARY_LAYERS_MISSING")["severity"] == "critical"

    def test_a_missing_layer_names_the_blind_spot_not_just_the_layer(self):
        record = build_provenance(
            bundle_found=True,
            timeline_event_count=100,
            observed_boundary_layers=["application_log"],
            missing_boundary_layers=["payment-svc.network_flow"],
        )
        entry = warning(record, "BOUNDARY_LAYERS_MISSING")
        assert "packet loss" in entry["impact"]
        # Scoped entry, but the message must not make the engineer parse a
        # component-qualified string to know what is absent.
        assert "payment-svc.network_flow" in entry["message"]

    def test_a_missing_layer_singular_is_not_pluralised(self):
        one = build_provenance(
            bundle_found=True,
            timeline_event_count=100,
            missing_boundary_layers=["svc.network_flow"],
        )
        assert "1 declared telemetry layer" in warning(one, "BOUNDARY_LAYERS_MISSING")["message"]

        two = build_provenance(
            bundle_found=True,
            timeline_event_count=100,
            missing_boundary_layers=["svc.network_flow", "svc.config_state"],
        )
        assert "2 declared telemetry layers" in warning(two, "BOUNDARY_LAYERS_MISSING")["message"]


# ---------------------------------------------------------------------------
# build_provenance: missing vs undeclared
# ---------------------------------------------------------------------------


class TestMissingVersusUndeclared:
    def test_a_complete_bundle_is_not_told_it_is_sparse(self):
        """The bug the split fixes: a system modelling two layers was told it
        had five missing ones."""
        record = build_provenance(
            bundle_found=True,
            timeline_event_count=100,
            observed_boundary_layers=["application_log", "metrics_export"],
            missing_boundary_layers=[],  # nothing declared went undelivered
            undeclared_boundary_layers=sorted(set(ALL_LAYERS) - {"application_log", "metrics_export"}),
        )
        assert "BOUNDARY_LAYERS_MISSING" not in codes(record)
        assert "BOUNDARY_LAYERS_UNDECLARED" in codes(record)

    def test_undeclared_is_info_severity_and_asks_for_nothing(self):
        record = build_provenance(
            bundle_found=True,
            timeline_event_count=100,
            observed_boundary_layers=["application_log"],
            undeclared_boundary_layers=["network_flow"],
        )
        entry = warning(record, "BOUNDARY_LAYERS_UNDECLARED")
        assert entry["severity"] == "info"
        assert entry["remediation"].startswith("No action required")

    def test_undeclared_states_that_nothing_expected_is_absent(self):
        record = build_provenance(
            bundle_found=True,
            timeline_event_count=100,
            observed_boundary_layers=["application_log"],
            undeclared_boundary_layers=["network_flow"],
        )
        assert "Nothing this bundle was supposed to contain is missing" in warning(
            record, "BOUNDARY_LAYERS_UNDECLARED"
        )["impact"]

    def test_missing_supersedes_undeclared_rather_than_double_reporting(self):
        """A real deficiency is the actionable statement; the coverage fact
        beside it would only dilute it."""
        record = build_provenance(
            bundle_found=True,
            timeline_event_count=100,
            observed_boundary_layers=["application_log"],
            missing_boundary_layers=["svc.network_flow"],
            undeclared_boundary_layers=["config_state", "deployment_event"],
        )
        assert "BOUNDARY_LAYERS_MISSING" in codes(record)
        assert "BOUNDARY_LAYERS_UNDECLARED" not in codes(record)

    def test_an_undeclared_layer_is_never_called_a_defect(self):
        record = build_provenance(
            bundle_found=True,
            timeline_event_count=100,
            observed_boundary_layers=["application_log"],
            undeclared_boundary_layers=["network_flow"],
        )
        entry = warning(record, "BOUNDARY_LAYERS_UNDECLARED")
        blob = f"{entry['message']} {entry['impact']} {entry['remediation']}".lower()

        # The phrasing a deficiency claim would use. "missing" alone is not one
        # of them — the impact says the opposite: nothing is missing.
        for phrase in ("delivered no evidence", "gap in the bundle", "defect"):
            assert phrase not in blob
        assert "nothing this bundle was supposed to contain is missing" in blob
        # And it must not ask the engineer to go export anything.
        assert "no action required" in entry["remediation"].lower()


# ---------------------------------------------------------------------------
# build_provenance: key emission
# ---------------------------------------------------------------------------


class TestKeyEmission:
    def test_layer_keys_are_absent_when_the_caller_did_not_pin_them(self):
        """`VisualizationDataGenerator.generate` reads an absent key as 'derive
        this from the reconstruction'. An empty placeholder would silently
        suppress that and report zero coverage for a fully instrumented
        incident."""
        record = build_provenance(bundle_found=True, timeline_event_count=100)
        assert "observed_boundary_layers" not in record
        assert "missing_boundary_layers" not in record
        assert "undeclared_boundary_layers" not in record

    def test_layer_keys_are_present_when_supplied(self):
        record = build_provenance(
            bundle_found=True,
            timeline_event_count=100,
            observed_boundary_layers=["application_log"],
            missing_boundary_layers=[],
            undeclared_boundary_layers=[],
        )
        assert record["observed_boundary_layers"] == ["application_log"]
        assert record["missing_boundary_layers"] == []
        assert record["undeclared_boundary_layers"] == []

    def test_an_explicitly_empty_list_is_not_confused_with_an_absent_one(self):
        record = build_provenance(
            bundle_found=True, timeline_event_count=100, observed_boundary_layers=[]
        )
        assert "observed_boundary_layers" in record


# ---------------------------------------------------------------------------
# build_provenance: shape
# ---------------------------------------------------------------------------


class TestRecordShape:
    def test_always_carries_the_keys_every_consumer_needs(self):
        record = build_provenance(bundle_found=False)
        for key in (
            "data_source",
            "bundle_found",
            "bundle_path",
            "bundle_search_paths",
            "timeline_event_count",
            "provenance_warnings",
        ):
            assert key in record, f"missing {key}"

    def test_every_warning_is_actionable(self):
        """A warning tells the engineer what is wrong, what they cannot
        conclude, and what to do — the UI renders all three."""
        records = [
            build_provenance(bundle_found=False, bundle_search_paths=["/nowhere"]),
            build_provenance(bundle_found=True, timeline_event_count=0),
            build_provenance(bundle_found=True, timeline_event_count=5),
            build_provenance(
                bundle_found=True,
                timeline_event_count=100,
                observed_boundary_layers=["application_log"],
                missing_boundary_layers=["svc.network_flow"],
            ),
            build_provenance(
                bundle_found=True,
                timeline_event_count=100,
                observed_boundary_layers=["application_log"],
                undeclared_boundary_layers=["network_flow"],
            ),
            default_provenance(),
        ]
        seen = set()
        for record in records:
            for entry in record["provenance_warnings"]:
                assert set(entry) >= {"code", "severity", "message", "impact", "remediation"}
                assert entry["severity"] in {"info", "warning", "critical"}
                for field in ("message", "impact", "remediation"):
                    assert entry[field].strip(), f"{entry['code']}.{field} is empty"
                seen.add(entry["code"])
        # The suite above claims to cover every warning the builder can emit.
        assert seen == {
            "BUNDLE_NOT_FOUND",
            "BUNDLE_HAS_NO_TIMELINE",
            "BUNDLE_TIMELINE_SPARSE",
            "BOUNDARY_LAYERS_MISSING",
            "BOUNDARY_LAYERS_UNDECLARED",
            "PROVENANCE_NOT_RECORDED",
        }

    def test_data_source_is_one_of_the_two_declared_values(self):
        for found in (True, False):
            record = build_provenance(bundle_found=found, timeline_event_count=100)
            assert record["data_source"] in {DATA_SOURCE_VERIFIED, DATA_SOURCE_SYNTHETIC}
            assert record["data_source"] == (
                DATA_SOURCE_VERIFIED if found else DATA_SOURCE_SYNTHETIC
            )

    def test_search_paths_are_copied_not_aliased(self):
        searched = ["/data/incidents/CAU-1"]
        record = build_provenance(bundle_found=False, bundle_search_paths=searched)
        searched.append("/mutated/afterwards")
        assert record["bundle_search_paths"] == ["/data/incidents/CAU-1"]
