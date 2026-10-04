"use client";

import { useState, useEffect, useMemo } from "react";
import { api, EvidenceItem } from "@/lib/api";

interface EvidenceExplorerProps {
  incidentId: string;
  onSelect?: (item: EvidenceItem) => void;
  onDownload?: (item: EvidenceItem) => void;
}

export function useEvidenceExplorer(incidentId: string) {
  const [loading, setLoading] = useState(false);
  const [evidenceItems, setEvidenceItems] = useState<EvidenceItem[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [error, setError] = useState<string | null>(null);

  const loadEvidenceItems = async () => {
    setLoading(true);
    setError(null);
    try {
      const incident = await api.get(incidentId);
      const items = incident.evidence_items || [];
      setEvidenceItems(items);
    } catch (e: any) {
      setError(e.message || "Failed to load evidence items");
      console.error("Failed to load evidence items:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (incidentId) {
      loadEvidenceItems();
    }
  }, [incidentId]);

  const filteredItems = useMemo(() => {
    return evidenceItems.filter(item => {
      const matchesSearch = !searchQuery ||
        item.file_path.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (item.checksum_sha256 && item.checksum_sha256.toLowerCase().includes(searchQuery.toLowerCase()));

      const matchesStatus = filterStatus === "all" || item.status === filterStatus;

      return matchesSearch && matchesStatus;
    });
  }, [evidenceItems, searchQuery, filterStatus]);

  const getStatusColor = (status: string) => {
    switch (status) {
      case "OBSERVED": return "text-[var(--color-accent)]";
      case "VALIDATED": return "text-[var(--color-brand-success)]";
      case "MISSING": return "text-[var(--color-brand-warning)]";
      default: return "text-muted";
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "OBSERVED": return "primary";
      case "VALIDATED": return "success";
      case "MISSING": return "warning";
      case "REDACTED": return "muted";
      default: return "secondary";
    }
  };

  return {
    loading,
    items: filteredItems,
    allItems: evidenceItems,
    searchQuery,
    setSearchQuery,
    filterStatus,
    setFilterStatus,
    error,
    getStatusColor,
    getStatusBadge,
    loadEvidenceItems
  };
}

interface EvidenceItemViewProps {
  item: EvidenceItem;
  onClose: () => void;
}

export function EvidenceItemView({ item, onClose }: EvidenceItemViewProps) {
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // SECURITY: For text files, load content safely - but note we don't render HTML
  const loadContent = async () => {
    setLoading(true);
    try {
      // SECURITY: Never render HTML directly - use text/plain or sanitized JSON
      const incidentReport = await api.getReport(item.file_path.split("/")[0] || "CAU-0001");

      // For now, show metadata only since actual file content would need safe handling
      setContent(null);
    } catch {
      setContent(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (item?.file_type?.startsWith("text/") || item?.file_type === "application/json") {
      // Note: In production, you'd fetch the actual file content securely
      // This is a placeholder that shows the metadata-based approach
    }
  }, [item]);

  const formatSize = (bytes: number) => {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  return (
    <div className="fixed inset-0 bg-[var(--color-overlay)] backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] w-full max-w-2xl max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-[var(--color-border)]">
          <h3 className="font-mono text-sm text-[var(--color-text-primary)] font-bold truncate">{item.file_path}</h3>
          <button onClick={onClose} className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] text-sm flex items-center justify-center h-8 w-8 rounded-lg hover:bg-[var(--color-surface)] transition-colors" aria-label="Close">
  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
  </svg>
</button>
        </div>
        <div className="p-4 overflow-y-auto">
          <div className="space-y-3 text-xs">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <span className="text-[var(--color-text-muted)]">Type:</span>
                <span className="text-[var(--color-text-muted)] font-mono ml-2">{item.file_type}</span>
              </div>
              <div>
                <span className="text-[var(--color-text-muted)]">Size:</span>
                <span className="font-mono ml-2 text-[var(--color-text-primary)]">{formatSize(item.size_bytes || 0)}</span>
              </div>
            </div>

            {/* SECURITY NOTE: We display metadata only, never raw file content as HTML */}
            <div className="p-3 rounded-lg bg-[var(--color-surface-2)]/50 border border-[var(--color-brand-danger)]/20 text-[var(--color-brand-danger)]/70">
              <div className="flex items-start gap-2">
                <svg className="w-4 h-4 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <div className="text-sm text-[var(--color-text-muted)]">
                  <span className="block font-bold mb-1">Security Restriction:</span>
                  Evidence files are stored securely and not rendered inline to prevent potential XSS attacks. Use the API endpoints to verify signatures and checksums.
                </div>
              </div>
            </div>

            <div className="pt-2">
              <span className="text-[var(--color-text-muted)]">Checksum (SHA-256):</span>
              <div className="font-mono text-xs text-[var(--color-accent)] break-all mt-1">{item.checksum_sha256 || "N/A"}</div>
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 p-4 border-t border-[var(--color-border)]">
          <button onClick={onClose} className="px-4 py-2 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]">Close</button>
        </div>
      </div>
    </div>
  );
}