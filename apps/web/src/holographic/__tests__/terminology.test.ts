/**
 * Phase 1: Robotics UX grounding.
 *
 * The survey's largest "Conceptual Mismatch Risk" was the literal optical
 * framing — lasers, wavelengths, Strehl ratios — presented to reliability
 * engineers. Every user-facing string now comes from `domain/terminology.ts`;
 * these are the tests that keep it that way.
 *
 * The distinction under test is *audience*, not vocabulary. The physics is
 * still the implementation and `implementationNote` still says so in full —
 * an engineer can always find out that the residual is an MSE. What must not
 * happen is a label or description that only makes sense to someone who
 * already knows the solver.
 */

import { describe, it, expect } from "vitest";
import {
  QUALITY_TERMS,
  STATUS_TERMS,
  VIEW_MODES,
  SCENE_VIEWS,
  INSTRUMENTATION_TERMS,
  PAGE_TERMS,
  SHELL_CONTEXT,
  COMPONENT_ACTIONS,
  DEEP_LINK_PARAM,
  DEEP_LINK_INCIDENT_PARAM,
  DEEP_LINK_SOURCE_PARAM,
  DEEP_LINK_SOURCE_VALUE,
  componentDeepLink,
  evidenceCoveragePercent,
  readDeepLink,
  viewModeLabel,
  type Term,
} from "../domain/terminology";

/**
 * Words that only make sense to someone who knows the solver.
 *
 * `\b`-anchored where a token could otherwise appear as a substring of an
 * ordinary word — `nm` inside "environment", `SLM` inside nothing but itself.
 * "holographic" is deliberately absent: it is the feature's name, not a claim
 * about what the engineer is looking at.
 */
const OPTICS_VOCABULARY: RegExp[] = [
  /\blasers?\b/i,
  /\boptical\b/i,
  /\boptics\b/i,
  /\bwavelengths?\b/i,
  /\bnm\b/i,
  /µm/i,
  /\bSLM\b/,
  /Strehl/i,
  /\bfringes?\b/i,
  /\bfringe-alias/i,
  /\bexposures?\b/i,
  /\bdiffraction\b/i,
  /\bwavefronts?\b/i,
  /\bspeckle\b/i,
  /\bphase retrieval\b/i,
  /\bpixel pitch\b/i,
];

/** Every term object exported as a user-facing vocabulary, flat. */
function allTerms(): Array<{ path: string; term: Term }> {
  const out: Array<{ path: string; term: Term }> = [];
  for (const [key, term] of Object.entries(QUALITY_TERMS)) {
    out.push({ path: `QUALITY_TERMS.${key}`, term: term as Term });
  }
  for (const [key, term] of Object.entries(STATUS_TERMS)) {
    out.push({ path: `STATUS_TERMS.${key}`, term: term as Term });
  }
  for (const [key, term] of Object.entries(INSTRUMENTATION_TERMS)) {
    out.push({ path: `INSTRUMENTATION_TERMS.${key}`, term: term as Term });
  }
  for (const mode of VIEW_MODES) {
    out.push({ path: `VIEW_MODES[${mode.value}]`, term: mode });
  }
  for (const view of SCENE_VIEWS) {
    out.push({ path: `SCENE_VIEWS[${view.value}]`, term: view });
  }
  return out;
}

/** The strings a user actually reads: label, description, and any terse `value`. */
function userFacingStrings(term: Term): Array<[string, string]> {
  const out: Array<[string, string]> = [
    ["label", term.label],
    ["description", term.description],
  ];
  if (term.value !== undefined) out.push(["value", term.value]);
  return out;
}

