"use client";

import React, { useState, useEffect, useMemo } from "react";
import { createPortal } from "react-dom";
import {
  X,
  Globe,
  Archive,
  GitBranch,
  Copy,
  Check,
  Search,
  ShieldCheck,
  ArrowRight,
} from "lucide-react";
import { api, IngestCapabilities } from "@/lib/api";
import { Button } from "./ui";

export interface SupportedFormatsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectExample?: (example: string) => void;
  capabilities?: IngestCapabilities | null;
}

const DEFAULT_SPEC_FORMS = [
  { form: "pypi:package[@version]", example: "pypi:requests@2.32.3", description: "PyPI source distribution (sdist preferred)" },
  { form: "npm:package[@version]", example: "npm:lodash@4.17.21", description: "npm registry package tarball (supports scoped @org/pkg)" },
  { form: "github:owner/repo[@ref]", example: "github:octocat/Hello-World", description: "GitHub codeload source tree archive" },
  { form: "crates:crate[@version]", example: "crates:serde@1.0.200", description: "crates.io Rust crate tarball" },
  { form: "go:module[@version]", example: "go:golang.org/x/sync@v0.7.0", description: "Go module zipball via official proxy" },
  { form: "nuget:package[@version]", example: "nuget:Newtonsoft.Json@13.0.3", description: "NuGet .NET package (.nupkg)" },
  { form: "gem:gem[@version]", example: "gem:rake@13.2.1", description: "RubyGems gem package (.gem)" },
  { form: "maven:group:artifact[@ver]", example: "maven:org.slf4j:slf4j-api@2.0.13", description: "Maven Central Java artifact" },
  { form: "git+https://...[.git]", example: "git+https://github.com/octocat/Hello-World.git", description: "Shallow git clone (isolated workspace)" },
  { form: "https://... (archive/file)", example: "https://example.com/telemetry.zip", description: "Direct HTTPS archive or evidence file (SSRF-protected)" },
];

const DEFAULT_ARCHIVES = ["zip", "tar", "tar.gz", "tgz", "tar.bz2", "tbz2", "tar.xz", "txz", "gz", "bz2", "xz"];

