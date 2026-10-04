"use client";

import { useState, useEffect, useCallback, useMemo, type ReactNode, useRef } from "react";
import { tv } from "tailwind-variants";
import { X, ChevronRight, Search, Zap, Database, GitBranch, FlaskConical, Wrench, Eye, FileText, RotateCcw, Download, AlertTriangle, Plus, Upload, Play, Square, ExternalLink, Clock } from "lucide-react";
import { Button, Badge } from "./ui";
import { Tooltip } from "./Tooltip";
import { useShell } from "@/lib/useShell";
import { useActiveIncident } from "@/lib/useIncident";
import { api } from "@/lib/api";
import { useRouter } from "next/navigation";

const paletteStyles = tv({
  base: `
    fixed inset-0 z-50 flex items-start justify-center pt-16
    bg-[var(--color-overlay)] backdrop-blur-sm
    animate-fade-in
  `,
});

const panelStyles = tv({
  base: `
    w-full max-w-2xl rounded-2xl border border-[var(--color-border)]
    bg-[var(--theme-background)]/95 backdrop-blur-xl shadow-2xl
    overflow-hidden flex flex-col
    animate-slide-up
  `,
});

const headerStyles = tv({
  base: `
    flex items-center gap-3 px-4 py-3 border-b border-[var(--color-border)]
    bg-[var(--color-surface)]/60 backdrop-blur-sm
  `,
});

const searchStyles = tv({
  base: `
    relative flex-1
  `,
});

const listStyles = tv({
  base: `
    flex-1 overflow-y-auto max-h-[60vh] min-h-[200px]
  `,
});

const categoryStyles = tv({
  base: `
    px-4 py-2 text-[10px] font-medium uppercase tracking-widest text-[var(--color-text-muted)]
    border-b border-[var(--color-border)]
  `,
});

const itemStyles = tv({
  base: `
    flex items-center gap-3 px-4 py-2.5 text-sm
    hover:bg-[var(--color-surface)] transition-colors
    cursor-pointer
    border-b border-[var(--color-border)] last:border-0
    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--theme-background)]
  `,
  variants: {
    selected: {
      true: "bg-[var(--color-surface)]",
      false: "",
    },
    disabled: {
      true: "opacity-50 cursor-not-allowed",
      false: "",
    },
  },
  defaultVariants: {
    selected: false,
    disabled: false,
  },
});

const shortcutStyles = tv({
  base: `
    flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium
    bg-[var(--color-surface)] text-[var(--color-text-muted)] border border-[var(--color-border)]
  `,
});

const emptyStyles = tv({
  base: `
    flex flex-col items-center justify-center py-12 px-6 gap-3 text-center text-[var(--color-text-muted)]
  `,
});

const footerStyles = tv({
  base: `
    flex items-center justify-between px-4 py-2 border-t border-[var(--color-border)]
    bg-[var(--color-surface)]/60 backdrop-blur-sm text-[11px] text-[var(--color-text-muted)]
  `,
});

interface Command {
  id: string;
  label: string;
  description: string;
  shortcut: string;
  category: "incident" | "investigation" | "views" | "export" | "demo";
  action: () => void | Promise<void>;
  disabled?: boolean;
  icon?: ReactNode;
}

const CATEGORIES: { key: Command["category"]; label: string; icon: ReactNode }[] = [
  { key: "incident", label: "Incident", icon: <Database className="h-3.5 w-3.5" /> },
  { key: "investigation", label: "Investigation", icon: <Play className="h-3.5 w-3.5" /> },
  { key: "views", label: "Views", icon: <ExternalLink className="h-3.5 w-3.5" /> },
  { key: "export", label: "Export", icon: <Download className="h-3.5 w-3.5" /> },
  { key: "demo", label: "Demo", icon: <RotateCcw className="h-3.5 w-3.5" /> },
];

