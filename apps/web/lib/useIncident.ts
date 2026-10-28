"use client";

import { useState, useEffect, useCallback } from "react";
import { api, Incident } from "@/lib/api";

const STORAGE_INCIDENT_KEY = "cauveris_active_incident_id";
const STORAGE_JUDGE_KEY = "cauveris_judge_mode";
const STORAGE_ENGINEER_KEY = "cauveris_engineer_mode";

// No hardcoded default incident: user starts with selectedIncidentId = null
const DEFAULT_INCIDENT_ID: string | null = null;

interface StatePayload {
  incidentId?: string | null;
  judgeMode?: boolean;
  engineerMode?: boolean;
}

let globalListeners: ((payload: StatePayload) => void)[] = [];

export function useActiveIncident() {
  const [incidentId, setIncidentIdState] = useState<string | null>(DEFAULT_INCIDENT_ID);
  const [judgeMode, setJudgeModeState] = useState<boolean>(true);
  const [engineerMode, setEngineerModeState] = useState<boolean>(false);
  const [incident, setIncidentState] = useState<Incident | null>(null);

  useEffect(() => {
    try {
      const storedId = localStorage.getItem(STORAGE_INCIDENT_KEY);
      if (storedId) setIncidentIdState(storedId);

      const storedJudge = localStorage.getItem(STORAGE_JUDGE_KEY);
      if (storedJudge !== null) setJudgeModeState(storedJudge === "true");

      const storedEng = localStorage.getItem(STORAGE_ENGINEER_KEY);
      if (storedEng !== null) setEngineerModeState(storedEng === "true");
    } catch {
      // Ignore
    }

    const listener = (payload: StatePayload) => {
      if (payload.incidentId !== undefined) setIncidentIdState(payload.incidentId);
      if (payload.judgeMode !== undefined) setJudgeModeState(payload.judgeMode);
      if (payload.engineerMode !== undefined) setEngineerModeState(payload.engineerMode);
    };

    globalListeners.push(listener);

    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_INCIDENT_KEY && e.newValue) {
        setIncidentIdState(e.newValue);
      } else if (e.key === STORAGE_JUDGE_KEY && e.newValue !== null) {
        setJudgeModeState(e.newValue === "true");
      } else if (e.key === STORAGE_ENGINEER_KEY && e.newValue !== null) {
        setEngineerModeState(e.newValue === "true");
      }
    };
    window.addEventListener("storage", onStorage);

    return () => {
      globalListeners = globalListeners.filter(l => l !== listener);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  const setIncidentId = (newId: string | null) => {
    setIncidentIdState(newId);
    try {
      if (newId) {
        localStorage.setItem(STORAGE_INCIDENT_KEY, newId);
      } else {
        localStorage.removeItem(STORAGE_INCIDENT_KEY);
      }
    } catch {}
    globalListeners.forEach(listener => listener({ incidentId: newId }));
  };

  const loadIncident = useCallback(async (id: string | null) => {
    if (!id) {
      setIncidentState(null);
      setIncidentId(null);
      return null;
    }
    try {
      const data = await api.get(id);
      setIncidentState(data);
      setIncidentId(id);
      return data;
    } catch {
      setIncidentState(null);
      return null;
    }
  }, []);

  const setJudgeMode = (enabled: boolean) => {
    setJudgeModeState(enabled);
    try {
      localStorage.setItem(STORAGE_JUDGE_KEY, String(enabled));
    } catch {}
    globalListeners.forEach(listener => listener({ judgeMode: enabled }));
  };

  const setEngineerMode = (enabled: boolean) => {
    setEngineerModeState(enabled);
    try {
      localStorage.setItem(STORAGE_ENGINEER_KEY, String(enabled));
    } catch {}
    globalListeners.forEach(listener => listener({ engineerMode: enabled }));
  };

  return {
    incidentId,
    setIncidentId,
    judgeMode,
    setJudgeMode,
    engineerMode,
    setEngineerMode,
    incident,
    loadIncident,
  };
}
