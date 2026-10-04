"use client";

import { useState, useEffect, useMemo, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Button, Card, Badge, PageHeader, Input, Select, Tooltip, Divider } from "@/components/ui";
import { api, TimelineEvent, TemporalAnalysis } from "@/lib/api";
import { notify } from "@/components/Notification";
import { useActiveIncident } from "@/lib/useIncident";
import { useShell } from "@/lib/useShell";
import { useAuthStore } from "@/lib/auth";
import { DataErrorBoundary } from "@/components/ErrorBoundary";
import {
  ZoomIn, ZoomOut, ArrowLeft, ArrowRight, Maximize, RotateCcw,
  Play, SkipBack, SkipForward, AlertTriangle, Globe, Timer,
  X, Check, Search, Download, Clock
} from "lucide-react";

// Safe Pause icon that doesn't crash when test environments fail to mock Pause in lucide-react
const PauseIcon = ({ className = "h-4.5 w-4.5" }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" fill="currentColor" stroke="none">
    <rect x="6" y="4" width="4" height="16" rx="1" />
    <rect x="14" y="4" width="4" height="16" rx="1" />
  </svg>
);

type LaneId =
  | "deployment"
  | "configuration"
  | "application-log"
  | "trace"
  | "metric"
  | "robotic-message"
  | "operator-observation"
  | "safety-event";

interface Lane {
  id: LaneId;
  name: string;
  color: string;
  events: TimelineEvent[];
}

interface TimelineControls {
  zoom: number;
  pan: number;
  timeRange: { start: number; end: number };
  showClockDomains: boolean;
  showClockCorrection: boolean;
}

