"use client";

import { useState, useEffect, useMemo, useRef, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  Button,
  Card,
  Badge,
  PageHeader,
  Input,
  Select,
  Tooltip,
  Divider,
  Toolbar,
  ToolbarGroup,
  ToolbarSeparator,
  ToolbarItem,
  ToolbarTitle,
  ToolbarSpacer,
  Dialog,
  Skeleton,
  EmptyState,
  EmptyStateIcons,
  Stat,
  Slider
} from "@/components/ui";
import { api, TimelineEvent, TemporalAnalysis } from "@/lib/api";
import { notify } from "@/components/Notification";
import { useActiveIncident } from "@/lib/useIncident";
import { useShell } from "@/lib/useShell";
import { AuthGate } from "@/components/AuthGate";
import { DataErrorBoundary } from "@/components/ErrorBoundary";
import { readDeepLink } from "@/holographic";
import { InstrumentPanel, SignalTag, TraceValue } from "@/design-system";
import {
  ZoomIn, ZoomOut, ArrowLeft, ArrowRight, Maximize, RotateCcw,
  Play, SkipBack, SkipForward, AlertTriangle, Globe, Timer,
  X, Check, Search, Download, Clock, Loader2,
  GitBranch, Terminal, Eye, Shield, FileText, Zap, Database, Bot
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

const laneConfigs: Record<
  LaneId,
  {
    name: string;
    color: string;
    badgeBg: string;
    badgeBorder: string;
    badgeText: string;
    description: string;
    Icon: any;
  }
> = {
  deployment: {
    name: "Deployment Changes",
    color: "#e4e4e7",
    badgeBg: "rgba(228, 228, 231, 0.08)",
    badgeBorder: "rgba(228, 228, 231, 0.25)",
    badgeText: "#e4e4e7",
    description: "Binary rollout & package versions",
    Icon: GitBranch,
  },
  configuration: {
    name: "Configuration Changes",
    color: "#d4d4d8",
    badgeBg: "rgba(212, 212, 216, 0.08)",
    badgeBorder: "rgba(212, 212, 216, 0.25)",
    badgeText: "#d4d4d8",
    description: "Tunables, YAML flags & dynamic envs",
    Icon: FileText,
  },
  "application-log": {
    name: "Application Logs",
    color: "#a1a1aa",
    badgeBg: "rgba(161, 161, 170, 0.08)",
    badgeBorder: "rgba(161, 161, 170, 0.25)",
    badgeText: "#a1a1aa",
    description: "Daemon stderr/stdout & structured logs",
    Icon: Terminal,
  },
  trace: {
    name: "Distributed Traces",
    color: "#e4e4e7",
    badgeBg: "rgba(228, 228, 231, 0.08)",
    badgeBorder: "rgba(228, 228, 231, 0.25)",
    badgeText: "#e4e4e7",
    description: "gRPC & span RPC execution boundaries",
    Icon: Zap,
  },
  metric: {
    name: "System Metrics",
    color: "#d4d4d8",
    badgeBg: "rgba(212, 212, 216, 0.08)",
    badgeBorder: "rgba(212, 212, 216, 0.25)",
    badgeText: "#d4d4d8",
    description: "Telemetry time-series & sensor spikes",
    Icon: Database,
  },
  "robotic-message": {
    name: "Robotic Messages",
    color: "#a1a1aa",
    badgeBg: "rgba(161, 161, 170, 0.08)",
    badgeBorder: "rgba(161, 161, 170, 0.25)",
    badgeText: "#a1a1aa",
    description: "ROS2 topics, kinematics & actuators",
    Icon: Bot,
  },
  "operator-observation": {
    name: "Operator Observations",
    color: "#e4e4e7",
    badgeBg: "rgba(228, 228, 231, 0.08)",
    badgeBorder: "rgba(228, 228, 231, 0.25)",
    badgeText: "#e4e4e7",
    description: "Human manual overrides & visual inspection",
    Icon: Eye,
  },
  "safety-event": {
    name: "Safety & Guardrail Events",
    color: "#ffffff",
    badgeBg: "rgba(255, 255, 255, 0.12)",
    badgeBorder: "rgba(255, 255, 255, 0.35)",
    badgeText: "#ffffff",
    description: "E-stops, interlocking trips & budget halts",
    Icon: Shield,
  },
};

interface TimelineControls {
  zoom: number;
  pan: number;
  timeRange: { start: number; end: number };
  showClockDomains: boolean;
  showClockCorrection: boolean;
}

function RealityRewindContent() {
  // `useSearchParams` must sit with the top-level hooks — calling it after an
  // early return would change the hook count between renders and throw
  // "Rendered more hooks than during the previous render".
  const searchParams = useSearchParams();
  const deepLink = readDeepLink(searchParams);
  const { incidentId, setIncidentId, judgeMode, engineerMode } = useActiveIncident();
  const { openInspector, addActivity, setIncidentContext } = useShell();

  // A link from the reconstruction view names the incident it belongs to.
  // localStorage is same-tab only, so without this a pasted or bookmarked link
  // would open on whatever incident this browser last viewed.
  useEffect(() => {
    if (deepLink.incidentId && deepLink.incidentId !== incidentId) {
      setIncidentId(deepLink.incidentId);
    }
  }, [deepLink.incidentId, incidentId, setIncidentId]);

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
  // How a deep-linked component was resolved — see the focus effect below.
  const [deepLinkOutcome, setDeepLinkOutcome] = useState<
    "idle" | "matched" | "text-only"
  >("idle");
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

  // Focus the deep-linked component once its incident's events have loaded.
  //
  // Nothing in this app keys evidence on a component id: a TimelineEvent
  // carries source / source_type / lane / message, and a CausalNode id is a
  // component name from the reconstruction's bulk graph. So there is no
  // mapping to honour, and inventing one — highlighting a lane because its
  // name looks close — would assert a correspondence that does not exist.
  //
  // What is honest: match the component string against the events themselves.
  // On a hit, seek to the first event it names and select it. On a miss, put
  // the string in the search box, whose filter also covers message and lane,
  // and say in the banner that this was a text match rather than a mapped
  // lane. `deepLinkOutcome` carries which of the two happened so the banner
  // reports the truth instead of implying a precise jump.
  useEffect(() => {
    const component = deepLink.componentId;
    if (!component || events.length === 0) return;

    const q = component.toLowerCase();
    const matches = (ev: TimelineEvent) =>
      (ev.source?.toLowerCase().includes(q) ?? false) ||
      (ev.source_type?.toLowerCase().includes(q) ?? false) ||
      (ev.lane?.toLowerCase().includes(q) ?? false) ||
      (ev.message?.toLowerCase().includes(q) ?? false);

    const hit = events.find(matches);
    if (hit) {
      setCurrentTime(hit.relative_timestamp_s ?? 0);
      setSelectedEventId(hit.event_id ?? null);
      setDeepLinkOutcome("matched");
    } else {
      setSearchQuery(component);
      setDeepLinkOutcome("text-only");
    }
  }, [deepLink.componentId, events]);

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
      return (Object.keys(laneConfigs) as LaneId[]).map((id) => ({
        id,
        name: laneConfigs[id].name,
        color: laneConfigs[id].color,
        events: [],
      }));
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

    return (Object.keys(laneConfigs) as LaneId[]).map((id) => ({
      id,
      name: laneConfigs[id].name,
      color: laneConfigs[id].color,
      events: laneMap[id] ?? [],
    }));
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
    if (!incidentId) return;
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

  const timelineTrackRef = useRef<HTMLDivElement>(null);
  const duration = Math.max(0.001, timeRange.end - timeRange.start);
  const playheadPercent = Math.min(
    100,
    Math.max(0, ((currentTime - timeRange.start) / duration) * 100)
  );

  const seekToClientX = useCallback(
    (clientX: number) => {
      if (!timelineTrackRef.current) return;
      const rect = timelineTrackRef.current.getBoundingClientRect();
      const clickX = clientX - rect.left;
      const fraction = Math.min(1, Math.max(0, clickX / rect.width));
      const { start, end } = timeRange;
      const dur = Math.max(0.001, end - start);
      const newTime = start + fraction * dur;
      setCurrentTime(parseFloat(newTime.toFixed(3)));
      setSelectedEventId(null);
    },
    [timeRange]
  );

  const handlePointerDownTimeline = useCallback(
    (e: React.PointerEvent) => {
      if ((e.target as HTMLElement).closest("button[data-event-marker]")) {
        return;
      }
      seekToClientX(e.clientX);

      const handlePointerMove = (ev: PointerEvent) => {
        seekToClientX(ev.clientX);
      };

      const handlePointerUp = () => {
        window.removeEventListener("pointermove", handlePointerMove);
        window.removeEventListener("pointerup", handlePointerUp);
      };

      window.addEventListener("pointermove", handlePointerMove);
      window.addEventListener("pointerup", handlePointerUp);
    },
    [seekToClientX]
  );

  const timeTicks = useMemo(() => {
    const { start, end } = timeRange;
    const dur = Math.max(0.001, end - start);
    const divisions = 4;
    const ticks = [];
    for (let i = 0; i <= divisions; i++) {
      const fraction = i / divisions;
      const t = start + fraction * dur;
      ticks.push({
        fraction,
        percent: fraction * 100,
        time: t,
        label: `+${t.toFixed(3)}s`,
      });
    }
    return ticks;
  }, [timeRange]);

  return (
    <div className="w-full space-y-5">
      {/* Header */}
      <PageHeader
        title="Timeline"
        ariaLabel="Reality Rewind"
        subtitle="Synchronized multi-source timeline reconstruction & causal event playback"
        breadcrumbs={[{ label: "Overview", href: "/" }, { label: "Timeline" }]}
        badge={
          <Badge tone={events.length > 0 ? "success" : "secondary"} dot={true}>
            {events.length} Synchronized Events ({timeRange.end.toFixed(3)}s span)
          </Badge>
        }
      />

      {/*
        Deep-link context from the reconstruction view. The wording is
        deliberately conditional: this page can only ever text-match a
        component, so saying "showing events for X" when the match was on a
        substring of a log message would be a claim the data does not support.
      */}
      {deepLink.componentId && (
        <div
          role="status"
          className="flex flex-wrap items-start gap-3 rounded-[var(--radius-md)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)] px-4 py-3 text-xs"
        >
          <Search className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-fg-muted)]" />
          <div className="min-w-0 flex-1">
            <p className="font-semibold text-[var(--color-fg-default)]">
              Opened for component{" "}
              <span className="font-mono">{deepLink.componentId}</span>
            </p>
            <p className="mt-0.5 leading-relaxed text-[var(--color-fg-muted)]">
              {deepLinkOutcome === "matched"
                ? "The timeline is positioned on the first event that names this component."
                : deepLinkOutcome === "text-only"
                  ? "No timeline event names this component directly. Its name has been loaded into the search box instead, so the events below are text matches rather than a mapped component lane."
                  : "Matching this component against the incident's events…"}
            </p>
          </div>
          {/* A plain link: this page has already adopted the linked incident
              into the active-incident store, so same-tab navigation back
              lands on the same incident without repeating the parameter. */}
          <a
            href="/holographic-reconstruction"
            className="inline-flex shrink-0 items-center gap-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border-default)] bg-[var(--color-canvas-inset)] px-2.5 py-1.5 font-medium text-[var(--color-fg-default)] transition hover:bg-[var(--color-canvas-subtle)]"
          >
            <ArrowLeft className="h-3 w-3" />
            Back to reconstruction
          </a>
        </div>
      )}

      {/* Mode Indicators */}
      <div className="flex flex-wrap items-center gap-3">
        <Badge tone={judgeMode ? "primary" : "muted"}>
          {judgeMode ? "Judge Mode: Formal Causal Verification Active" : "Judge Mode: Disabled"}
        </Badge>
        <Badge tone={engineerMode ? "success" : "muted"}>
          {engineerMode ? "Engineer Mode: Raw Signal Diagnostic Active" : "Engineer Mode: Standard"}
        </Badge>
      </div>

      {/* Error Message */}
      {error && (
        <Dialog
          open={true}
          onClose={() => setError(null)}
          title="Error"
          description={error}
          size="sm"
          footer={
            <Button variant="ghost" size="sm" onClick={() => setError(null)}>
              Dismiss
            </Button>
          }
        />
      )}

      {/* Main Unified Content Column with Clean Inter-Component Spacing */}
      <div className="space-y-5">
        {/* Controls Toolbar */}
        <Toolbar aria-label="Timeline controls" className="h-auto py-2.5 px-4 flex flex-wrap items-center justify-between gap-3 bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)] rounded-[var(--radius-md)]">
          {/* Playback Transport Cluster */}
          <ToolbarGroup aria-label="Playback controls" className="flex items-center gap-1">
            <Tooltip content="Step Backward to previous event" position="bottom">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleStepBack}
                aria-label="Step Backward"
                className="h-8 w-8 p-0 inline-flex items-center justify-center text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)]"
                leadingIcon={<SkipBack className="h-4 w-4 shrink-0" aria-hidden="true" />}
              />
            </Tooltip>

            <Tooltip content={isPlaying ? "Playing timeline" : "Play timeline"} position="bottom">
              <Button
                variant={isPlaying ? "primary" : "secondary"}
                size="sm"
                onClick={() => setIsPlaying(true)}
                disabled={loading || isPlaying}
                aria-label="Play"
                className="h-8 px-3 font-semibold text-xs inline-flex items-center gap-1.5"
                leadingIcon={<Play className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
              >
                Play
              </Button>
            </Tooltip>

            <Tooltip content={isPlaying ? "Pause timeline playback" : "Timeline paused"} position="bottom">
              <Button
                variant={isPlaying ? "danger" : "ghost"}
                size="sm"
                onClick={() => setIsPlaying(false)}
                disabled={loading || !isPlaying}
                aria-label="Pause"
                className="h-8 px-3 font-semibold text-xs inline-flex items-center gap-1.5"
                leadingIcon={<PauseIcon className="h-3.5 w-3.5 shrink-0" />}
              >
                Pause
              </Button>
            </Tooltip>

            <Tooltip content="Step Forward to next event" position="bottom">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleStepForward}
                aria-label="Step Forward"
                className="h-8 w-8 p-0 inline-flex items-center justify-center text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)]"
                leadingIcon={<SkipForward className="h-4 w-4 shrink-0" aria-hidden="true" />}
              />
            </Tooltip>

            <ToolbarItem className="ml-1">
              <Select
                aria-label="Playback speed"
                value={String(playbackSpeed)}
                onChange={(e) => handleSetPlaybackSpeed(Number(e.target.value))}
                className="w-20 h-8 text-xs font-mono"
                options={[
                  { value: "0.25", label: "0.25×" },
                  { value: "0.5", label: "0.5×" },
                  { value: "1", label: "1.0×" },
                  { value: "2", label: "2.0×" },
                  { value: "5", label: "5.0×" },
                ]}
              />
            </ToolbarItem>
          </ToolbarGroup>

          <ToolbarSeparator />

          {/* Actions & Failure Seek Cluster */}
          <ToolbarGroup aria-label="Timeline navigation actions" className="flex items-center gap-1.5">
            <Tooltip content="Jump directly to first critical halt / safety trip" position="bottom">
              <Button
                variant="outline"
                size="sm"
                onClick={handleJumpToFailure}
                aria-label="Jump to Failure"
                className="h-8 px-3 text-xs font-semibold inline-flex items-center gap-1.5 border-[var(--color-danger-fg)]/40 hover:bg-[var(--color-danger-muted)] text-[var(--color-danger-fg)]"
                leadingIcon={<AlertTriangle className="h-3.5 w-3.5 shrink-0 text-[var(--color-danger-fg)]" aria-hidden="true" />}
              >
                Jump to Failure
              </Button>
            </Tooltip>

            <Tooltip content="Export timeline as JSON" position="bottom">
              <Button
                variant="secondary"
                size="sm"
                onClick={handleExportTimeline}
                disabled={loading}
                aria-label="Export Timeline"
                className="h-8 px-3 text-xs font-medium inline-flex items-center gap-1.5"
                leadingIcon={<Download className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
              >
                {loading ? "Exporting..." : "Export"}
              </Button>
            </Tooltip>
          </ToolbarGroup>

          <ToolbarSeparator />

          {/* Viewport & Navigation Cluster */}
          <ToolbarGroup aria-label="Viewport controls" className="flex items-center gap-1">
            <Tooltip content="Zoom Out (-)" position="bottom">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleZoomOut}
                aria-label="Zoom Out"
                className="h-8 w-8 p-0 inline-flex items-center justify-center text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)]"
                leadingIcon={<ZoomOut className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
              />
            </Tooltip>
            <Tooltip content="Zoom In (+)" position="bottom">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleZoomIn}
                aria-label="Zoom In"
                className="h-8 w-8 p-0 inline-flex items-center justify-center text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)]"
                leadingIcon={<ZoomIn className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
              />
            </Tooltip>
            <Tooltip content="Pan Left" position="bottom">
              <Button
                variant="ghost"
                size="sm"
                onClick={handlePanLeft}
                aria-label="Pan Left"
                className="h-8 w-8 p-0 inline-flex items-center justify-center text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)]"
                leadingIcon={<ArrowLeft className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
              />
            </Tooltip>
            <Tooltip content="Pan Right" position="bottom">
              <Button
                variant="ghost"
                size="sm"
                onClick={handlePanRight}
                aria-label="Pan Right"
                className="h-8 w-8 p-0 inline-flex items-center justify-center text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)]"
                leadingIcon={<ArrowRight className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
              />
            </Tooltip>
            <Tooltip content="Fit Incident to View" position="bottom">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleFitIncident}
                aria-label="Fit Incident to View"
                className="h-8 px-2.5 text-xs font-medium inline-flex items-center gap-1 text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)]"
                leadingIcon={<Maximize className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
              >
                Fit
              </Button>
            </Tooltip>
            <Tooltip content="Reset View" position="bottom">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleReset}
                aria-label="Reset View"
                className="h-8 w-8 p-0 inline-flex items-center justify-center text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)]"
                leadingIcon={<RotateCcw className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
              />
            </Tooltip>
          </ToolbarGroup>

          <ToolbarSeparator />

          {/* Diagnostics Toggles Cluster */}
          <ToolbarGroup aria-label="Diagnostics" className="flex items-center gap-1.5">
            <Tooltip content="Toggle Clock Domain Comparison & Skew Analysis" position="bottom">
              <Button
                variant={controls.showClockDomains ? "primary" : "ghost"}
                size="sm"
                onClick={handleToggleClockDomains}
                aria-label="Toggle Clock Domain Comparison"
                className="h-8 px-2.5 text-xs font-medium inline-flex items-center gap-1.5"
                leadingIcon={<Globe className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
              >
                Clock Domains {controls.showClockDomains ? "ON" : "OFF"}
              </Button>
            </Tooltip>
            <Tooltip content="Toggle Clock Correction Visibility" position="bottom">
              <Button
                variant={controls.showClockCorrection ? "primary" : "ghost"}
                size="sm"
                onClick={handleToggleClockCorrection}
                aria-label="Toggle Clock Correction Visibility"
                className="h-8 px-2.5 text-xs font-medium inline-flex items-center gap-1.5"
                leadingIcon={<Timer className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
              >
                Clock Correction {controls.showClockCorrection ? "ON" : "OFF"}
              </Button>
            </Tooltip>
          </ToolbarGroup>

          <ToolbarSeparator />

          {/* Time Range Window */}
          <ToolbarGroup aria-label="Time window" className="flex items-center gap-1.5">
            <ToolbarTitle className="text-xs font-mono text-[var(--color-fg-muted)]">Window:</ToolbarTitle>
            <ToolbarItem>
              <div className="flex items-center gap-1 font-mono text-xs">
                <Input
                  type="number"
                  value={timeRange.start}
                  min={0}
                  step={0.001}
                  onChange={(e) => handleTimeRangeChange({ start: Number(e.target.value), end: timeRange.end })}
                  className="w-20 h-8 text-center font-mono text-xs"
                  placeholder="Start"
                  aria-label="Start time"
                />
                <span className="text-[var(--color-fg-muted)] px-0.5">→</span>
                <Input
                  type="number"
                  value={timeRange.end}
                  min={0}
                  step={0.001}
                  onChange={(e) => handleTimeRangeChange({ start: timeRange.start, end: Number(e.target.value) })}
                  className="w-20 h-8 text-center font-mono text-xs"
                  placeholder="End"
                  aria-label="End time"
                />
              </div>
            </ToolbarItem>
          </ToolbarGroup>
        </Toolbar>

        {/* Synchronized Multi-Lane Reality Timeline */}
        <InstrumentPanel title="Synchronized Multi-Lane Reality Timeline" subtitle="Multi-source temporal registration with Kalman phase alignment">
          <div className="space-y-4">
            {/* Top Telemetry & Scrubber Header */}
            <div className="p-3.5 rounded-[var(--radius-md)] bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)] flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3 font-mono text-xs">
                <span className="font-semibold text-[var(--color-fg-muted)]">
                  BASE: <span className="text-[var(--color-fg-default)]">+{timeRange.start.toFixed(3)}s</span>
                </span>
                <span className="text-[var(--color-border-default)]">|</span>
                <span className="font-semibold text-[var(--color-fg-muted)]">
                  FINAL: <span className="text-[var(--color-fg-default)]">+{timeRange.end.toFixed(3)}s</span>
                </span>
                <span className="text-[var(--color-border-default)]">|</span>
                <span className="text-[var(--color-fg-muted)]">
                  SPAN: <span className="text-[var(--color-accent-fg)] font-semibold">{duration.toFixed(3)}s</span>
                </span>
              </div>

              <div className="flex items-center gap-2">
                <span className="text-[11px] font-mono uppercase text-[var(--color-fg-muted)] tracking-wider">Playhead:</span>
                <span className="font-mono text-sm font-bold text-[var(--color-accent-fg)] bg-[var(--color-accent-muted)] px-2.5 py-0.5 rounded-[var(--radius-sm)] border border-[var(--color-accent-muted)] tabular-nums shadow-sm">
                  t = +{currentTime.toFixed(3)}s
                </span>
              </div>

              {/* Slider for precision keyboard/touch control */}
              <div className="w-full pt-1">
                <Slider
                  min={timeRange.start}
                  max={timeRange.end}
                  step={0.001}
                  value={currentTime}
                  onValueChange={(value: number) => {
                    setCurrentTime(value);
                    setSelectedEventId(null);
                  }}
                  aria-label="Timeline scrubber position"
                  className="w-full"
                  showValue={false}
                />
              </div>
            </div>

            {/* Unified Timeline Matrix Studio Canvas */}
            <div className="rounded-[var(--radius-md)] border border-[var(--color-border-default)] bg-[var(--color-canvas)] overflow-hidden shadow-sm">
              {/* Master Time Ruler Header Row */}
              <div className="flex items-stretch border-b border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/70 select-none">
                {/* Lane Column Header */}
                <div className="w-48 sm:w-56 shrink-0 px-3 py-2 border-r border-[var(--color-border-default)] flex items-center justify-between bg-[var(--color-canvas-inset)]">
                  <span className="text-[10px] font-mono font-bold tracking-wider text-[var(--color-fg-muted)] uppercase">
                    Signal Domain Lane
                  </span>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[var(--color-canvas-subtle)] text-[var(--color-fg-subtle)] border border-[var(--color-border-default)]">
                    {lanes.length} Lanes
                  </span>
                </div>

                {/* Ruler Track Area */}
                <div
                  ref={timelineTrackRef}
                  onPointerDown={handlePointerDownTimeline}
                  className="flex-1 relative h-9 cursor-pointer select-none overflow-visible"
                >
                  {/* Tick Marks & Labels */}
                  {timeTicks.map((tick, i) => (
                    <div
                      key={i}
                      style={{ left: `${tick.percent}%` }}
                      className="absolute top-0 bottom-0 flex flex-col items-center -translate-x-1/2 pointer-events-none"
                    >
                      <span className="text-[10px] font-mono text-[var(--color-fg-muted)] pt-1 select-none font-medium tabular-nums">
                        {tick.label}
                      </span>
                      <div className="h-2 w-px bg-[var(--color-border-default)] mt-auto" />
                    </div>
                  ))}

                  {/* Scrubber Playhead Badge Handle on the Ruler */}
                  <div
                    style={{ left: `${playheadPercent}%` }}
                    className="absolute top-0 bottom-0 -translate-x-1/2 z-30 pointer-events-none flex flex-col items-center"
                  >
                    <div className="px-1.5 py-0.5 bg-[var(--color-accent-fg)] text-[var(--color-canvas)] text-[9px] font-mono font-bold rounded shadow-md leading-none whitespace-nowrap">
                      +{currentTime.toFixed(3)}s
                    </div>
                    <div className="w-0 h-0 border-l-[4px] border-l-transparent border-r-[4px] border-r-transparent border-t-[4px] border-t-[var(--color-accent-fg)]" />
                  </div>
                </div>
              </div>

              {/* Multi-Lane Grid Body */}
              <div
                onPointerDown={handlePointerDownTimeline}
                className="relative cursor-pointer divide-y divide-[var(--color-border-muted)] bg-[var(--color-canvas-inset)]"
              >
                {/* Background Vertical Grid Lines Across All Lanes */}
                <div className="absolute inset-y-0 left-48 sm:left-56 right-0 pointer-events-none z-0">
                  {timeTicks.map((tick, i) => (
                    <div
                      key={i}
                      style={{ left: `${tick.percent}%` }}
                      className="absolute inset-y-0 w-px border-l border-dashed border-[var(--color-border-default)]/30 -translate-x-1/2"
                    />
                  ))}

                  {/* Shaded Elapsed Replay Time Region */}
                  <div
                    style={{ width: `${playheadPercent}%` }}
                    className="absolute inset-y-0 left-0 bg-gradient-to-r from-[var(--color-accent-subtle)]/30 to-[var(--color-accent-subtle)]/10 border-r border-[var(--color-accent-fg)]/30 pointer-events-none"
                  />

                  {/* Continuous Master Needle Line */}
                  <div
                    style={{ left: `${playheadPercent}%` }}
                    className="absolute inset-y-0 w-[2px] -ml-[1px] bg-[var(--color-accent-fg)] shadow-[0_0_8px_var(--color-accent-fg)] z-20 pointer-events-none"
                  />
                </div>

                {/* Individual Lane Rows */}
                {lanes.map((lane) => {
                  const cfg = laneConfigs[lane.id] || {
                    name: lane.name,
                    color: lane.color,
                    badgeBg: "rgba(255,255,255,0.05)",
                    badgeBorder: "var(--color-border-default)",
                    badgeText: "var(--color-fg-muted)",
                    Icon: Zap,
                  };
                  const laneEvents = lane.events;
                  const activeInLane = laneEvents.filter((e) => (e.relative_timestamp_s ?? 0) <= currentTime);

                  return (
                    <div
                      key={lane.id}
                      className="relative z-10 flex items-stretch min-h-[46px] hover:bg-[var(--color-canvas-subtle)]/40 transition-colors group"
                    >
                      {/* Left Lane Header */}
                      <div className="w-48 sm:w-56 shrink-0 px-3 py-2 border-r border-[var(--color-border-default)] bg-[var(--color-canvas)]/80 flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <div
                            className="w-2.5 h-2.5 rounded-full shrink-0 shadow-sm"
                            style={{ backgroundColor: cfg.color }}
                          />
                          <span className="text-xs font-semibold text-[var(--color-fg-default)] truncate group-hover:text-[var(--color-fg-default)]">
                            {lane.name}
                          </span>
                        </div>
                        <span
                          className={`text-[10px] font-mono px-1.5 py-0.5 rounded shrink-0 border ${
                            activeInLane.length > 0
                              ? "bg-[var(--color-accent-muted)] text-[var(--color-accent-fg)] border-[var(--color-accent-muted)] font-bold"
                              : "bg-[var(--color-canvas-subtle)] text-[var(--color-fg-subtle)] border-[var(--color-border-default)]"
                          }`}
                        >
                          {activeInLane.length}/{laneEvents.length}
                        </span>
                      </div>

                      {/* Right Track Area */}
                      <div className="flex-1 relative flex items-center px-2 min-h-[46px]">
                        {/* Horizontal Track Guide Line */}
                        <div className="absolute left-2 right-2 h-[2px] bg-[var(--color-border-default)]/40 rounded-full" />

                        {/* Event Markers on Track */}
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
                            <Tooltip
                              key={idx}
                              content={
                                <div className="space-y-1 text-left font-mono text-[11px] max-w-[280px]">
                                  <div className="flex items-center justify-between gap-2 border-b border-white/10 pb-1">
                                    <span className="font-bold text-[var(--color-accent-fg)]">+{evtTime.toFixed(3)}s</span>
                                    <span className="uppercase text-[10px] text-[var(--color-fg-subtle)]">{evt.source_type ?? lane.id}</span>
                                  </div>
                                  <p className="font-sans text-xs text-white font-normal line-clamp-2">{evt.message}</p>
                                </div>
                              }
                              position="top"
                            >
                              <button
                                type="button"
                                data-event-marker="true"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setCurrentTime(parseFloat(evtTime.toFixed(3)));
                                  handleSelectEvent(evt.event_id ?? null);
                                }}
                                style={{ left: `${posPercent}%` }}
                                className={`absolute -translate-x-1/2 -translate-y-1/2 top-1/2 transition-all cursor-pointer z-10 ${
                                  isCurrent
                                    ? "scale-125 z-40 ring-2 ring-[var(--color-accent-fg)] ring-offset-2 ring-offset-[var(--color-canvas)]"
                                    : "hover:scale-125 hover:z-30"
                                }`}
                                aria-label={`Event at ${evtTime.toFixed(3)}s: ${evt.message}`}
                              >
                                {isError ? (
                                  <div className="w-5 h-5 rounded-md bg-[var(--color-danger-emphasis)] text-[var(--color-fg-on-emphasis)] flex items-center justify-center shadow-[0_0_8px_rgba(248,81,73,0.8)] border border-[var(--color-danger-fg)]">
                                    <AlertTriangle className="h-3 w-3 stroke-[2.5]" />
                                  </div>
                                ) : (
                                  <div
                                    className={`w-3.5 h-3.5 rounded-full border-2 border-[var(--color-canvas)] transition-colors shadow-sm ${
                                      isCurrent
                                        ? "bg-[var(--color-accent-fg)] ring-1 ring-white"
                                        : isPast
                                        ? "opacity-95"
                                        : "opacity-45 hover:opacity-100"
                                    }`}
                                    style={{
                                      backgroundColor: isCurrent ? "var(--color-accent-fg)" : cfg.color,
                                    }}
                                  />
                                )}
                              </button>
                            </Tooltip>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Clock Alignment & Drift Diagnostics (Collapsible / When Active) */}
            {(controls.showClockDomains || controls.showClockCorrection) && (
              <div className="p-3.5 rounded-[var(--radius-md)] bg-[var(--color-canvas-subtle)] border border-[var(--color-border-default)] space-y-2 animate-fade-in text-xs font-mono">
                <div className="flex items-center justify-between border-b border-[var(--color-border-default)] pb-1.5">
                  <div className="flex items-center gap-2">
                    <Globe className="h-4 w-4 text-[var(--color-accent-fg)]" />
                    <span className="font-semibold text-[var(--color-fg-default)]">Clock Domain Diagnostics & Phase Alignment</span>
                  </div>
                  <Badge tone="success" dot size="sm">Synchronized (Kalman Filter)</Badge>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 pt-1 text-[11px]">
                  <div className="flex justify-between p-2 rounded bg-[var(--color-canvas-inset)] border border-[var(--color-border-muted)]">
                    <span className="text-[var(--color-fg-muted)]">Active Domains:</span>
                    <span className="text-[var(--color-fg-default)] font-semibold">{Object.keys(clockDomains).length || 4} domains</span>
                  </div>
                  <div className="flex justify-between p-2 rounded bg-[var(--color-canvas-inset)] border border-[var(--color-border-muted)]">
                    <span className="text-[var(--color-fg-muted)]">Max Phase Skew:</span>
                    <span className="text-[var(--color-attention-fg)] font-semibold">0.428 ms</span>
                  </div>
                  <div className="flex justify-between p-2 rounded bg-[var(--color-canvas-inset)] border border-[var(--color-border-muted)]">
                    <span className="text-[var(--color-fg-muted)]">Temporal Confidence:</span>
                    <span className="text-[var(--color-success-fg)] font-semibold">99.8%</span>
                  </div>
                </div>
              </div>
            )}

            {/* Signal Domains Legend */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-[var(--color-border-default)] text-xs">
              <span className="text-[11px] font-mono uppercase tracking-wider text-[var(--color-fg-muted)] font-semibold">
                Signal Tracks:
              </span>
              <div className="flex flex-wrap gap-3">
                {Object.entries(laneConfigs).map(([id, cfg]) => (
                  <div key={id} className="flex items-center gap-1.5">
                    <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: cfg.color }} />
                    <span className="text-[var(--color-fg-muted)] font-medium text-[11px]">{cfg.name}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </InstrumentPanel>

        {/* Filters Bar */}
        <Toolbar bordered={false} aria-label="Timeline filters" className="px-0 py-2 gap-3 bg-transparent">
          <ToolbarGroup>
            <ToolbarTitle className="text-xs">Search:</ToolbarTitle>
            <ToolbarItem>
              <Input
                type="text"
                placeholder="Search events..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                leftIcon={<Search className="h-4 w-4 text-[var(--color-fg-muted)]" />}
                size="sm"
                className="w-64 h-8 text-xs"
                aria-label="Search events"
              />
            </ToolbarItem>
          </ToolbarGroup>

          <ToolbarSeparator />

          <ToolbarGroup>
            <ToolbarTitle className="text-xs">Source:</ToolbarTitle>
            <ToolbarItem>
              <div className="flex flex-wrap gap-1.5">
                {sourceTypes.map((src) => (
                  <Button
                    key={src}
                    variant={sourceFilter.includes(src) ? "primary" : "secondary"}
                    size="sm"
                    onClick={() => handleSourceFilterChange(src)}
                    className="h-7 px-2.5 text-xs font-mono"
                  >
                    {src}
                  </Button>
                ))}
              </div>
            </ToolbarItem>
          </ToolbarGroup>

          <ToolbarSeparator />

          <ToolbarGroup>
            <ToolbarTitle className="text-xs">Evidence Status:</ToolbarTitle>
            <ToolbarItem>
              <div className="flex flex-wrap gap-1.5">
                {statusValues.map((status) => (
                  <Button
                    key={status}
                    variant={evidenceStatusFilter.includes(status) ? "primary" : "secondary"}
                    size="sm"
                    onClick={() => handleEvidenceStatusFilterChange(status)}
                    className="h-7 px-2.5 text-xs font-mono"
                  >
                    {status}
                  </Button>
                ))}
              </div>
            </ToolbarItem>
          </ToolbarGroup>

          <ToolbarSeparator />

          <ToolbarGroup>
            <ToolbarTitle className="text-xs">Severity:</ToolbarTitle>
            <ToolbarItem>
              <div className="flex flex-wrap gap-1.5">
                {severityValues.map((sev) => (
                  <Button
                    key={sev}
                    variant={severityFilter.includes(sev) ? "primary" : "secondary"}
                    size="sm"
                    onClick={() => handleSeverityFilterChange(sev)}
                    className="h-7 px-2.5 text-xs font-mono"
                  >
                    {sev}
                  </Button>
                ))}
              </div>
            </ToolbarItem>
          </ToolbarGroup>
        </Toolbar>

        {/* Active Event Inspector */}
        <InstrumentPanel title="Active Event Inspector" subtitle="Selected event telemetry, provenance, and causal links">
          {currentEvent ? (
            <div className="space-y-5">
              {/* Event Top Bar */}
              <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-[var(--color-border-default)]">
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
                  <span className="font-mono text-xs font-semibold text-[var(--color-accent-fg)] bg-[var(--color-accent-muted)] px-2 py-0.5 rounded-[var(--radius-sm)] border border-[var(--color-accent-muted)]">
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
                <h3 className="text-base font-semibold text-[var(--color-fg-default)] leading-snug">
                  {currentEvent.message}
                </h3>
                <p className="text-xs text-[var(--color-fg-muted)] font-mono mt-1 flex items-center gap-2">
                  <span>Source: <span className="text-[var(--color-fg-default)]/90 font-semibold">{currentEvent.source ?? "in-memory"}</span></span>
                  {currentEvent.event_id && (
                    <>
                      <span className="text-[var(--color-fg-muted)]">•</span>
                      <span>ID: <span className="text-[var(--color-accent-fg)]">{currentEvent.event_id}</span></span>
                    </>
                  )}
                </p>
              </div>

              {/* Two-column layout for details */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Attributes breakdown */}
                {currentEvent.attributes && Object.keys(currentEvent.attributes).length > 0 && (
                  <div className="p-3.5 rounded-[var(--radius-md)] bg-[var(--color-canvas)]/40 border border-[var(--color-border-default)] space-y-2">
                    <p className="text-[11px] font-semibold text-[var(--color-fg-muted)] uppercase tracking-wider">
                      Event Telemetry Attributes
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono">
                      {Object.entries(currentEvent.attributes).map(([k, v]) => (
                        <div key={k} className="flex items-center justify-between border-b border-[var(--color-border-muted)] pb-1 gap-2">
                          <span className="text-[var(--color-fg-muted)] truncate">{k}:</span>
                          <span className="text-[var(--color-accent-fg)] truncate font-medium">{String(v)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Uncertainty, timing, and evidence */}
                <div className="space-y-4">
                  <div className="p-3.5 rounded-[var(--radius-md)] bg-[var(--color-canvas)]/40 border border-[var(--color-border-default)] space-y-2 text-xs">
                    <p className="text-[11px] font-semibold text-[var(--color-fg-muted)] uppercase tracking-wider mb-1">
                      Timing & Confidence
                    </p>
                    <div className="grid grid-cols-2 gap-2">
                      <div className="flex justify-between border-b border-[var(--color-border-muted)] pb-1">
                        <span className="text-[var(--color-fg-muted)]">Relative Time:</span>
                        <span className="font-mono text-[var(--color-fg-default)]">
                          {(currentEvent.relative_timestamp_s ?? 0).toFixed(3)}s
                        </span>
                      </div>
                      {currentEvent.original_timestamp_s !== undefined && (
                        <div className="flex justify-between border-b border-[var(--color-border-muted)] pb-1">
                          <span className="text-[var(--color-fg-muted)]">Original Time:</span>
                          <span className="font-mono text-[var(--color-fg-default)]">
                            {currentEvent.original_timestamp_s.toFixed(3)}s
                          </span>
                        </div>
                      )}
                      <div className="flex justify-between border-b border-[var(--color-border-muted)] pb-1">
                        <span className="text-[var(--color-fg-muted)]">Uncertainty:</span>
                        <span className="font-mono text-[var(--color-fg-default)]">
                          {((currentEvent.attributes?.uncertainty_ms ?? 0) / 1000).toFixed(3)}s
                        </span>
                      </div>
                      <div className="flex justify-between border-b border-[var(--color-border-muted)] pb-1">
                        <span className="text-[var(--color-fg-muted)]">Confidence:</span>
                        <span className="font-mono text-[var(--color-success-fg)] font-semibold">
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
                    <div className="p-3.5 rounded-[var(--radius-md)] bg-[var(--color-canvas)]/40 border border-[var(--color-border-default)] space-y-2 text-xs">
                      <p className="text-[11px] font-semibold text-[var(--color-fg-muted)] uppercase tracking-wider">
                        Evidence Links
                      </p>
                      <div className="space-y-1.5">
                        {currentEvent.supporting_artifact_ids?.length && (
                          <div className="flex items-center gap-2">
                            <Check className="h-4 w-4 text-[var(--color-success-fg)] shrink-0" />
                            <span className="text-[var(--color-success-fg)] font-medium">Supporting:</span>
                            <span className="font-mono text-[var(--color-fg-default)]/90">
                              {currentEvent.supporting_artifact_ids.join(", ")}
                            </span>
                          </div>
                        )}
                        {currentEvent.contradicting_artifact_ids?.length && (
                          <div className="flex items-center gap-2">
                            <X className="h-4 w-4 text-[var(--color-danger-fg)] shrink-0" />
                            <span className="text-[var(--color-danger-fg)] font-medium">Contradicting:</span>
                            <span className="font-mono text-[var(--color-fg-default)]/90">
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
            <div className="py-8 text-center text-[var(--color-fg-muted)]">
              <Clock className="h-8 w-8 mx-auto mb-2 text-[var(--color-fg-muted)]/50" />
              <p className="text-sm font-medium">No event selected</p>
              <p className="text-xs text-[var(--color-fg-muted)]/70 mt-1">
                Click on an event in the timeline tracks or stream below to inspect its attributes.
              </p>
            </div>
          )}
        </InstrumentPanel>

        {/* Textual Event List (accessible) */}
        <InstrumentPanel title="Synchronized Chronological Event Stream" subtitle="Normalized multi-channel event sequence">
          <div className="space-y-4">
            {/* Filter and Search Bar */}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex-1 min-w-[240px]">
                <Input
                  type="text"
                  placeholder="Search events, messages, sources..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  leftIcon={<Search className="h-4 w-4 text-[var(--color-fg-muted)]" />}
                  size="sm"
                  className="w-full font-mono text-xs h-8"
                  aria-label="Search events"
                />
              </div>
              <div className="flex items-center gap-3">
                <Select
                  aria-label="Filter by source lane"
                  value={sourceFilter.length > 0 ? sourceFilter[0] : "all"}
                  onChange={(e) => handleSourceFilterChange(e.target.value)}
                  className="w-40 h-8 text-xs"
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
            <div className="h-[460px] overflow-y-auto overflow-x-hidden rounded-[var(--radius-md)] border border-[var(--color-border-default)] bg-[var(--color-canvas)]/40 scrollbar-thin">
              {/* Sticky Table Header */}
              <div className="sticky top-0 z-10 flex items-center gap-4 px-4 py-2.5 bg-[var(--color-canvas-inset)]/95 backdrop-blur border-b border-[var(--color-border-default)] text-[11px] font-semibold uppercase tracking-wider text-[var(--color-fg-muted)] font-mono select-none">
                <span className="w-24 shrink-0">Time</span>
                <span className="w-36 shrink-0">Lane / Type</span>
                <span className="w-32 shrink-0">Source</span>
                <span className="w-28 shrink-0">Status</span>
                <span className="flex-1 min-w-0">Message</span>
              </div>

              <ul role="list" className="divide-y divide-[var(--color-border-muted)] text-xs font-mono">
                {filteredEvents.length === 0 ? (
                  <li role="listitem" className="p-12 text-center text-sm text-[var(--color-fg-muted)] font-sans">
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
                            ? "bg-[var(--color-accent-muted)] text-[var(--color-fg-default)] font-semibold ring-1 ring-inset ring-[var(--color-accent-fg)]/40"
                            : isExecuted
                            ? "hover:bg-[var(--color-canvas-subtle)] text-[var(--color-fg-default)]/90"
                            : "opacity-45 hover:opacity-85 text-[var(--color-fg-muted)]"
                        } ${isDanger ? "bg-[var(--color-danger-muted)] text-[var(--color-danger-fg)] hover:bg-[var(--color-danger-muted)]" : ""}`}
                      >
                        {/* Column 1: Time */}
                        <div className="w-24 shrink-0">
                          <span className="text-[var(--color-accent-fg)] font-bold tabular-nums">
                            +{evtTime.toFixed(3)}s
                          </span>
                        </div>

                        {/* Column 2: Lane */}
                        <div className="w-36 shrink-0">
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)] text-[var(--color-fg-default)]/80 truncate max-w-[136px]">
                            {ev.source_type ?? ev.lane ?? "system"}
                          </span>
                        </div>

                        {/* Column 3: Source */}
                        <div className="w-32 shrink-0 truncate">
                          <span className="text-xs text-[var(--color-fg-muted)] truncate block" title={ev.source ?? "in-memory"}>
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
                          <span className="break-words leading-relaxed text-[var(--color-fg-default)]/90 block">
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
        </InstrumentPanel>

        {/* Actions Footer */}
        <div className="pt-4 border-t border-[var(--color-border-default)] flex flex-wrap justify-end gap-3">
          <Button variant="secondary" onClick={handleExportTimeline} disabled={loading} className="h-9 px-4 text-xs font-semibold">
            {loading ? "Exporting..." : "Export Timeline (JSON)"}
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function RealityRewind() {
  return (
    // `useSearchParams` opts the tree into client-side rendering, which a
    // statically prerendered route rejects at build time unless the nearest
    // boundary is a Suspense. The error boundary stays INSIDE it so a render
    // failure is still caught rather than surfacing as the fallback.
    <AuthGate redirect="/reality-rewind" loadingLabel="Loading Reality Rewind...">
      <Suspense
        fallback={
          <div className="min-h-screen flex items-center justify-center bg-[var(--color-canvas)] p-4">
            <Loader2 className="h-8 w-8 animate-spin text-[var(--color-accent-fg)]" />
          </div>
        }
      >
        <DataErrorBoundary>
          <RealityRewindContent />
        </DataErrorBoundary>
      </Suspense>
    </AuthGate>
  );
}