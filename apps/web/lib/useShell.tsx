"use client";

import { createContext, useContext, useReducer, useEffect, useCallback, useMemo, ReactNode } from "react";
import type { Incident } from "@/lib/api";

/* -------------------------------------------------------------------------- */
/* Types                                                                      */
/* -------------------------------------------------------------------------- */

export type NavItemKey =
  | "mission-control"
  | "reality-rewind"
  | "causal-constellation"
  | "holographic-reconstruction"
  | "ghost-lab"
  | "patch-forge"
  | "victory-replay"
  | "evidence-vault"
  | "reports"
  | "settings";

export interface IncidentContext {
  id: string;
  title: string;
  state: string;
  pipelineStage: string;
  evidenceCoverage: number;
  modelProvider: string;
  backendStatus: "online" | "degraded" | "offline";
  processingMode: "autonomous" | "judge" | "engineer";
  isDemonstration: boolean;
}

export type InspectorMode =
  | "timeline"
  | "graph"
  | "evidence"
  | "hypothesis"
  | "experiment"
  | "patch"
  | null;

export interface InspectorData {
  mode: InspectorMode;
  // Timeline event
  eventId?: string;
  eventData?: any;
  // Graph node/edge
  elementId?: string;
  elementType?: "node" | "edge";
  elementData?: any;
  // Evidence item
  evidenceId?: string;
  evidenceData?: any;
  // Hypothesis
  hypothesisId?: string;
  hypothesisData?: any;
  // Experiment
  experimentId?: string;
  experimentData?: any;
  // Patch
  patchId?: string;
  patchData?: any;
}

export type ActivityType = "pipeline" | "experiment" | "system" | "warning" | "error";

export interface Activity {
  id: string;
  type: ActivityType;
  timestamp: number;
  message: string;
  details?: string;
  stageId?: string;
  experimentId?: string;
  dismissible: boolean;
}

export type TrayState = "closed" | "expanded";

export interface Command {
  id: string;
  label: string;
  description: string;
  shortcut: string;
  category: "incident" | "investigation" | "views" | "export" | "demo";
  action: () => void | Promise<void>;
  disabled?: boolean;
}

export interface ShellState {
  // Navigation
  activeNav: NavItemKey;
  isNavCollapsed: boolean;
  isNavDrawerOpen: boolean;

  // Top Context Bar
  incidentContext: IncidentContext | null;

  // Right Inspector
  inspectorOpen: boolean;
  inspectorMode: InspectorMode;
  inspectorData: InspectorData;

  // Bottom Activity Tray
  trayState: TrayState;
  activities: Activity[];

  // Command Palette
  commandPaletteOpen: boolean;
}

export type ShellAction =
  | { type: "SET_ACTIVE_NAV"; payload: NavItemKey }
  | { type: "TOGGLE_NAV_COLLAPSE" }
  | { type: "SET_NAV_COLLAPSE"; payload: boolean }
  | { type: "SET_NAV_DRAWER"; payload: boolean }
  | { type: "SET_INCIDENT_CONTEXT"; payload: IncidentContext | null }
  | { type: "OPEN_INSPECTOR"; payload: { mode: InspectorMode; data: InspectorData } }
  | { type: "CLOSE_INSPECTOR" }
  | { type: "SET_TRAY_STATE"; payload: TrayState }
  | { type: "ADD_ACTIVITY"; payload: Activity }
  | { type: "REMOVE_ACTIVITY"; payload: string }
  | { type: "CLEAR_ACTIVITIES" }
  | { type: "TOGGLE_COMMAND_PALETTE" }
  | { type: "SET_COMMAND_PALETTE"; payload: boolean };

/* -------------------------------------------------------------------------- */
/* Reducer                                                                    */
/* -------------------------------------------------------------------------- */