function RealityRewindContent() {
  const { incidentId, judgeMode, engineerMode } = useActiveIncident();
  const { openInspector, addActivity, setIncidentContext } = useShell();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  const router = useRouter();

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login?redirect=/reality-rewind');
    }
  }, [isAuthenticated, authLoading, router]);

  // Show loading while auth is initializing
  if (authLoading) {
    return (
      <div className="flex flex-col gap-4 min-h-screen items-center justify-center p-8">
        <div className="flex h-8 w-8 animate-spin text-primary">
          <svg className="h-8 w-8" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" /></svg>
        </div>
        <p className="text-sm text-[var(--color-text-muted)]">Loading Reality Rewind...</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="flex flex-col gap-4 min-h-screen items-center justify-center p-8">
        <div className="flex h-8 w-8 animate-spin text-primary">
          <svg className="h-8 w-8" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" /></svg>
        </div>
        <p className="text-sm text-[var(--color-text-muted)]">Redirecting to login...</p>
      </div>
    );
  }

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [analysis, setAnalysis] = useState<TemporalAnalysis | null>(null);
  const [lanes, setLanes] = useState<Lane[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [currentTime, setCurrentTime] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState<string[]>([]);
  const [evidenceStatusFilter, setEvidenceStatusFilter] = useState<string[]>([]);
  const [severityFilter, setSeverityFilter] = useState<string[]>([]);
  const [timeRange, setTimeRange] = useState<{ start: number; end: number }>({ start: 0, end: 1 });
  const [controls, setControls] = useState<TimelineControls>({
    zoom: 1,
    pan: 0,
    timeRange: { start: 0, end: 1 },
    showClockDomains: false,
    showClockCorrection: false,
  });

  const [clockDomains, setClockDomains] = useState<Record<string, number[]>>({});
  const animationFrameRef = useRef<number>(0);

  // Load timeline and temporal data
  const loadData = async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const tl = await api.getTimeline(id);
      if (tl && tl.timeline_events) {
        setEvents(tl.timeline_events);
        if (tl.clock_alignment) {
          setClockDomains(tl.clock_alignment as Record<string, number[]>);
        }
      } else {
        setEvents([]);
        setClockDomains({});
      }

      const ta = await api.getTemporalAnalysis(id);
      if (ta) {
        setAnalysis(ta);
      }
    } catch (e: any) {
      setError(e.message || "Failed to load timeline events");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (incidentId) {
      loadData(incidentId);
    }
  }, [incidentId]);

  // Build and set incident context for shell
  useEffect(() => {
    if (incidentId) {
      setIncidentContext({
        id: incidentId,
        title: "Incident Timeline",
        state: "IDLE",
        pipelineStage: "IDLE",
        evidenceCoverage: 0,
        modelProvider: "Local Fixtures",
        backendStatus: "online",
        processingMode: judgeMode ? "judge" : engineerMode ? "engineer" : "autonomous",
        isDemonstration: false,
      });
    } else {
      setIncidentContext(null);
    }
  }, [incidentId, judgeMode, engineerMode]);

  // Group events into predefined lanes
  const groupedLanes: Lane[] = useMemo(() => {
    if (!events.length) {
      return [
        { id: "deployment" as LaneId, name: "Deployment Changes", color: "var(--color-brand-primary)", events: [] },
        { id: "configuration" as LaneId, name: "Configuration Changes", color: "var(--color-brand-info)", events: [] },
        { id: "application-log" as LaneId, name: "Application Logs", color: "var(--color-brand-danger)", events: [] },
        { id: "trace" as LaneId, name: "Traces", color: "var(--color-brand-warning)", events: [] },
        { id: "metric" as LaneId, name: "Metrics", color: "var(--color-brand-danger)", events: [] },
        { id: "robotic-message" as LaneId, name: "Robotic Messages", color: "var(--color-brand-danger)", events: [] },
        { id: "operator-observation" as LaneId, name: "Operator Observations", color: "var(--color-brand-success)", events: [] },
        { id: "safety-event" as LaneId, name: "Safety Events", color: "var(--color-accent)", events: [] },
      ];
    }

    const laneMap: Partial<Record<LaneId, TimelineEvent[]>> = {
      deployment: [],
      configuration: [],
      "application-log": [],
      trace: [],
      metric: [],
      "robotic-message": [],
      "operator-observation": [],
      "safety-event": [],
    };

    events.forEach((ev) => {
      let lane: LaneId | undefined;
      const sourceType = (ev.source_type || "").toLowerCase();
      const laneFromEvent = (ev.lane || "").toLowerCase();
      const source = (ev.source || "").toLowerCase();
      const message = (ev.message || "").toLowerCase();

      if (sourceType.includes("deploy") || laneFromEvent.includes("deploy") || message.includes("deploy")) {
        lane = "deployment";
      } else if (sourceType.includes("config") || laneFromEvent.includes("config") || message.includes("config")) {
        lane = "configuration";
      } else if (sourceType.includes("log") || laneFromEvent.includes("log") || source.includes("log") || message.includes("log")) {
        lane = "application-log";
      } else if (sourceType.includes("trace") || laneFromEvent.includes("trace") || message.includes("trace")) {
        lane = "trace";
      } else if (sourceType.includes("metric") || laneFromEvent.includes("metric") || message.includes("metric")) {
        lane = "metric";
      } else if (sourceType.includes("robotic") || laneFromEvent.includes("robotic") || source.includes("ros") || message.includes("robot")) {
        lane = "robotic-message";
      } else if (sourceType.includes("operator") || laneFromEvent.includes("operator") || message.includes("operator")) {
        lane = "operator-observation";
      } else if (
        sourceType.includes("safety") ||
        laneFromEvent.includes("safety") ||
        message.includes("halt") ||
        message.includes("stop") ||
        message.includes("emergency")
      ) {
        lane = "safety-event";
      } else {
        lane = "application-log";
      }

      if (lane && laneMap[lane]) {
        laneMap[lane]!.push(ev);
      }
    });

    return [
      { id: "deployment", name: "Deployment Changes", color: "var(--color-brand-primary)", events: laneMap.deployment ?? [] },
      { id: "configuration", name: "Configuration Changes", color: "var(--color-brand-info)", events: laneMap.configuration ?? [] },
      { id: "application-log", name: "Application Logs", color: "var(--color-brand-danger)", events: laneMap["application-log"] ?? [] },
      { id: "trace", name: "Traces", color: "var(--color-brand-warning)", events: laneMap.trace ?? [] },
      { id: "metric", name: "Metrics", color: "var(--color-brand-danger)", events: laneMap.metric ?? [] },
      { id: "robotic-message", name: "Robotic Messages", color: "var(--color-brand-danger)", events: laneMap["robotic-message"] ?? [] },
      { id: "operator-observation", name: "Operator Observations", color: "var(--color-brand-success)", events: laneMap["operator-observation"] ?? [] },
      { id: "safety-event", name: "Safety Events", color: "var(--color-accent)", events: laneMap["safety-event"] ?? [] },
    ];
  }, [events]);

  // Determine time range from events
  useEffect(() => {
    if (!events.length) {
      setTimeRange({ start: 0, end: 1 });
      setControls((prev) => ({ ...prev, timeRange: { start: 0, end: 1 } }));
      return;
    }
    const times = events
      .map((e) => e.relative_timestamp_s ?? 0)
      .filter((t) => !isNaN(t));
    const min = Math.min(...times);
    const max = Math.max(...times);
    const padding = Math.max(0.1, (max - min) * 0.05);
    const startVal = Math.max(0, min - padding);
    const endVal = max + padding;
    setTimeRange({ start: startVal, end: endVal });
    setControls((prev) => ({ ...prev, timeRange: { start: startVal, end: endVal } }));
  }, [events]);

  // Filtered and sorted events based on UI filters
  const filteredEvents = useMemo(() => {
    return events
      .filter((ev) => {
        if (searchQuery) {
          const q = searchQuery.toLowerCase();
          const matches =
            (ev.message?.toLowerCase().includes(q) ?? false) ||
            (ev.source?.toLowerCase().includes(q) ?? false) ||
            (ev.source_type?.toLowerCase().includes(q) ?? false) ||
            (ev.lane?.toLowerCase().includes(q) ?? false);
          if (!matches) return false;
        }
        if (sourceFilter.length > 0) {
          const src = ev.source_type ?? ev.lane ?? "";
          if (!sourceFilter.includes(src)) return false;
        }
        if (evidenceStatusFilter.length > 0) {
          const status = ev.status ?? "";
          if (!evidenceStatusFilter.includes(status)) return false;
        }
        if (severityFilter.length > 0) {
          const sev = ev.attributes?.severity?.toString() ?? "";
          if (!severityFilter.includes(sev)) return false;
        }
        return true;
      })
      .sort((a, b) => {
        const ta = a.relative_timestamp_s ?? 0;
        const tb = b.relative_timestamp_s ?? 0;
        if (ta !== tb) return ta - tb;
        const na = a.timestamp_ns ?? 0;
        const nb = b.timestamp_ns ?? 0;
        if (na !== nb) return na - nb;
        return (a.event_id ?? "").localeCompare(b.event_id ?? "");
      });
  }, [
    events,
    searchQuery,
    sourceFilter,
    evidenceStatusFilter,
    severityFilter,
  ]);

  // Update lanes with filtered events
  useEffect(() => {
    setLanes(
      groupedLanes.map((lane) => {
        const laneEvents = filteredEvents.filter(
          (ev) =>
            ((ev.source_type ?? ev.lane ?? "").toLowerCase() === lane.id ||
              (ev.source_type ?? "").toLowerCase().includes(lane.id) ||
              (ev.lane ?? "").toLowerCase().includes(lane.id))
        );
        return { ...lane, events: laneEvents };
      })
    );
  }, [filteredEvents, groupedLanes]);

  // Playback animation loop
  useEffect(() => {
    if (!isPlaying) {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = 0;
      }
      return;
    }

    const { start, end } = timeRange;
    const duration = Math.max(0.001, end - start);
    let lastTimestamp = performance.now();

    const step = (now: number) => {
      const dt = (now - lastTimestamp) / 1000;
      lastTimestamp = now;

      setCurrentTime((prev) => {
        const next = prev + dt * playbackSpeed;
        if (next >= end) {
          return start;
        }
        return next;
      });

      animationFrameRef.current = requestAnimationFrame(step);
    };

    animationFrameRef.current = requestAnimationFrame(step);
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [isPlaying, playbackSpeed, timeRange]);

  const handleSelectEvent = (eventId: string | null) => {
    setSelectedEventId(eventId);
    if (eventId) {
      const event = filteredEvents.find((ev) => (ev.event_id ?? "") === eventId);
      if (event) {
        openInspector("timeline", {
          mode: "timeline",
          eventId,
          eventData: event,
        });
        addActivity({
          type: "system",
          message: `Inspecting timeline event: ${event.event_id}`,
          dismissible: true,
        });
      }
    }
  };

  const handleJumpToFailure = () => {
    const failureEvent = filteredEvents.find(
      (ev) =>
        (ev.message ?? "").toLowerCase().includes("halt") ||
        (ev.message ?? "").toLowerCase().includes("emergency stop") ||
        (ev.status ?? "").toLowerCase() === "failed" ||
        (ev.status ?? "").toLowerCase() === "error" ||
        (ev.attributes?.severity ?? "").toString().toLowerCase() === "critical"
    );
    if (failureEvent && failureEvent.relative_timestamp_s !== undefined) {
      const time = failureEvent.relative_timestamp_s;
      setCurrentTime(time);
      setSelectedEventId(failureEvent.event_id ?? null);
      notify("Jumped to failure event", "info");
    } else {
      notify("No failure event found in timeline", "warning");
    }
  };

  const handleZoomIn = () => {
    setControls((prev) => ({ ...prev, zoom: Math.min(10, prev.zoom * 1.2) }));
  };

  const handleZoomOut = () => {
    setControls((prev) => ({ ...prev, zoom: Math.max(0.1, prev.zoom / 1.2) }));
  };

  const handlePanLeft = () => {
    setControls((prev) => ({ ...prev, pan: prev.pan + 50 }));
  };

  const handlePanRight = () => {
    setControls((prev) => ({ ...prev, pan: prev.pan - 50 }));
  };

  const handleFitIncident = () => {
    if (!events.length) return;
    const times = events
      .map((e) => e.relative_timestamp_s ?? 0)
      .filter((t) => !isNaN(t));
    const min = Math.min(...times);
    const max = Math.max(...times);
    const padding = Math.max(0.1, (max - min) * 0.05);
    setTimeRange({ start: Math.max(0, min - padding), end: max + padding });
    setControls((prev) => ({
      ...prev,
      timeRange: { start: Math.max(0, min - padding), end: max + padding },
      pan: 0,
      zoom: 1,
    }));
  };

  const handleReset = () => {
    setCurrentTime(0);
    setIsPlaying(false);
    setSelectedEventId(null);
    handleFitIncident();
  };

  const handleStepBack = () => {
    const prevEvents = filteredEvents.filter((ev) => (ev.relative_timestamp_s ?? 0) < currentTime);
    if (prevEvents.length > 0) {
      const prev = prevEvents[prevEvents.length - 1];
      setCurrentTime(prev.relative_timestamp_s ?? 0);
      setSelectedEventId(prev.event_id ?? null);
    }
  };

  const handleStepForward = () => {
    const nextEvents = filteredEvents.filter((ev) => (ev.relative_timestamp_s ?? 0) > currentTime);
    if (nextEvents.length > 0) {
      const next = nextEvents[0];
      setCurrentTime(next.relative_timestamp_s ?? 0);
      setSelectedEventId(next.event_id ?? null);
    }
  };

  const handleSetPlaybackSpeed = (speed: number) => {
    setPlaybackSpeed(speed);
  };

  const handleSourceFilterChange = (value: string) => {
    if (value === "all") {
      setSourceFilter([]);
      return;
    }
    if (sourceFilter.includes(value)) {
      setSourceFilter(sourceFilter.filter((v) => v !== value));
    } else {
      setSourceFilter([...sourceFilter, value]);
    }
  };

  const handleEvidenceStatusFilterChange = (value: string) => {
    if (evidenceStatusFilter.includes(value)) {
      setEvidenceStatusFilter(evidenceStatusFilter.filter((v) => v !== value));
    } else {
      setEvidenceStatusFilter([...evidenceStatusFilter, value]);
    }
  };

  const handleSeverityFilterChange = (value: string) => {
    if (severityFilter.includes(value)) {
      setSeverityFilter(severityFilter.filter((v) => v !== value));
    } else {
      setSeverityFilter([...severityFilter, value]);
    }
  };

  const handleTimeRangeChange = (range: { start: number; end: number }) => {
    setTimeRange(range);
    setControls((prev) => ({ ...prev, timeRange: range }));
  };

  const handleToggleClockDomains = () => {
    setControls((prev) => ({ ...prev, showClockDomains: !prev.showClockDomains }));
  };

  const handleToggleClockCorrection = () => {
    setControls((prev) => ({ ...prev, showClockCorrection: !prev.showClockCorrection }));
  };

  const handleExportTimeline = async () => {
    setLoading(true);
    try {
      const tl = await api.getTimeline(incidentId);
      const timelineStr = JSON.stringify(tl, null, 2);
      const blob = new Blob([timelineStr], { type: "application/json" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `timeline-${incidentId}.json`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      notify("Timeline exported successfully!", "success");
    } catch (e: any) {
      notify(e.message || "Failed to export timeline", "error");
    } finally {
      setLoading(false);
    }
  };

  const sourceTypes = useMemo(() => {
    const set = new Set<string>();
    events.forEach((ev) => {
      const src = ev.source_type ?? ev.lane ?? "unknown";
      if (src) set.add(src);
    });
    return Array.from(set).sort();
  }, [events]);

  const statusValues = useMemo(() => {
    const set = new Set<string>();
    events.forEach((ev) => {
      const status = ev.status ?? "";
      if (status) set.add(status);
    });
    return Array.from(set).sort();
  }, [events]);

  const severityValues = useMemo(() => {
    const set = new Set<string>();
    events.forEach((ev) => {
      const sev = ev.attributes?.severity?.toString();
      if (sev) set.add(sev);
    });
    return Array.from(set).sort();
  }, [events]);

  // Current selected event or event nearest scrubber position
  const currentEvent = useMemo(() => {
    if (selectedEventId) {
      return filteredEvents.find((ev) => ev.event_id === selectedEventId) ?? null;
    }
    const past = filteredEvents.filter((ev) => (ev.relative_timestamp_s ?? 0) <= currentTime);
    if (!past.length) return filteredEvents[0] ?? null;
    return past[past.length - 1];
  }, [filteredEvents, selectedEventId, currentTime]);

  return (
    <div className="min-h-screen bg-[var(--theme-background)] text-[var(--theme-foreground)] p-6">
      {/* Header */}
      <PageHeader
        title="Reality Rewind"
        subtitle="Synchronized multi-source timeline reconstruction & causal event playback"
        badge={
          <Badge tone={events.length > 0 ? "success" : "secondary"} dot={true}>
            {events.length} Synchronized Events ({timeRange.end.toFixed(3)}s span)
          </Badge>
        }
      />

      {/* Mode Indicators */}
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <Badge tone={judgeMode ? "primary" : "muted"}>
          {judgeMode ? "Judge Mode: Formal Causal Verification Active" : "Judge Mode: Disabled"}
        </Badge>
        <Badge tone={engineerMode ? "success" : "muted"}>
          {engineerMode ? "Engineer Mode: Raw Signal Diagnostic Active" : "Engineer Mode: Standard"}
        </Badge>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mb-6 p-4 bg-[var(--color-brand-danger)]/10 border border-[var(--color-brand-danger)]/25 rounded-xl text-[var(--color-brand-danger)] text-sm flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4.5 w-4.5 text-[var(--color-brand-danger)] shrink-0" />
            <span>{error}</span>
          </div>
          <button
            type="button"
            onClick={() => setError(null)}
            className="text-[var(--color-brand-danger)] hover:text-[var(--color-text-primary)] text-xs font-semibold uppercase px-2 py-1 rounded hover:bg-[var(--color-brand-danger)]/20 transition-colors"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Main Unified Content Column with Clean Inter-Component Spacing */}
      <div className="space-y-8">
        {/* Controls Toolbar */}
        <div className="flex flex-wrap items-center gap-3 p-4 bg-[var(--color-surface)]/50 rounded-xl border border-[var(--color-border)]">
          {/* Zoom / Pan Cluster */}
          <div className="flex items-center gap-1.5 p-1 bg-[var(--color-surface-2)] border border-[var(--color-border)] rounded-xl">
            <Tooltip content="Zoom In" position="bottom">
              <Button
                variant="outline"
                size="sm"
                onClick={handleZoomIn}
                className="h-9 w-9 p-0 flex items-center justify-center border-[var(--color-border)] hover:border-[var(--color-border-strong)] hover:bg-[var(--color-surface-2)]"
                aria-label="Zoom In"
              >
                <ZoomIn className="h-5 w-5 text-[var(--color-text-primary)]/90" />
              </Button>
            </Tooltip>
            <Tooltip content="Zoom Out" position="bottom">
              <Button
                variant="outline"
                size="sm"
                onClick={handleZoomOut}
                className="h-9 w-9 p-0 flex items-center justify-center border-[var(--color-border)] hover:border-[var(--color-border-strong)] hover:bg-[var(--color-surface-2)]"
                aria-label="Zoom Out"
              >
                <ZoomOut className="h-5 w-5 text-[var(--color-text-primary)]/90" />
              </Button>
            </Tooltip>
            <Tooltip content="Pan Left" position="bottom">
              <Button
                variant="outline"
                size="sm"
                onClick={handlePanLeft}
                className="h-9 w-9 p-0 flex items-center justify-center border-[var(--color-border)] hover:border-[var(--color-border-strong)] hover:bg-[var(--color-surface-2)]"
                aria-label="Pan Left"
              >
                <ArrowLeft className="h-5 w-5 text-[var(--color-text-primary)]/90" />
              </Button>
            </Tooltip>
            <Tooltip content="Pan Right" position="bottom">
              <Button
                variant="outline"
                size="sm"
                onClick={handlePanRight}
                className="h-9 w-9 p-0 flex items-center justify-center border-[var(--color-border)] hover:border-[var(--color-border-strong)] hover:bg-[var(--color-surface-2)]"
                aria-label="Pan Right"
              >
                <ArrowRight className="h-5 w-5 text-[var(--color-text-primary)]/90" />
              </Button>
            </Tooltip>
            <Tooltip content="Fit Incident to View" position="bottom">
              <Button
                variant="outline"
                size="sm"
                onClick={handleFitIncident}
                className="h-9 w-9 p-0 flex items-center justify-center border-[var(--color-border)] hover:border-[var(--color-border-strong)] hover:bg-[var(--color-surface-2)]"
                aria-label="Fit Incident to View"
              >
                <Maximize className="h-5 w-5 text-[var(--color-text-primary)]/90" />
              </Button>
            </Tooltip>
            <Tooltip content="Reset View" position="bottom">
              <Button
                variant="outline"
                size="sm"
                onClick={handleReset}
                className="h-9 w-9 p-0 flex items-center justify-center border-[var(--color-border)] hover:border-[var(--color-border-strong)] hover:bg-[var(--color-surface-2)]"
                aria-label="Reset View"
              >
                <RotateCcw className="h-5 w-5 text-[var(--color-text-primary)]/90" />
              </Button>
            </Tooltip>
          </div>

          <Divider orientation="vertical" className="h-7 mx-1 border-[var(--color-border)]" />

          {/* Playback Cluster */}
          <div className="flex items-center gap-1.5 p-1 bg-[var(--color-surface-2)] border border-[var(--color-border)] rounded-xl">
            <Tooltip content="Play" position="bottom">
              <Button
                variant={!isPlaying ? "primary" : "outline"}
                size="sm"
                onClick={() => setIsPlaying(true)}
                disabled={loading || isPlaying}
                aria-label="Play"
                className={`h-9 px-3 flex items-center gap-1.5 font-medium ${!isPlaying ? "bg-[var(--color-brand-primary)] text-[var(--color-text-primary)]" : "border-[var(--color-border)] text-[var(--color-text-muted)]"}`}
              >
                <Play className="h-4.5 w-4.5" />
                <span>Play</span>
              </Button>
            </Tooltip>
            <Tooltip content="Pause" position="bottom">
              <Button
                variant={isPlaying ? "danger" : "outline"}
                size="sm"
                onClick={() => setIsPlaying(false)}
                disabled={loading || !isPlaying}
                aria-label="Pause"
                className={`h-9 px-3 flex items-center gap-1.5 font-medium ${isPlaying ? "bg-[var(--color-brand-danger)] text-[var(--color-text-primary)] ring-1 ring-[var(--color-brand-danger)]/40" : "border-[var(--color-border)] text-[var(--color-text-muted)]"}`}
              >
                <PauseIcon className="h-4.5 w-4.5" />
                <span>Pause</span>
              </Button>
            </Tooltip>
            <Tooltip content="Step Backward" position="bottom">
              <Button
                variant="outline"
                size="sm"
                onClick={handleStepBack}
                className="h-9 w-9 p-0 flex items-center justify-center border-[var(--color-border)] hover:border-[var(--color-border-strong)] hover:bg-[var(--color-surface-2)]"
                aria-label="Step Backward"
              >
                <SkipBack className="h-5 w-5 text-[var(--color-text-primary)]/90" />
              </Button>
            </Tooltip>
            <Tooltip content="Step Forward" position="bottom">
              <Button
                variant="outline"
                size="sm"
                onClick={handleStepForward}
                className="h-9 w-9 p-0 flex items-center justify-center border-[var(--color-border)] hover:border-[var(--color-border-strong)] hover:bg-[var(--color-surface-2)]"
                aria-label="Step Forward"
              >
                <SkipForward className="h-5 w-5 text-[var(--color-text-primary)]/90" />
              </Button>
            </Tooltip>
            <div className="flex items-center pl-1">
              <Select
                aria-label="Playback speed"
                value={String(playbackSpeed)}
                onChange={(e) => handleSetPlaybackSpeed(Number(e.target.value))}
                className="w-24 h-9 text-xs"
                options={[
                  { value: "0.5", label: "0.5×" },
                  { value: "1", label: "1×" },
                  { value: "2", label: "2×" },
                  { value: "5", label: "5×" },
                ]}
              />
            </div>
          </div>

          <Divider orientation="vertical" className="h-7 mx-1 border-[var(--color-border)]" />

          {/* Actions Cluster */}
          <div className="flex items-center gap-2">
            <Tooltip content="Jump to Failure" position="bottom">
              <Button
                variant="outline"
                size="sm"
                onClick={handleJumpToFailure}
                aria-label="Jump to Failure"
                className="h-9 px-3.5 flex items-center gap-2 border-[var(--color-border)] hover:border-danger/30 hover:bg-[var(--color-brand-danger)]/5 text-xs font-medium"
              >
                <AlertTriangle className="h-4.5 w-4.5 text-[var(--color-brand-danger)]" />
                <span>Jump to Failure</span>
              </Button>
            </Tooltip>
            <Tooltip content="Export Timeline" position="bottom">
              <Button
                variant="outline"
                size="sm"
                onClick={handleExportTimeline}
                disabled={loading}
                aria-label="Export Timeline"
                className="h-9 px-3.5 flex items-center gap-2 border-[var(--color-border)] hover:border-[var(--color-border-strong)] hover:bg-[var(--color-surface-2)] text-xs font-medium"
              >
                <Download className="h-4.5 w-4.5 text-[var(--color-text-primary)]/90" />
                <span>{loading ? "Exporting..." : "Export JSON"}</span>
              </Button>
            </Tooltip>
          </div>

          <Divider orientation="vertical" className="h-7 mx-1 border-[var(--color-border)]" />

          {/* Toggles Cluster */}
          <div className="flex items-center gap-2">
            <Tooltip content="Toggle Clock Domain Comparison" position="bottom">
              <Button
                variant="outline"
                size="sm"
                onClick={handleToggleClockDomains}
                aria-label="Toggle Clock Domain Comparison"
                className={`h-9 px-3 flex items-center gap-2 border-[var(--color-border)] text-xs font-medium ${controls.showClockDomains ? "bg-[var(--color-brand-primary)]/10 border-[var(--color-brand-primary)]/30 text-[var(--color-brand-primary)]" : "hover:bg-[var(--color-surface-2)] text-[var(--color-text-muted)]"}`}
              >
                <Globe className="h-4.5 w-4.5" />
                <span>Clock Domains {controls.showClockDomains ? "ON" : "OFF"}</span>
              </Button>
            </Tooltip>
            <Tooltip content="Toggle Clock Correction Visibility" position="bottom">
              <Button
                variant="outline"
                size="sm"
                onClick={handleToggleClockCorrection}
                aria-label="Toggle Clock Correction Visibility"
                className={`h-9 px-3 flex items-center gap-2 border-[var(--color-border)] text-xs font-medium ${controls.showClockCorrection ? "bg-[var(--color-brand-warning)]/10 border-[var(--color-brand-warning)]/30 text-[var(--color-brand-warning)]" : "hover:bg-[var(--color-surface-2)] text-[var(--color-text-muted)]"}`}
              >
                <Timer className="h-4.5 w-4.5" />
                <span>Clock Correction {controls.showClockCorrection ? "ON" : "OFF"}</span>
              </Button>
            </Tooltip>
          </div>

          <Divider orientation="vertical" className="h-7 mx-1 border-[var(--color-border)]" />

          {/* Time Range Cluster */}
          <div className="flex items-center gap-2 text-xs">
            <span className="text-[var(--color-text-muted)] font-medium">Time Range:</span>
            <div className="flex items-center gap-1.5">
              <Input
                type="number"
                value={timeRange.start}
                min={0}
                step={0.001}
                onChange={(e) => handleTimeRangeChange({ start: Number(e.target.value), end: timeRange.end })}
                className="w-24 h-9 text-center font-mono text-xs"
                placeholder="Start"
                aria-label="Start time"
              />
              <span className="text-[var(--color-text-muted)] font-mono">→</span>
              <Input
                type="number"
                value={timeRange.end}
                min={0}
                step={0.001}
                onChange={(e) => handleTimeRangeChange({ start: timeRange.start, end: Number(e.target.value) })}
                className="w-24 h-9 text-center font-mono text-xs"
                placeholder="End"
                aria-label="End time"
              />
            </div>
          </div>
        </div>

        {/* Synchronized Multi-Lane Reality Timeline */}
        <Card title="Synchronized Multi-Lane Reality Timeline">
          <div className="space-y-6">
            {/* Interactive Player & Scrubber */}
            <div className="p-4 rounded-xl bg-[var(--theme-surface)]/40 border border-[var(--color-border)] space-y-3">
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-[var(--color-text-muted)]">t={timeRange.start.toFixed(3)}s (Baseline)</span>
                <span className="text-[var(--color-brand-primary)] font-bold text-sm bg-[var(--color-brand-primary)]/10 px-3 py-1 rounded-lg border border-[var(--color-brand-primary)]/20 tabular-nums">
                  Scrubber: {currentTime.toFixed(3)}s / {timeRange.end.toFixed(3)}s
                </span>
                <span className="text-[var(--color-text-muted)]">t={timeRange.end.toFixed(3)}s (Final)</span>
              </div>

              {/* Range Slider */}
              <input
                type="range"
                min={timeRange.start}
                max={Math.max(timeRange.end, timeRange.start + 0.001)}
                step={0.001}
                value={currentTime}
                onChange={(e) => {
                  setCurrentTime(parseFloat(e.target.value));
                  setSelectedEventId(null);
                }}
                aria-label="Timeline scrubber position"
                className="w-full accent-primary cursor-pointer h-2.5 bg-[var(--color-text-primary)]/10 rounded-lg appearance-none transition-all"
              />
            </div>

            {/* Dynamic Timeline Lanes */}
            <div className="space-y-3 relative">
              {lanes.map((lane) => {
                const laneEvents = lane.events;
                const activeInLane = laneEvents.filter((e) => (e.relative_timestamp_s ?? 0) <= currentTime);
                const duration = Math.max(0.001, timeRange.end - timeRange.start);

                return (
                  <div
                    key={lane.id}
                    className="p-3 rounded-xl bg-[var(--color-surface)]/40 border border-[var(--color-border)] flex items-center gap-4 hover:border-[var(--color-border)] transition-colors"
                  >
                    <div className="flex items-center gap-2.5 w-48 shrink-0">
                      <div
                        className="w-3 h-3 rounded-full shrink-0 shadow-sm"
                        style={{ backgroundColor: lane.color }}
                      />
                      <span className="text-xs font-semibold text-[var(--color-text-primary)]/90 truncate">
                        {lane.name}
                      </span>
                    </div>

                    {/* Timeline Bar with Event Markers */}
                    <div className="flex-1 h-3.5 bg-[var(--theme-surface)]/40 rounded-full overflow-hidden relative border border-[var(--color-border)]">
                      {/* Active progress track */}
                      <div
                        className="absolute left-0 top-0 bottom-0 opacity-25 transition-all duration-75"
                        style={{
                          width: `${Math.min(100, Math.max(0, ((currentTime - timeRange.start) / duration) * 100))}%`,
                          backgroundColor: lane.color,
                        }}
                      />

                      {/* Event Markers */}
                      {laneEvents.map((evt, idx) => {
                        const evtTime = evt.relative_timestamp_s ?? 0;
                        const posPercent = Math.min(100, Math.max(0, ((evtTime - timeRange.start) / duration) * 100));
                        const isPast = evtTime <= currentTime;
                        const isCurrent = currentEvent?.event_id === evt.event_id;
                        const isError =
                          (evt.message ?? "").toLowerCase().includes("halt") ||
                          (evt.message ?? "").toLowerCase().includes("emergency stop") ||
                          (evt.status ?? "").toLowerCase() === "error" ||
                          (evt.status ?? "").toLowerCase() === "failed";

                        return (
                          <button
                            key={idx}
                            type="button"
                            title={`${evt.message} (t=${evtTime.toFixed(3)}s)`}
                            onClick={() => {
                              setCurrentTime(parseFloat(evtTime.toFixed(3)));
                              handleSelectEvent(evt.event_id ?? null);
                            }}
                            style={{ left: `${posPercent}%` }}
                            className={`absolute top-0.5 bottom-0.5 w-2.5 -ml-1.25 rounded-full transition-all cursor-pointer z-10 ${
                              isCurrent
                                ? "ring-2 ring-primary ring-offset-1 ring-offset-black scale-125 z-30 bg-[var(--color-brand-primary)]"
                                : isError
                                ? "bg-[var(--color-brand-danger)] ring-1 ring-[var(--color-brand-danger)]/50"
                                : isPast
                                ? "bg-[var(--color-text-primary)] opacity-90 hover:opacity-100"
                                : "bg-[var(--color-text-primary)]/30 hover:bg-[var(--color-text-primary)]/60"
                            }`}
                            aria-label={`Event at ${evtTime.toFixed(3)}s: ${evt.message}`}
                          />
                        );
                      })}
                    </div>

                    {/* Lane Count Badge */}
                    <div className="shrink-0 w-16 text-right">
                      <Badge tone={activeInLane.length > 0 ? "primary" : "secondary"}>
                        {activeInLane.length} / {laneEvents.length}
                      </Badge>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Evidence Legend */}
            <div className="flex flex-wrap gap-4 text-xs pt-2 border-t border-[var(--color-border)]">
              <div className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full bg-[var(--color-brand-primary)]" />
                <span className="text-[var(--color-text-muted)]">Deployment</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full bg-[var(--color-brand-info)]" />
                <span className="text-[var(--color-text-muted)]">Configuration</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full bg-[var(--color-brand-danger)]" />
                <span className="text-[var(--color-text-muted)]">Logs</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full bg-[var(--color-brand-warning)]" />
                <span className="text-[var(--color-text-muted)]">Traces</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full bg-[var(--color-brand-danger)]" />
                <span className="text-[var(--color-text-muted)]">Metrics</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full bg-[var(--color-brand-danger)]" />
                <span className="text-[var(--color-text-muted)]">Robotic</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full bg-[var(--color-brand-success)]" />
                <span className="text-[var(--color-text-muted)]">Operator</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full bg-[var(--color-accent)]" />
                <span className="text-[var(--color-text-muted)]">Safety</span>
              </div>
            </div>
          </div>
        </Card>

        {/* Filters Bar */}
        <div className="p-4 bg-[var(--color-surface)]/50 rounded-xl border border-[var(--color-border)] flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-xs text-[var(--color-text-muted)] font-medium">Search:</span>
            <Input
              type="text"
              placeholder="Search events..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              leftIcon={<Search className="h-4.5 w-4.5 text-[var(--color-text-muted)]" />}
              size="sm"
              className="w-64 h-9 text-xs"
              aria-label="Search events"
            />
          </div>

          <Divider orientation="vertical" className="h-6 mx-1 border-[var(--color-border)]" />

          <div className="flex items-center gap-2">
            <span className="text-xs text-[var(--color-text-muted)] font-medium">Source:</span>
            <div className="flex flex-wrap gap-1.5">
              {sourceTypes.map((src) => (
                <button
                  key={src}
                  type="button"
                  onClick={() => handleSourceFilterChange(src)}
                  className={`h-7 px-2.5 rounded-lg text-xs font-mono transition-all border ${
                    sourceFilter.includes(src)
                      ? "bg-[var(--color-brand-primary)] text-[var(--color-text-primary)] border-[var(--color-brand-primary)]/50 shadow-sm font-semibold"
                      : "bg-[var(--color-surface-2)] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)] border-[var(--color-border)]"
                  }`}
                >
                  {src}
                </button>
              ))}
            </div>
          </div>

          <Divider orientation="vertical" className="h-6 mx-1 border-[var(--color-border)]" />

          <div className="flex items-center gap-2">
            <span className="text-xs text-[var(--color-text-muted)] font-medium">Evidence Status:</span>
            <div className="flex flex-wrap gap-1.5">
              {statusValues.map((status) => (
                <button
                  key={status}
                  type="button"
                  onClick={() => handleEvidenceStatusFilterChange(status)}
                  className={`h-7 px-2.5 rounded-lg text-xs font-mono transition-all border ${
                    evidenceStatusFilter.includes(status)
                      ? "bg-[var(--color-brand-primary)] text-[var(--color-text-primary)] border-[var(--color-brand-primary)]/50 shadow-sm font-semibold"
                      : "bg-[var(--color-surface-2)] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)] border-[var(--color-border)]"
                  }`}
                >
                  {status}
                </button>
              ))}
            </div>
          </div>

          <Divider orientation="vertical" className="h-6 mx-1 border-[var(--color-border)]" />

          <div className="flex items-center gap-2">
            <span className="text-xs text-[var(--color-text-muted)] font-medium">Severity:</span>
            <div className="flex flex-wrap gap-1.5">
              {severityValues.map((sev) => (
                <button
                  key={sev}
                  type="button"
                  onClick={() => handleSeverityFilterChange(sev)}
                  className={`h-7 px-2.5 rounded-lg text-xs font-mono transition-all border ${
                    severityFilter.includes(sev)
                      ? "bg-[var(--color-brand-primary)] text-[var(--color-text-primary)] border-[var(--color-brand-primary)]/50 shadow-sm font-semibold"
                      : "bg-[var(--color-surface-2)] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)] border-[var(--color-border)]"
                  }`}
                >
                  {sev}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Active Event Inspector */}
        <Card title="Active Event Inspector">
          {currentEvent ? (
            <div className="space-y-5">
              {/* Event Top Bar */}
              <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-[var(--color-border)]">
                <div className="flex items-center gap-2.5">
                  <Badge
                    tone={
                      currentEvent.source_type === "deployment"
                        ? "primary"
                        : currentEvent.source_type === "configuration"
                        ? "secondary"
                        : currentEvent.source_type === "log"
                        ? "danger"
                        : currentEvent.source_type === "trace"
                        ? "amber"
                        : currentEvent.source_type === "metric"
                        ? "muted"
                        : currentEvent.source_type === "robotic"
                        ? "accent"
                        : currentEvent.source_type === "operator"
                        ? "secondary"
                        : currentEvent.source_type === "safety"
                        ? "danger"
                        : "primary"
                    }
                  >
                    {currentEvent.source_type ?? "Event"}
                  </Badge>
                  <span className="font-mono text-xs font-semibold text-[var(--color-brand-primary)] bg-[var(--color-brand-primary)]/10 px-2 py-0.5 rounded border border-[var(--color-brand-primary)]/20">
                    t={
                      currentEvent.relative_timestamp_s !== undefined
                        ? currentEvent.relative_timestamp_s.toFixed(3)
                        : "0.000"
                    }s
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge
                    tone={
                      (currentEvent.message ?? "").toLowerCase().includes("halt") ||
                      (currentEvent.message ?? "").toLowerCase().includes("emergency stop")
                        ? "danger"
                        : (currentEvent.relative_timestamp_s ?? 0) <= currentTime
                        ? "success"
                        : "muted"
                    }
                  >
                    {(currentEvent.message ?? "").toLowerCase().includes("halt")
                      ? "HALT"
                      : (currentEvent.relative_timestamp_s ?? 0) <= currentTime
                      ? "EXECUTED"
                      : "PENDING"}
                  </Badge>
                  {currentEvent.attributes?.reconstructed && (
                    <Badge tone="muted">RECONSTRUCTED</Badge>
                  )}
                </div>
              </div>

              {/* Event Headline */}
              <div>
                <h3 className="text-base font-semibold text-[var(--color-text-primary)] leading-snug">
                  {currentEvent.message}
                </h3>
                <p className="text-xs text-[var(--color-text-muted)] font-mono mt-1 flex items-center gap-2">
                  <span>Source: <span className="text-[var(--color-text-primary)]/90 font-semibold">{currentEvent.source ?? "in-memory"}</span></span>
                  {currentEvent.event_id && (
                    <>
                      <span className="text-[var(--color-text-primary)]/20">•</span>
                      <span>ID: <span className="text-[var(--color-brand-primary)]">{currentEvent.event_id}</span></span>
                    </>
                  )}
                </p>
              </div>

              {/* Two-column layout for details */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Attributes breakdown */}
                {currentEvent.attributes && Object.keys(currentEvent.attributes).length > 0 && (
                  <div className="p-3.5 rounded-xl bg-[var(--theme-surface)]/40 border border-[var(--color-border)] space-y-2">
                    <p className="text-[11px] font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">
                      Event Telemetry Attributes
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono">
                      {Object.entries(currentEvent.attributes).map(([k, v]) => (
                        <div key={k} className="flex items-center justify-between border-b border-[var(--color-border)] pb-1 gap-2">
                          <span className="text-[var(--color-text-muted)] truncate">{k}:</span>
                          <span className="text-[var(--color-brand-primary)] truncate font-medium">{String(v)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Uncertainty, timing, and evidence */}
                <div className="space-y-4">
                  <div className="p-3.5 rounded-xl bg-[var(--theme-surface)]/40 border border-[var(--color-border)] space-y-2 text-xs">
                    <p className="text-[11px] font-semibold text-[var(--color-text-muted)] uppercase tracking-wider mb-1">
                      Timing & Confidence
                    </p>
                    <div className="grid grid-cols-2 gap-2">
                      <div className="flex justify-between border-b border-[var(--color-border)] pb-1">
                        <span className="text-[var(--color-text-muted)]">Relative Time:</span>
                        <span className="font-mono text-[var(--color-text-primary)]">
                          {(currentEvent.relative_timestamp_s ?? 0).toFixed(3)}s
                        </span>
                      </div>
                      {currentEvent.original_timestamp_s !== undefined && (
                        <div className="flex justify-between border-b border-[var(--color-border)] pb-1">
                          <span className="text-[var(--color-text-muted)]">Original Time:</span>
                          <span className="font-mono text-[var(--color-text-primary)]">
                            {currentEvent.original_timestamp_s.toFixed(3)}s
                          </span>
                        </div>
                      )}
                      <div className="flex justify-between border-b border-[var(--color-border)] pb-1">
                        <span className="text-[var(--color-text-muted)]">Uncertainty:</span>
                        <span className="font-mono text-[var(--color-text-primary)]">
                          {((currentEvent.attributes?.uncertainty_ms ?? 0) / 1000).toFixed(3)}s
                        </span>
                      </div>
                      <div className="flex justify-between border-b border-[var(--color-border)] pb-1">
                        <span className="text-[var(--color-text-muted)]">Confidence:</span>
                        <span className="font-mono text-[var(--color-brand-success)] font-semibold">
                          {
                            (currentEvent.attributes?.confidence ?? analysis?.confidence_score ?? 1)
                              .toFixed(3)
                          }
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Supporting & Contradicting Evidence */}
                  {(currentEvent.supporting_artifact_ids?.length || currentEvent.contradicting_artifact_ids?.length) ? (
                    <div className="p-3.5 rounded-xl bg-[var(--theme-surface)]/40 border border-[var(--color-border)] space-y-2 text-xs">
                      <p className="text-[11px] font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">
                        Evidence Links
                      </p>
                      <div className="space-y-1.5">
                        {currentEvent.supporting_artifact_ids?.length && (
                          <div className="flex items-center gap-2">
                            <Check className="h-4 w-4 text-[var(--color-brand-success)] shrink-0" />
                            <span className="text-[var(--color-brand-success)] font-medium">Supporting:</span>
                            <span className="font-mono text-[var(--color-text-primary)]/90">
                              {currentEvent.supporting_artifact_ids.join(", ")}
                            </span>
                          </div>
                        )}
                        {currentEvent.contradicting_artifact_ids?.length && (
                          <div className="flex items-center gap-2">
                            <X className="h-4 w-4 text-[var(--color-brand-danger)] shrink-0" />
                            <span className="text-[var(--color-brand-danger)] font-medium">Contradicting:</span>
                            <span className="font-mono text-[var(--color-text-primary)]/90">
                              {currentEvent.contradicting_artifact_ids.join(", ")}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          ) : (
            <div className="py-8 text-center text-[var(--color-text-muted)]">
              <Clock className="h-8 w-8 mx-auto mb-2 text-[var(--color-text-muted)]/50" />
              <p className="text-sm font-medium">No event selected</p>
              <p className="text-xs text-[var(--color-text-muted)]/70 mt-1">
                Click on an event in the timeline tracks or stream below to inspect its attributes.
              </p>
            </div>
          )}
        </Card>

        {/* Textual Event List (accessible) */}
        <Card title="Synchronized Chronological Event Stream">
          <div className="space-y-4">
            {/* Filter and Search Bar */}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex-1 min-w-[240px]">
                <Input
                  type="text"
                  placeholder="Search events, messages, sources..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  leftIcon={<Search className="h-4.5 w-4.5 text-[var(--color-text-muted)]" />}
                  size="sm"
                  className="w-full font-mono text-xs h-9"
                  aria-label="Search events"
                />
              </div>
              <div className="flex items-center gap-3">
                <Select
                  aria-label="Filter by source lane"
                  value={sourceFilter.length > 0 ? sourceFilter[0] : "all"}
                  onChange={(e) => handleSourceFilterChange(e.target.value)}
                  className="w-40 h-9 text-xs"
                  options={[
                    { value: "all", label: "All Lanes" },
                    ...sourceTypes.map((src) => ({ value: src, label: src })),
                  ]}
                />
                <Badge tone={filteredEvents.length > 0 ? "primary" : "secondary"}>
                  {filteredEvents.length} Events
                </Badge>
              </div>
            </div>

            {/* Event List Container */}
            <div className="h-[460px] overflow-y-auto overflow-x-hidden rounded-xl border border-[var(--color-border)] bg-[var(--theme-surface)]/40 scrollbar-thin scrollbar-thumb-white/10 hover:scrollbar-thumb-white/20 overscroll-contain">
              {/* Sticky Table Header */}
              <div className="sticky top-0 z-10 flex items-center gap-4 px-4 py-2.5 bg-[var(--color-surface)]/95 backdrop-blur border-b border-[var(--color-border)] text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] font-mono select-none">
                <span className="w-24 shrink-0">Time</span>
                <span className="w-36 shrink-0">Lane / Type</span>
                <span className="w-32 shrink-0">Source</span>
                <span className="w-28 shrink-0">Status</span>
                <span className="flex-1 min-w-0">Message</span>
              </div>

              <ul role="list" className="divide-y divide-white/5 text-xs font-mono">
                {filteredEvents.length === 0 ? (
                  <li role="listitem" className="p-12 text-center text-sm text-[var(--color-text-muted)] font-sans">
                    No events match current filters.
                  </li>
                ) : (
                  filteredEvents.map((ev, idx) => {
                    const evtTime = ev.relative_timestamp_s ?? 0;
                    const isExecuted = evtTime <= currentTime;
                    const isSelected = currentEvent?.event_id === ev.event_id;
                    const isDanger =
                      (ev.message ?? "").toLowerCase().includes("halt") ||
                      (ev.message ?? "").toLowerCase().includes("emergency stop") ||
                      (ev.status ?? "").toLowerCase() === "error" ||
                      (ev.status ?? "").toLowerCase() === "failed";

                    return (
                      <li
                        key={ev.event_id ?? idx}
                        role="listitem"
                        onClick={() => {
                          setCurrentTime(parseFloat(evtTime.toFixed(3)));
                          setSelectedEventId(ev.event_id ?? null);
                        }}
                        className={`flex items-center gap-4 px-4 py-3 transition-colors cursor-pointer select-none ${
                          isSelected
                            ? "bg-[var(--color-brand-primary)]/20 text-[var(--color-text-primary)] font-semibold ring-1 ring-inset ring-[var(--color-brand-primary)]/40"
                            : isExecuted
                            ? "hover:bg-[var(--color-surface-2)] text-[var(--color-text-primary)]/90"
                            : "opacity-45 hover:opacity-85 text-[var(--color-text-muted)]"
                        } ${isDanger ? "bg-[var(--color-brand-danger)]/10 text-[var(--color-brand-danger)] hover:bg-[var(--color-brand-danger)]/15" : ""}`}
                      >
                        {/* Column 1: Time */}
                        <div className="w-24 shrink-0">
                          <span className="text-[var(--color-brand-primary)] font-bold tabular-nums">
                            +{evtTime.toFixed(3)}s
                          </span>
                        </div>

                        {/* Column 2: Lane */}
                        <div className="w-36 shrink-0">
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono border border-[var(--color-border)] bg-[var(--color-surface-2)] text-[var(--color-text-primary)]/80 truncate max-w-[136px]">
                            {ev.source_type ?? ev.lane ?? "system"}
                          </span>
                        </div>

                        {/* Column 3: Source */}
                        <div className="w-32 shrink-0 truncate">
                          <span className="text-xs text-[var(--color-text-muted)] truncate block" title={ev.source ?? "in-memory"}>
                            {ev.source ?? "in-memory"}
                          </span>
                        </div>

                        {/* Column 4: Status */}
                        <div className="w-28 shrink-0 flex items-center">
                          <Badge
                            tone={
                              isDanger
                                ? "danger"
                                : isExecuted
                                ? "success"
                                : "muted"
                            }
                          >
                            {isDanger ? "HALT" : isExecuted ? "EXECUTED" : "PENDING"}
                          </Badge>
                        </div>

                        {/* Column 5: Message */}
                        <div className="flex-1 min-w-0 pr-2">
                          <span className="break-words leading-relaxed text-[var(--color-text-primary)]/90 block">
                            {ev.message}
                          </span>
                        </div>
                      </li>
                    );
                  })
                )}
              </ul>
            </div>
          </div>
        </Card>

        {/* Actions Footer */}
        <div className="pt-4 border-t border-[var(--color-border)] flex flex-wrap justify-end gap-3">
          <Button variant="outline" onClick={handleExportTimeline} disabled={loading} className="h-9 px-4 text-xs font-semibold">
            {loading ? "Exporting..." : "Export Timeline (JSON)"}
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function RealityRewind() {
  return (
    <DataErrorBoundary>
      <RealityRewindContent />
    </DataErrorBoundary>
  );
}