export function CommandPalette() {
  const { state, setCommandPalette, toggleCommandPalette, toggleNavCollapse } = useShell();
  const { incident, loadIncident } = useActiveIncident();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [isMounted, setIsMounted] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setIsMounted(true);
    setQuery("");
    setSelectedIndex(0);
    // Focus search input
    searchInputRef.current?.focus();
  }, [state.commandPaletteOpen]);

  // Handle global escape key to close palette
  useEffect(() => {
    if (!state.commandPaletteOpen) return;

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setCommandPalette(false);
      }
    };

    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [state.commandPaletteOpen, setCommandPalette]);

  // Build commands
  const commands = useMemo<Command[]>(() => [
    // Incident
    {
      id: "create-incident",
      label: "Create Incident",
      description: "Create a new incident investigation",
      shortcut: "C I",
      category: "incident",
      icon: <Plus className="h-3.5 w-3.5" />,
      action: async () => {
        try {
          const result = await api.create(false, { title: "New Incident" });
          if (result.incident_id) {
            loadIncident(result.incident_id);
            router.push("/");
          }
        } catch (error) {
          console.error("Failed to create incident:", error);
        }
        setCommandPalette(false);
      },
    },
    {
      id: "load-golden",
      label: "Load Golden Incident",
      description: "Load the CAU-0001 golden incident for demonstration",
      shortcut: "L G",
      category: "incident",
      icon: <Download className="h-3.5 w-3.5" />,
      action: async () => {
        try {
          const result = await api.create(true);
          if (result.incident_id) {
            loadIncident(result.incident_id);
            router.push("/");
          }
        } catch (error) {
          console.error("Failed to load golden incident:", error);
        }
        setCommandPalette(false);
      },
    },
    {
      id: "upload-evidence",
      label: "Upload Evidence Bundle",
      description: "Upload evidence artifacts from local files",
      shortcut: "U B",
      category: "incident",
      icon: <Upload className="h-3.5 w-3.5" />,
      action: () => {
        const input = document.createElement("input");
        input.type = "file";
        input.accept = ".zip,.json,.tar.gz";
        input.multiple = true;
        input.onchange = (e) => {
          const files = (e.target as HTMLInputElement).files;
          if (files && files.length > 0) {
            // TODO: Implement upload
            console.log("Uploading", files.length, "files");
          }
        };
        input.click();
        setCommandPalette(false);
      },
    },

    // Investigation
    {
      id: "start-investigation",
      label: "Start Investigation",
      description: "Begin autonomous pipeline reconstruction",
      shortcut: "S I",
      category: "investigation",
      icon: <Play className="h-3.5 w-3.5" />,
      action: async () => {
        if (!incident) return;
        try {
          await api.reconstruct(incident.id);
          router.push("/reality-rewind");
        } catch (error) {
          console.error("Failed to start investigation:", error);
        }
        setCommandPalette(false);
      },
      disabled: !incident,
    },
    {
      id: "cancel-investigation",
      label: "Cancel Investigation",
      description: "Stop the currently running pipeline",
      shortcut: "C X",
      category: "investigation",
      icon: <Square className="h-3.5 w-3.5" />,
      action: async () => {
        if (!incident) return;
        try {
          await api.cancel(incident.id);
        } catch (error) {
          console.error("Failed to cancel investigation:", error);
        }
        setCommandPalette(false);
      },
      disabled: !incident,
    },

    // Views
    {
      id: "toggle-sidebar",
      label: state.isNavCollapsed ? "Expand Sidebar" : "Collapse Sidebar",
      description: "Toggle left navigation sidebar between expanded and collapsed",
      shortcut: "[",
      category: "views",
      icon: <ChevronRight className="h-3.5 w-3.5" />,
      action: () => {
        toggleNavCollapse();
        setCommandPalette(false);
      },
    },
    {
      id: "open-timeline",
      label: "Open Timeline",
      description: "View event timeline in Reality Rewind",
      shortcut: "O T",
      category: "views",
      icon: <Clock className="h-3.5 w-3.5" />,
      action: () => {
        router.push("/reality-rewind");
        setCommandPalette(false);
      },
    },
    {
      id: "open-graph",
      label: "Open Graph",
      description: "View causal graph in Causal Constellation",
      shortcut: "O G",
      category: "views",
      icon: <GitBranch className="h-3.5 w-3.5" />,
      action: () => {
        router.push("/causal-constellation");
        setCommandPalette(false);
      },
    },
    {
      id: "open-reconstruction",
      label: "Open Reconstruction",
      description: "View holographic reconstruction",
      shortcut: "O R",
      category: "views",
      icon: <Eye className="h-3.5 w-3.5" />,
      action: () => {
        router.push("/holographic-reconstruction");
        setCommandPalette(false);
      },
    },
    {
      id: "open-ghost-lab",
      label: "Open Ghost Lab",
      description: "Run simulation experiments",
      shortcut: "O L",
      category: "views",
      icon: <FlaskConical className="h-3.5 w-3.5" />,
      action: () => {
        router.push("/ghost-lab");
        setCommandPalette(false);
      },
    },
    {
      id: "verify-patch",
      label: "Verify Patch",
      description: "Review patch candidates in Patch Forge",
      shortcut: "V P",
      category: "views",
      icon: <Wrench className="h-3.5 w-3.5" />,
      action: () => {
        router.push("/patch-forge");
        setCommandPalette(false);
      },
    },

    // Export
    {
      id: "export-report",
      label: "Export Report",
      description: "Download investigation report as JSON",
      shortcut: "E R",
      category: "export",
      icon: <FileText className="h-3.5 w-3.5" />,
      action: async () => {
        if (!incident) return;
        try {
          const report = await api.exportReport(incident.id);
          const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `${incident.id}-report.json`;
          a.click();
          URL.revokeObjectURL(url);
        } catch (error) {
          console.error("Failed to export report:", error);
        }
        setCommandPalette(false);
      },
      disabled: !incident,
    },

    // Demo
    {
      id: "reset-demo",
      label: "Reset Demo Environment",
      description: "Clear all demo data and reset to initial state",
      shortcut: "R D",
      category: "demo",
      icon: <AlertTriangle className="h-3.5 w-3.5" />,
      action: async () => {
        if (confirm("Reset demo environment? This will clear all demo data.")) {
          try {
            await api.resetDemo();
            window.location.reload();
          } catch (error) {
            console.error("Failed to reset demo:", error);
          }
        }
        setCommandPalette(false);
      },
    },
  ], [incident, loadIncident, router, setCommandPalette]);

  // Filter commands by query
  const filteredCommands = useMemo(() => {
    if (!query.trim()) return commands;
    const q = query.toLowerCase();
    return commands.filter(
      (cmd) =>
        cmd.label.toLowerCase().includes(q) ||
        cmd.description.toLowerCase().includes(q) ||
        cmd.shortcut.toLowerCase().includes(q) ||
        cmd.category.toLowerCase().includes(q)
    );
  }, [commands, query]);

  // Group by category
  const groupedCommands = useMemo(() => {
    const groups: Record<Command["category"], Command[]> = {
      incident: [],
      investigation: [],
      views: [],
      export: [],
      demo: [],
    };
    filteredCommands.forEach((cmd) => groups[cmd.category].push(cmd));
    return groups;
  }, [filteredCommands]);

  // Handle keyboard navigation
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const totalItems = filteredCommands.length;
      if (totalItems === 0) return;

      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setSelectedIndex((prev) => (prev + 1) % totalItems);
          break;
        case "ArrowUp":
          e.preventDefault();
          setSelectedIndex((prev) => (prev - 1 + totalItems) % totalItems);
          break;
        case "Enter":
          e.preventDefault();
          if (filteredCommands[selectedIndex] && !filteredCommands[selectedIndex].disabled) {
            filteredCommands[selectedIndex].action();
          }
          break;
        case "Escape":
          setCommandPalette(false);
          break;
      }
    },
    [filteredCommands, selectedIndex, setCommandPalette]
  );

  if (!state.commandPaletteOpen || !isMounted) return null;

  return (
    <div className={paletteStyles()} onKeyDown={handleKeyDown} role="dialog" aria-modal="true" aria-label="Command Palette">
      <div className={panelStyles()}>
        {/* Header */}
        <header className={headerStyles()}>
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-accent)]/10 text-[var(--color-accent)]">
            <Zap className="h-5 w-5" />
          </div>
          <div className={searchStyles()}>
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--color-text-muted)] pointer-events-none" />
            <input
              id="command-palette-search"
              type="text"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setSelectedIndex(0);
              }}
              placeholder="Type a command or search…"
              className="w-full h-10 pl-10 pr-4 bg-[var(--color-surface-2)]/60 border border-[var(--color-border)] rounded-xl text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]/60 focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] focus:border-transparent transition-all"
              autoFocus
            />
          </div>
          <Tooltip content="Close (Esc)" position="left">
            <button
              onClick={() => setCommandPalette(false)}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface)] transition-colors border border-transparent hover:border-[var(--color-border)]"
              aria-label="Close command palette"
            >
              <X className="h-4 w-4" />
            </button>
          </Tooltip>
        </header>

        {/* Results */}
        <div className={listStyles()} role="listbox" aria-label="Commands">
          {filteredCommands.length === 0 ? (
            <div className={emptyStyles()}>
              <Search className="h-8 w-8 text-[var(--color-text-muted)]/50" />
              <span>No commands match "{query}"</span>
              <span className="text-[11px]">Try a different search term</span>
            </div>
          ) : (
            <>
              {CATEGORIES.map(({ key, label, icon }) => {
                const items = groupedCommands[key];
                if (!items.length) return null;
                return (
                  <div key={key}>
                    <div className={categoryStyles()} aria-hidden="true">
                      <span className="flex items-center gap-1.5">{icon} {label}</span>
                    </div>
                    {items.map((cmd, index) => {
                      const globalIndex = filteredCommands.indexOf(cmd);
                      const isSelected = globalIndex === selectedIndex;
                      return (
                        <div
                          key={cmd.id}
                          className={itemStyles({ selected: isSelected, disabled: cmd.disabled })}
                          role="option"
                          aria-selected={isSelected}
                          aria-disabled={cmd.disabled}
                          onClick={() => !cmd.disabled && cmd.action()}
                          onMouseEnter={() => setSelectedIndex(globalIndex)}
                        >
                          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-surface)] text-[var(--color-text-muted)]">
                            {cmd.icon || <Zap className="h-4 w-4" />}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="font-medium text-[var(--color-text-primary)] truncate">{cmd.label}</div>
                            <div className="text-[11px] text-[var(--color-text-muted)] truncate">{cmd.description}</div>
                          </div>
                          <div className="flex items-center gap-1.5">
                            {cmd.shortcut.split(" ").map((key) => (
                              <kbd key={key} className={shortcutStyles()}>
                                {key}
                              </kbd>
                            ))}
                            {isSelected && <ChevronRight className="h-4 w-4 text-[var(--color-accent)]" />}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </>
          )}
        </div>

        {/* Footer */}
        <footer className={footerStyles()}>
          <span>↑↓ Navigate • Enter Execute • Esc Close</span>
          <span>{filteredCommands.length} command{filteredCommands.length !== 1 ? "s" : ""}</span>
        </footer>
      </div>
    </div>
  );
}