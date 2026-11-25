import { api } from "@/lib/api";

export interface ExportedSessionResult {
  built: Awaited<ReturnType<typeof api.buildSession>>;
  filename: string;
}

/**
 * Build a `cauveris-session/v1` archive for an incident and trigger browser download.
 */
export async function exportAndDownloadSession(incidentId: string): Promise<ExportedSessionResult> {
  const built = await api.buildSession(incidentId);
  const { blob, filename } = await api.downloadSession(incidentId);

  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  window.URL.revokeObjectURL(url);
  document.body.removeChild(anchor);

  return { built, filename };
}