export function SupportedFormatsModal({
  isOpen,
  onClose,
  onSelectExample,
  capabilities: initialCapabilities,
}: SupportedFormatsModalProps) {
  const [mounted, setMounted] = useState(false);
  const [capabilities, setCapabilities] = useState<IngestCapabilities | null>(initialCapabilities || null);
  const [searchQuery, setSearchQuery] = useState("");
  const [copiedExample, setCopiedExample] = useState<string | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Sync capabilities if prop updates
  useEffect(() => {
    if (initialCapabilities) {
      setCapabilities(initialCapabilities);
    }
  }, [initialCapabilities]);

  // Fetch capabilities if not provided
  useEffect(() => {
    if (!isOpen || initialCapabilities || capabilities) return;
    let cancelled = false;
    try {
      const p = api.getIngestCapabilities?.();
      if (p && typeof p.then === "function") {
        p.then((caps) => {
          if (!cancelled && caps) setCapabilities(caps);
        }).catch((err) => {
          console.warn("Could not fetch ingest capabilities in modal", err);
        });
      }
    } catch (err) {
      console.warn("Error invoking getIngestCapabilities", err);
    }
    return () => {
      cancelled = true;
    };
  }, [isOpen, initialCapabilities, capabilities]);

  // Handle ESC key
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  const effectiveCapabilities = initialCapabilities || capabilities;

  const specForms = effectiveCapabilities?.spec_forms && effectiveCapabilities.spec_forms.length > 0
    ? effectiveCapabilities.spec_forms
    : DEFAULT_SPEC_FORMS;

  const archiveFormats = effectiveCapabilities?.supported_archive_formats && effectiveCapabilities.supported_archive_formats.length > 0
    ? effectiveCapabilities.supported_archive_formats
    : DEFAULT_ARCHIVES;

  const filteredSpecs = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return specForms;
    return specForms.filter(
      (item) =>
        item.form.toLowerCase().includes(q) ||
        item.example.toLowerCase().includes(q) ||
        item.description.toLowerCase().includes(q)
    );
  }, [specForms, searchQuery]);

  const handleCopy = (example: string, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(example);
    setCopiedExample(example);
    setTimeout(() => {
      setCopiedExample((cur) => (cur === example ? null : cur));
    }, 2000);
  };

  const handleSelect = (example: string) => {
    onSelectExample?.(example);
    onClose();
  };

  if (!isOpen || !mounted) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[120] flex items-center justify-center p-3 sm:p-6 bg-black/75 backdrop-blur-xs animate-fade-in"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="supported-formats-title"
    >
      <div
        className="relative w-full max-w-3xl rounded-[var(--radius-lg,8px)] border border-[var(--color-border-default,#27272a)] bg-[var(--color-canvas-inset,#09090b)] shadow-2xl overflow-hidden flex flex-col max-h-[88vh] animate-scale-in"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <header className="flex items-center justify-between gap-3 px-5 py-4 border-b border-[var(--color-border-default,#27272a)] bg-[var(--color-canvas-subtle,#18181b)] flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-md,6px)] bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <Globe className="h-4.5 w-4.5" />
            </div>
            <div>
              <h2 id="supported-formats-title" className="text-sm font-semibold text-zinc-100">
                Universal Intake Formats &amp; Registries
              </h2>
              <p className="text-xs text-zinc-400">
                Supported package registries, Git URLs, shorthands, and archive formats
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close formats reference"
            className="inline-flex h-8 w-8 items-center justify-center rounded-[var(--radius-md,6px)] text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/60 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        {/* Search & Filter Bar */}
        <div className="px-5 py-3 border-b border-[var(--color-border-default,#27272a)] bg-[var(--color-canvas,#09090b)] flex items-center gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search formats (e.g. pypi, npm, crates, git, tar.gz)..."
              className="w-full h-8 pl-8 pr-3 rounded-[var(--radius-sm,4px)] border border-[var(--color-border-default,#27272a)] bg-[var(--color-canvas-subtle,#18181b)] text-xs text-zinc-100 placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
            />
          </div>
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="text-[11px] text-zinc-400 hover:text-zinc-200"
            >
              Clear
            </button>
          )}
        </div>

        {/* Body content */}
        <div className="flex-1 min-h-0 overflow-y-auto p-5 space-y-6 overscroll-contain text-xs">
          {/* Section: Accepted Source Formats & Shorthands */}
          <section>
            <div className="flex items-center justify-between mb-2.5">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-200 flex items-center gap-2">
                <GitBranch className="h-3.5 w-3.5 text-indigo-400" />
                Accepted Source Formats &amp; Shorthands
              </h3>
              <span className="text-[11px] text-zinc-400">
                {filteredSpecs.length} {filteredSpecs.length === 1 ? "format" : "formats"}
              </span>
            </div>

            {filteredSpecs.length === 0 ? (
              <div className="p-6 text-center text-zinc-500 rounded border border-dashed border-zinc-800">
                No formats matching &ldquo;{searchQuery}&rdquo;
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {filteredSpecs.map((item, idx) => (
                  <div
                    key={idx}
                    onClick={() => handleSelect(item.example)}
                    className="p-2.5 rounded-[var(--radius-sm,4px)] bg-zinc-900/60 border border-zinc-800/90 hover:border-indigo-500/60 hover:bg-zinc-900 transition-all cursor-pointer group flex flex-col justify-between gap-1.5"
                    title="Click to insert this example"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[11px] font-semibold text-indigo-300">
                        {item.form}
                      </span>
                      <div className="flex items-center gap-1.5 opacity-80 group-hover:opacity-100">
                        <button
                          type="button"
                          onClick={(e) => handleCopy(item.example, e)}
                          title="Copy example"
                          className="p-1 rounded text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800"
                        >
                          {copiedExample === item.example ? (
                            <Check className="h-3 w-3 text-emerald-400" />
                          ) : (
                            <Copy className="h-3 w-3" />
                          )}
                        </button>
                        <span className="text-[10px] text-indigo-400 group-hover:underline flex items-center gap-0.5">
                          Use <ArrowRight className="h-2.5 w-2.5" />
                        </span>
                      </div>
                    </div>

                    <code className="block text-[11px] font-mono text-zinc-300 bg-zinc-950/80 px-1.5 py-1 rounded border border-zinc-800/60 truncate">
                      {item.example}
                    </code>

                    <p className="text-[11px] text-zinc-400 line-clamp-1">{item.description}</p>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Section: Supported Archive & Compression Formats */}
          <section className="pt-2 border-t border-zinc-800/70">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-200 mb-2 flex items-center gap-2">
              <Archive className="h-3.5 w-3.5 text-emerald-400" />
              Supported Archive &amp; Compression Formats
            </h3>
            <p className="text-[11px] text-zinc-400 mb-2.5">
              Cauveris inspects archive magic bytes to identify formats, preventing file-extension spoofing and zip-bombs:
            </p>
            <div className="flex flex-wrap gap-1.5">
              {archiveFormats.map((fmt, idx) => (
                <span
                  key={idx}
                  className="px-2 py-0.5 rounded bg-zinc-800/80 border border-zinc-700/60 font-mono text-[11px] text-zinc-200"
                >
                  .{fmt}
                </span>
              ))}
            </div>
          </section>

          {/* Section: Security Perimeter & Resource Limits */}
          <section className="pt-2 border-t border-zinc-800/70">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-200 mb-2 flex items-center gap-2">
              <ShieldCheck className="h-3.5 w-3.5 text-cyan-400" />
              Security Perimeter &amp; System Limits
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
              <div className="p-2 rounded bg-zinc-900/50 border border-zinc-800">
                <span className="text-zinc-400 block text-[10px]">Max Download</span>
                <span className="font-mono text-zinc-200 font-semibold">
                  {effectiveCapabilities?.limits?.max_download_size
                    ? `${(effectiveCapabilities.limits.max_download_size / (1024 * 1024)).toFixed(0)} MB`
                    : "50 MB"}
                </span>
              </div>
              <div className="p-2 rounded bg-zinc-900/50 border border-zinc-800">
                <span className="text-zinc-400 block text-[10px]">Max Archive Size</span>
                <span className="font-mono text-zinc-200 font-semibold">
                  {effectiveCapabilities?.limits?.max_archive_uncompressed_size
                    ? `${(effectiveCapabilities.limits.max_archive_uncompressed_size / (1024 * 1024)).toFixed(0)} MB`
                    : "200 MB"}
                </span>
              </div>
              <div className="p-2 rounded bg-zinc-900/50 border border-zinc-800">
                <span className="text-zinc-400 block text-[10px]">Max Member Files</span>
                <span className="font-mono text-zinc-200 font-semibold">
                  {effectiveCapabilities?.limits?.max_archive_members || 1000} files
                </span>
              </div>
              <div className="p-2 rounded bg-zinc-900/50 border border-zinc-800">
                <span className="text-zinc-400 block text-[10px]">SSRF Protection</span>
                <span className="text-emerald-400 font-semibold flex items-center gap-1">
                  Active (Blocked)
                </span>
              </div>
            </div>
          </section>
        </div>

        {/* Footer */}
        <footer className="px-5 py-3 border-t border-[var(--color-border-default,#27272a)] bg-[var(--color-canvas-subtle,#18181b)] flex items-center justify-between text-xs text-zinc-400 flex-shrink-0">
          <span className="hidden sm:inline text-[11px]">
            Click any format card to insert it directly into the intake field.
          </span>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </footer>
      </div>
    </div>,
    document.body
  );
}
