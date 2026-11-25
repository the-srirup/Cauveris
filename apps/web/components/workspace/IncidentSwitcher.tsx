"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, ChevronDown, FolderOpen, Loader2, Plus, Search } from "lucide-react";
import { api, type Incident } from "@/lib/api";
import { useActiveIncident } from "@/lib/useIncident";
import { useShell } from "@/lib/useShell";
import { notify } from "@/components/Notification";

/**
 * Interactive in-session incident switcher embedded in the top navbar.
 *
 * Allows operators to jump between incidents immediately within the same
 * workbench session (without leaving the dashboard), or jump out to create a
 * new incident / open the Workspace Hub.
 */
export function IncidentSwitcher({
  activeId,
  activeTitle,
  onOpenWorkspaceHub,
}: {
  activeId: string | null | undefined;
  activeTitle: string;
  onOpenWorkspaceHub: () => void;
}) {
  const router = useRouter();
  const { setIncidentId } = useActiveIncident();
  const { setWorkspacePrompt } = useShell();

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const loadIncidents = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await api.list();
      const list = Array.isArray(res) ? res : res?.incidents ?? [];
      setIncidents(list);
    } catch {
      // Keep any previously loaded list if refresh fails silently
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    void loadIncidents();
    const timer = setTimeout(() => searchInputRef.current?.focus(), 20);
    return () => clearTimeout(timer);
  }, [open, loadIncidents]);

  useEffect(() => {
    if (!open) return;
    const onMouseDown = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return incidents;
    return incidents.filter(
      (inc) =>
        inc.id.toLowerCase().includes(q) ||
        (inc.title || "").toLowerCase().includes(q) ||
        (inc.system_name || "").toLowerCase().includes(q)
    );
  }, [incidents, query]);

  const handleSelectIncident = (target: Incident) => {
    setOpen(false);
    setQuery("");
    if (target.id === activeId) return;
    setIncidentId(target.id);
    notify(`Switched active incident to ${target.id}`, "info");
  };

  const handleNewIncident = () => {
    setOpen(false);
    if (activeId && typeof setWorkspacePrompt === "function") {
      // Let user choose to save before leaving to create a new session/incident
      setWorkspacePrompt(true);
    } else {
      router.push("/workspace/new");
    }
  };

  return (
    <div ref={containerRef} className="relative min-w-0">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        title={`Switch active incident (${activeTitle})`}
        aria-label="Switch active incident"
        aria-expanded={open}
        aria-haspopup="listbox"
        className={`flex items-center gap-2 px-2.5 h-8.5 rounded-[var(--radius-sm,4px)] transition-colors min-w-0 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] ${
          open
            ? "bg-[var(--surface-tile,var(--color-canvas-muted))]"
            : "bg-[var(--color-canvas-default)] hover:bg-[var(--surface-tile,var(--color-canvas-muted))]"
        }`}
      >
        <span className="text-xs font-mono font-medium text-[var(--color-fg-muted)] shrink-0">
          {activeId ? activeId : "STANDBY"}
        </span>
        <span className="text-xs font-semibold text-[var(--color-fg-default)] truncate max-w-[140px] sm:max-w-[210px]">
          {activeTitle}
        </span>
        <ChevronDown
          className={`h-3.5 w-3.5 text-[var(--color-fg-muted)] shrink-0 transition-transform duration-150 ${
            open ? "rotate-180" : ""
          }`}
          aria-hidden="true"
        />
      </button>

      {open && (
        <div
          className="absolute left-0 top-full mt-1.5 w-80 sm:w-96 rounded-[var(--radius-lg,8px)] bg-[var(--surface-rail,var(--color-canvas-default))] shadow-[var(--shadow-xl),inset_0_1px_0_rgba(255,255,255,0.06)] z-[var(--z-dropdown,30)] overflow-hidden"
          role="dialog"
          aria-label="In-session incident switcher"
        >
          {/* Filter Input */}
          <div className="p-2.5 bg-[var(--surface-card,var(--color-canvas-inset))]">
            <div className="relative flex items-center">
              <Search
                className="absolute left-2.5 h-3.5 w-3.5 text-[var(--color-fg-subtle)] pointer-events-none"
                aria-hidden="true"
              />
              <input
                ref={searchInputRef}
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Filter incidents in this session..."
                aria-label="Filter incidents"
                className="w-full h-8 pl-8 pr-3 rounded-[var(--radius-sm,4px)] bg-[var(--surface-well,var(--color-canvas))] text-xs text-[var(--color-fg-default)] placeholder:text-[var(--color-fg-subtle)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
              />
            </div>
          </div>

          {/* Incident List */}
          <div className="max-h-72 overflow-y-auto p-1.5 space-y-0.5" role="listbox" aria-label="Incidents">
            {isLoading && incidents.length === 0 ? (
              <div className="flex items-center justify-center gap-2 py-6 text-xs text-[var(--color-fg-muted)]">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>Loading incidents...</span>
              </div>
            ) : filtered.length === 0 ? (
              <div className="py-6 text-center text-xs text-[var(--color-fg-muted)]">
                {query ? "No matching incidents found." : "No incidents in this session."}
              </div>
            ) : (
              filtered.map((inc) => {
                const isSelected = inc.id === activeId;
                return (
                  <button
                    key={inc.id}
                    type="button"
                    role="option"
                    aria-selected={isSelected}
                    onClick={() => handleSelectIncident(inc)}
                    className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-[var(--radius-sm,4px)] text-left transition-colors ${
                      isSelected
                        ? "bg-[var(--color-accent-subtle)] text-[var(--color-fg-default)]"
                        : "hover:bg-[var(--surface-tile,var(--color-canvas-muted))] text-[var(--color-fg-default)]"
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-[11px] font-medium text-[var(--color-fg-muted)] shrink-0">
                          {inc.id}
                        </span>
                        {inc.is_demonstration && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase bg-[var(--color-attention-muted)] text-[var(--color-attention-fg)]">
                            Demo
                          </span>
                        )}
                        {inc.status && (
                          <span className="text-[10px] font-mono uppercase text-[var(--color-fg-subtle)] truncate">
                            {inc.status}
                          </span>
                        )}
                      </div>
                      <p className="mt-0.5 text-xs font-medium truncate text-[var(--color-fg-default)]">
                        {inc.title || `Incident ${inc.id}`}
                      </p>
                    </div>
                    {isSelected && (
                      <Check
                        className="h-4 w-4 text-[var(--color-accent-fg)] shrink-0"
                        aria-hidden="true"
                      />
                    )}
                  </button>
                );
              })
            )}
          </div>

          {/* Footer Actions: Create New / Open Workspace Hub */}
          <div className="p-1.5 bg-[var(--surface-card,var(--color-canvas-inset))] flex items-center justify-between gap-1.5">
            <button
              type="button"
              onClick={handleNewIncident}
              className="flex-1 flex items-center justify-center gap-1.5 h-8 px-2.5 rounded-[var(--radius-sm,4px)] text-xs font-medium text-[var(--color-accent-fg)] hover:bg-[var(--color-accent-subtle)] transition-colors"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>New Incident…</span>
            </button>
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                onOpenWorkspaceHub();
              }}
              className="flex-1 flex items-center justify-center gap-1.5 h-8 px-2.5 rounded-[var(--radius-sm,4px)] text-xs font-medium text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] hover:bg-[var(--surface-tile)] transition-colors"
            >
              <FolderOpen className="h-3.5 w-3.5" />
              <span>Workspace Hub</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default IncidentSwitcher;