function shellReducer(state: ShellState, action: ShellAction): ShellState {
  switch (action.type) {
    case "SET_ACTIVE_NAV":
      return { ...state, activeNav: action.payload };

    case "TOGGLE_NAV_COLLAPSE":
      return { ...state, isNavCollapsed: !state.isNavCollapsed };

    case "SET_NAV_COLLAPSE":
      return { ...state, isNavCollapsed: action.payload };

    case "SET_NAV_DRAWER":
      return { ...state, isNavDrawerOpen: action.payload };

    case "SET_INCIDENT_CONTEXT":
      return { ...state, incidentContext: action.payload };

    case "OPEN_INSPECTOR":
      return {
        ...state,
        inspectorOpen: true,
        inspectorMode: action.payload.mode,
        inspectorData: action.payload.data,
      };

    case "CLOSE_INSPECTOR":
      return {
        ...state,
        inspectorOpen: false,
        inspectorMode: null,
        inspectorData: {
          mode: null,
        },
      };

    
    case "SET_TRAY_STATE":
      return { ...state, trayState: action.payload };

    case "ADD_ACTIVITY":
      return {
        ...state,
        activities: [action.payload, ...state.activities].slice(0, 100),
      };

    case "REMOVE_ACTIVITY":
      return {
        ...state,
        activities: state.activities.filter((a) => a.id !== action.payload),
      };

    case "CLEAR_ACTIVITIES":
      return { ...state, activities: [] };

    case "TOGGLE_COMMAND_PALETTE":
      return { ...state, commandPaletteOpen: !state.commandPaletteOpen };

    case "SET_COMMAND_PALETTE":
      return { ...state, commandPaletteOpen: action.payload };

    default:
      return state;
  }
}

/* -------------------------------------------------------------------------- */
/* Initial State                                                              */
/* -------------------------------------------------------------------------- */

const initialState: ShellState = {
  activeNav: "mission-control",
  isNavCollapsed: false,
  isNavDrawerOpen: false,
  incidentContext: null,
  inspectorOpen: false,
  inspectorMode: null,
  inspectorData: { mode: null },
  trayState: "closed",
  activities: [],
  commandPaletteOpen: false,
};

/* -------------------------------------------------------------------------- */
/* Context                                                                    */
/* -------------------------------------------------------------------------- */

interface ShellContextValue {
  state: ShellState;
  dispatch: React.Dispatch<ShellAction>;
  // Convenience methods
  setActiveNav: (nav: NavItemKey) => void;
  toggleNavCollapse: () => void;
  setNavCollapse: (collapsed: boolean) => void;
  setNavDrawer: (open: boolean) => void;
  setIncidentContext: (ctx: IncidentContext | null) => void;
  openInspector: (mode: InspectorMode, data: InspectorData) => void;
  closeInspector: () => void;
  setTrayState: (trayState: TrayState) => void;
  addActivity: (activity: Omit<Activity, "id" | "timestamp">) => void;
  removeActivity: (id: string) => void;
  clearActivities: () => void;
  toggleCommandPalette: () => void;
  setCommandPalette: (open: boolean) => void;
}

const ShellContext = createContext<ShellContextValue | null>(null);

/* -------------------------------------------------------------------------- */
/* Provider                                                                   */
/* -------------------------------------------------------------------------- */