describe("Holographic terminology: robotics grounding", () => {
  describe("no user-facing string is optics vocabulary", () => {
    it.each(allTerms())("$path", ({ term }) => {
      for (const [field, text] of userFacingStrings(term)) {
        for (const banned of OPTICS_VOCABULARY) {
          expect(text, `${field} matches ${banned}`).not.toMatch(banned);
        }
      }
    });

    it("page-level copy is grounded too", () => {
      const pageStrings: Array<[string, string]> = [
        ["title", PAGE_TERMS.title],
        ["subtitleWithIncident", PAGE_TERMS.subtitleWithIncident("CAU-0001")],
        ["subtitleNoIncident", PAGE_TERMS.subtitleNoIncident],
        ["recompute", PAGE_TERMS.recompute],
        ["telemetryCardTitle", PAGE_TERMS.telemetryCardTitle],
        ["sliceOverlayTitle", PAGE_TERMS.sliceOverlayTitle],
        ["displayGain", PAGE_TERMS.displayGain],
        ["volumeAriaLabel", PAGE_TERMS.volumeAriaLabel],
        ["shell.title", SHELL_CONTEXT.title],
        ["shell.pipelineStage", SHELL_CONTEXT.pipelineStage],
      ];
      for (const [field, text] of pageStrings) {
        for (const banned of OPTICS_VOCABULARY) {
          expect(text, `${field} matches ${banned}`).not.toMatch(banned);
        }
      }
    });
  });

  describe("the implementation note is preserved, not scrubbed", () => {
    // The rename would be a lie if it hid how the number was produced. These
    // assert the escape hatch survives: at least one term still names the
    // actual computation, and every term has a non-empty note.
    it("every term carries a real implementation note", () => {
      for (const { path, term } of allTerms()) {
        const note = term.implementationNote;
        expect(note, `${path} has no implementationNote`).toBeTruthy();
        expect(note.trim().length, `${path} has a stub note`).toBeGreaterThan(15);
        // A note that just echoes the label tells the reader nothing new.
        expect(note, `${path} note restates its label`).not.toBe(term.label);
        expect(note, `${path} note restates its description`).not.toBe(term.description);
      }
    });

    it("the solver term still names Fienup HIO/ER, because that is the solver", () => {
      expect(INSTRUMENTATION_TERMS.solver.value).toBe("Fienup HIO/ER");
      expect(INSTRUMENTATION_TERMS.solver.implementationNote).toMatch(/Fienup/);
    });

    it("the quality terms still name their computation", () => {
      expect(QUALITY_TERMS.residual.implementationNote).toMatch(/mean squared error/i);
      expect(QUALITY_TERMS.peakRecovery.implementationNote).toMatch(/Strehl/i);
    });
  });

  describe("relabelling is backed by a quantity the backend emits", () => {
    it("the observation window is the reconstruction's own time window, not a constant", () => {
      expect(INSTRUMENTATION_TERMS.observationWindow.implementationNote).toMatch(
        /time_window_ns/
      );
    });

    it("the fusion grid is the reconstruction's grid size, not a fixed pitch", () => {
      expect(INSTRUMENTATION_TERMS.samplingGrid.implementationNote).toMatch(/grid/i);
    });
  });

  describe("wire contracts are untouched by the rename", () => {
    // `HologramVolume`'s `displayMode` prop and the mode indices in
    // hologramMaterial.ts key on these exact strings. Only the label may move.
    it("VIEW_MODES values are unchanged", () => {
      expect(VIEW_MODES.map((m) => m.value)).toEqual([
        "phase_hue",
        "fringe_alarm",
        "intensity_slice",
        "raw",
      ]);
    });

    it("SCENE_VIEWS values are unchanged", () => {
      expect(SCENE_VIEWS.map((v) => v.value)).toEqual(["3d", "topology", "timeline"]);
    });

    it("the old optical display-mode labels are gone", () => {
      const labels = VIEW_MODES.map((m) => m.label);
      expect(labels).not.toContain("Fringe Aliasing Alarm");
      expect(labels).not.toContain("ASM Propagation Slice");
      expect(SCENE_VIEWS.map((v) => v.label)).not.toContain("3D Hologram Volume");
      expect(SCENE_VIEWS.map((v) => v.label)).not.toContain("Reality Rewind Timeline");
    });

    it("viewModeLabel tolerates an unrecognised wire value instead of throwing", () => {
      expect(viewModeLabel("phase_hue")).toBe("Confidence Field");
      expect(viewModeLabel("something_from_a_newer_backend")).toBe(
        "something_from_a_newer_backend"
      );
    });
  });

  describe("evidenceCoveragePercent", () => {
    it("is the share of modelled layers that reached the inversion", () => {
      expect(evidenceCoveragePercent(7, 7)).toBe(100);
      expect(evidenceCoveragePercent(0, 7)).toBe(0);
      expect(evidenceCoveragePercent(3, 7)).toBeCloseTo((3 / 7) * 100, 6);
    });

    it("returns 0 — not 100, not NaN — when provenance is unavailable", () => {
      // Zero reads as "unknown" in the top bar. A fabricated 0.94 is what this
      // replaced, so the failure mode must not be a plausible-looking number.
      expect(evidenceCoveragePercent(undefined, 7)).toBe(0);
      expect(evidenceCoveragePercent(3, 0)).toBe(0);
    });

    it("clamps nonsense counts rather than reporting over 100% coverage", () => {
      expect(evidenceCoveragePercent(99, 7)).toBe(100);
      expect(evidenceCoveragePercent(-4, 7)).toBe(0);
    });
  });
});

describe("Deep links into the downstream investigation tools", () => {
  it("carries the component and the incident", () => {
    const href = componentDeepLink("/ghost-lab", "svc-payments", "CAU-0001");
    const params = new URLSearchParams(href.slice(href.indexOf("?") + 1));
    expect(params.get(DEEP_LINK_PARAM)).toBe("svc-payments");
    expect(params.get(DEEP_LINK_INCIDENT_PARAM)).toBe("CAU-0001");
    expect(params.get(DEEP_LINK_SOURCE_PARAM)).toBe(DEEP_LINK_SOURCE_VALUE);
  });

  it("omits the component rather than writing the string 'null'", () => {
    const href = componentDeepLink("/reality-rewind", null, "CAU-0001");
    expect(href).not.toMatch(/component=null/);
    expect(readDeepLink(new URLSearchParams(href.split("?")[1])).componentId).toBeNull();
  });

  it("is readable back out by the consumer", () => {
    const href = componentDeepLink("/patch-forge", "svc-auth", "CAU-0007");
    const link = readDeepLink(new URLSearchParams(href.split("?")[1]));
    expect(link).toEqual({
      componentId: "svc-auth",
      incidentId: "CAU-0007",
      experimentId: null,
      patchId: null,
      arrivedFromReconstruction: true,
    });
  });

  it("readDeepLink never throws and returns nulls for an empty URL", () => {
    const empty = readDeepLink(new URLSearchParams(""));
    expect(empty.componentId).toBeNull();
    expect(empty.arrivedFromReconstruction).toBe(false);
    // Called with no params at all — the case a page hits before it knows
    // whether it is being deep-linked.
    expect(readDeepLink(null).componentId).toBeNull();
  });

  it("only reports a reconstruction arrival when the source marker matches", () => {
    const other = readDeepLink(new URLSearchParams("component=a&from=sidebar"));
    expect(other.componentId).toBe("a");
    expect(other.arrivedFromReconstruction).toBe(false);
  });

  it("every action points at a route that accepts these params", () => {
    for (const action of COMPONENT_ACTIONS) {
      const href = componentDeepLink(action.href, "svc-x", "CAU-0001");
      expect(href.startsWith(`${action.href}?`)).toBe(true);
      expect(["ghost-lab", "patch-forge", "reality-rewind"]).toContain(
        action.href.replace("/", "")
      );
    }
  });
});