export function ShellProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(shellReducer, initialState);

  // Sync isNavCollapsed with localStorage after mount (client-side only)
  useEffect(() => {
    try {
      const saved = localStorage.getItem("cauveris:sidebar-collapsed");
      if (saved !== null) {
        const isCollapsed = JSON.parse(saved);
        if (typeof isCollapsed === "boolean" && isCollapsed !== state.isNavCollapsed) {
          dispatch({ type: "SET_NAV_COLLAPSE", payload: isCollapsed });
        }
      }
    } catch {
      // Ignore localStorage errors
    }
  }, []);

  // Save changes to localStorage
  useEffect(() => {
    try {
      localStorage.setItem("cauveris:sidebar-collapsed", JSON.stringify(state.isNavCollapsed));
    } catch {
      // Ignore localStorage errors
    }
  }, [state.isNavCollapsed]);

  // Use useCallback for stable function references - dispatch is stable from useReducer
  const setActiveNav = useCallback((nav: NavItemKey) => dispatch({ type: "SET_ACTIVE_NAV", payload: nav }), [dispatch]);
  const toggleNavCollapse = useCallback(() => dispatch({ type: "TOGGLE_NAV_COLLAPSE" }), [dispatch]);
  const setNavCollapse = useCallback((collapsed: boolean) => dispatch({ type: "SET_NAV_COLLAPSE", payload: collapsed }), [dispatch]);
  const setNavDrawer = useCallback((open: boolean) => dispatch({ type: "SET_NAV_DRAWER", payload: open }), [dispatch]);
  const setIncidentContext = useCallback((ctx: IncidentContext | null) => dispatch({ type: "SET_INCIDENT_CONTEXT", payload: ctx }), [dispatch]);
  const openInspector = useCallback((mode: InspectorMode, data: InspectorData) => dispatch({ type: "OPEN_INSPECTOR", payload: { mode, data } }), [dispatch]);
  const closeInspector = useCallback(() => dispatch({ type: "CLOSE_INSPECTOR" }), [dispatch]);
  const setTrayState = useCallback((trayState: TrayState) => dispatch({ type: "SET_TRAY_STATE", payload: trayState }), [dispatch]);
  const addActivity = useCallback((activity: Omit<Activity, "id" | "timestamp">) =>
    dispatch({
      type: "ADD_ACTIVITY",
      payload: {
        ...activity,
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
        timestamp: Date.now(),
      },
    }), [dispatch]);
  const removeActivity = useCallback((id: string) => dispatch({ type: "REMOVE_ACTIVITY", payload: id }), [dispatch]);
  const clearActivities = useCallback(() => dispatch({ type: "CLEAR_ACTIVITIES" }), [dispatch]);
  const toggleCommandPalette = useCallback(() => dispatch({ type: "TOGGLE_COMMAND_PALETTE" }), [dispatch]);
  const setCommandPalette = useCallback((open: boolean) => dispatch({ type: "SET_COMMAND_PALETTE", payload: open }), [dispatch]);

  const value = useMemo<ShellContextValue>(
    () => ({
      state,
      dispatch,
      setActiveNav,
      toggleNavCollapse,
      setNavCollapse,
      setNavDrawer,
      setIncidentContext,
      openInspector,
      closeInspector,
      setTrayState,
      addActivity,
      removeActivity,
      clearActivities,
      toggleCommandPalette,
      setCommandPalette,
    }),
    [
      state,
      setActiveNav,
      toggleNavCollapse,
      setNavCollapse,
      setNavDrawer,
      setIncidentContext,
      openInspector,
      closeInspector,
      setTrayState,
      addActivity,
      removeActivity,
      clearActivities,
      toggleCommandPalette,
      setCommandPalette,
    ]
  );

  return <ShellContext.Provider value={value}>{children}</ShellContext.Provider>;
}

/* -------------------------------------------------------------------------- */
/* Hook                                                                       */
/* -------------------------------------------------------------------------- */

export function useShell() {
  const context = useContext(ShellContext);
  if (!context) {
    throw new Error("useShell must be used within a ShellProvider");
  }
  return context;
}

/* -------------------------------------------------------------------------- */
/* Helper: Build IncidentContext from Incident + pipeline state               */
/* -------------------------------------------------------------------------- */

export function buildIncidentContext(
  incident: Incident | null,
  pipelineState: string,
  activeStageId: string | null,
  pipelineStages: any[],
  evidenceSummary: any,
  modelProviderName: string,
  backendOnline: boolean,
  judgeMode: boolean,
  engineerMode: boolean
): IncidentContext | null {
  if (!incident) return null;

  const evidenceCoverage =
    evidenceSummary?.required_evidence_count > 0
      ? Math.min(100, Math.round((evidenceSummary.evidence_count / evidenceSummary.required_evidence_count) * 100))
      : incident.evidence_count > 0 && incident.required_evidence_count
      ? Math.min(100, Math.round((incident.evidence_count / incident.required_evidence_count) * 100))
      : 0;

  return {
    id: incident.id,
    title: incident.title || "Untitled Incident",
    state: pipelineState,
    pipelineStage: activeStageId || "IDLE",
    evidenceCoverage,
    modelProvider: modelProviderName,
    backendStatus: backendOnline ? "online" : "offline",
    processingMode: judgeMode ? "judge" : engineerMode ? "engineer" : "autonomous",
    isDemonstration: Boolean(incident.is_demonstration),
  };
}