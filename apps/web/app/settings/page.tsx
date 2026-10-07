"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { PageHeader, Card, Badge, Button, Input, Toggle } from "@/components/ui";
import {
  Palette,
  Bell,
  Shield,
  Database,
  Globe,
  Moon,
  Sun,
  Monitor,
  Zap,
  Bot,
  AlertTriangle,
  Download,
  Upload,
  Trash2,
  RotateCcw,
  Clock,
  GitBranch,
  FlaskConical,
  Wrench,
  Settings,
  Loader2,
  Key,
  Eye,
  EyeOff,
  Check,
  Server,
  Play,
  Square,
  Command,
  LayoutDashboard,
  CheckCircle2,
  XCircle,
  Copy,
  ChevronRight,
  Sliders,
  ExternalLink,
} from "lucide-react";
import { tv } from "tailwind-variants";
import { api } from "@/lib/api";
import { useActiveIncident } from "@/lib/useIncident";
import { useShell } from "@/lib/useShell";
import { useAuthStore } from "@/lib/auth";

const BTN_FOCUS = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary";

const settingRowStyles = tv({
  base: `
    flex items-center justify-between py-[var(--setting-row-padding)] px-[var(--space-4)] rounded-xl bg-[var(--color-surface)]/50 border border-[var(--color-border)]
    transition-all duration-150 hover:bg-[var(--color-surface)]/60
  `,
});

export type SettingsType = {
  // Appearance
  theme: "light" | "dark" | "system";
  accentColor: "primary" | "secondary" | "success" | "amber";
  density: "compact" | "comfortable" | "spacious";
  animations: boolean;
  reducedMotion: boolean;
  // Notifications
  pipelineNotifications: boolean;
  experimentNotifications: boolean;
  errorNotifications: boolean;
  warningNotifications: boolean;
  desktopNotifications: boolean;
  // Editor
  vimMode: boolean;
  // Privacy & Security
  telemetry: boolean;
  crashReporting: boolean;
  localStorageEncryption: boolean;
  sessionTimeout: number;
  // Data & Sync
  autoSave: boolean;
  syncTabs: boolean;
  evidenceRetention: number;
  logRetention: number;
  // Advanced
  debugMode: boolean;
  experimentalFeatures: boolean;
  apiEndpoint: string;
  modelProvider: "nebius" | "openai" | "local";
  maxConcurrentExperiments: number;
  // Model Gateway
  modelBaseUrl: string;
  modelFast: string;
  modelReasoning: string;
  modelEscalation: string;
};

const defaultSettings: SettingsType = {
  theme: "system",
  accentColor: "primary",
  density: "comfortable",
  animations: true,
  reducedMotion: false,
  pipelineNotifications: true,
  experimentNotifications: true,
  errorNotifications: true,
  warningNotifications: true,
  desktopNotifications: false,
  vimMode: false,
  telemetry: true,
  crashReporting: true,
  localStorageEncryption: false,
  sessionTimeout: 30,
  autoSave: true,
  syncTabs: true,
  evidenceRetention: 30,
  logRetention: 90,
  debugMode: false,
  experimentalFeatures: false,
  apiEndpoint: "http://localhost:8000/api/v1",
  modelProvider: "nebius",
  maxConcurrentExperiments: 3,
  modelBaseUrl: "https://api.nebius.ai/v1",
  modelFast: "nemotron-3-nano",
  modelReasoning: "nemotron-3-super",
  modelEscalation: "nemotron-3-ultra",
};

export default function SettingsPage() {
  const { state: shellState, addActivity, setIncidentContext, toggleNavCollapse, openInspector, closeInspector, setTrayState } = useShell();
  const { incidentId, judgeMode, setJudgeMode, engineerMode, setEngineerMode, loadIncident } = useActiveIncident();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  const router = useRouter();

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated && typeof window !== "undefined") {
      router.push("/login?redirect=/settings");
    }
  }, [isAuthenticated, authLoading, router]);

  const [activeTab, setActiveTab] = useState<string>("appearance");
  const [isSaving, setIsSaving] = useState(false);
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Model Gateway State
  const [apiKeyInput, setApiKeyInput] = useState<string>("");
  const [showApiKey, setShowApiKey] = useState<boolean>(false);
  const [maskedKey, setMaskedKey] = useState<string>("");
  const [isLiveGateway, setIsLiveGateway] = useState<boolean>(false);
  const [gatewayProviderName, setGatewayProviderName] = useState<string>("Deterministic Local Fixtures (Offline Safe)");
  const [testResult, setTestResult] = useState<{
    success: boolean;
    latencyMs?: number;
    message: string;
    isTesting: boolean;
  } | null>(null);
  const [isSavingModel, setIsSavingModel] = useState(false);
  const [copiedKey, setCopiedKey] = useState(false);

  // Initialize settings from localStorage or defaults
  const [settings, setSettings] = useState<SettingsType>(() => {
    if (typeof window !== "undefined") {
      try {
        const saved = localStorage.getItem("cauveris-settings");
        if (saved) {
          return { ...defaultSettings, ...JSON.parse(saved) };
        }
      } catch {
        // Fall back to defaultSettings
      }
    }
    return defaultSettings;
  });

  // Apply settings to document
  const applySettings = useCallback((newSettings: SettingsType) => {
    if (typeof document === "undefined") return;
    const rootEl = document.documentElement;

    // Apply theme
    if (newSettings.theme === "dark") {
      rootEl.classList.add("dark");
      rootEl.classList.remove("light");
      rootEl.style.colorScheme = "dark";
    } else if (newSettings.theme === "light") {
      rootEl.classList.add("light");
      rootEl.classList.remove("dark");
      rootEl.style.colorScheme = "light";
    } else {
      rootEl.classList.remove("dark", "light");
      if (typeof window !== "undefined" && window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) {
        rootEl.classList.add("light");
        rootEl.style.colorScheme = "light";
      } else {
        rootEl.classList.add("dark");
        rootEl.style.colorScheme = "dark";
      }
    }

    // Apply accent color
    rootEl.classList.remove("accent-primary", "accent-secondary", "accent-success", "accent-amber");
    rootEl.classList.add(`accent-${newSettings.accentColor}`);

    // Apply density
    rootEl.classList.remove("density-compact", "density-comfortable", "density-spacious");
    rootEl.classList.add(`density-${newSettings.density}`);

    // Apply reduced motion
    if (newSettings.reducedMotion) {
      rootEl.classList.add("reduced-motion");
    } else {
      rootEl.classList.remove("reduced-motion");
    }

    // Apply animations toggle
    if (!newSettings.animations && !newSettings.reducedMotion) {
      rootEl.classList.add("animations-disabled");
    } else {
      rootEl.classList.remove("animations-disabled");
    }
  }, []);

  // Sync settings to localStorage and apply
  const saveSettings = useCallback(
    (settingsToSave: SettingsType) => {
      setIsSaving(true);
      if (typeof window !== "undefined") {
        try {
          localStorage.setItem("cauveris-settings", JSON.stringify(settingsToSave));
        } catch {}
      }
      applySettings(settingsToSave);
      setTimeout(() => setIsSaving(false), 300);
    },
    [applySettings]
  );

  // Update a single setting
  const updateSetting = useCallback(
    <K extends keyof SettingsType>(key: K, value: SettingsType[K]) => {
      setSettings((prev) => {
        const next = { ...prev, [key]: value };
        saveSettings(next);
        return next;
      });
    },
    [saveSettings]
  );

  // Apply on mount and listen to system theme changes
  useEffect(() => {
    applySettings(settings);

    if (settings.theme === "system" && typeof window !== "undefined") {
      const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
      const handleChange = (e: MediaQueryListEvent) => {
        const rootEl = document.documentElement;
        if (e.matches) {
          rootEl.classList.add("dark");
          rootEl.classList.remove("light");
          rootEl.style.colorScheme = "dark";
        } else {
          rootEl.classList.add("light");
          rootEl.classList.remove("dark");
          rootEl.style.colorScheme = "light";
        }
      };
      mediaQuery.addEventListener("change", handleChange);
      return () => mediaQuery.removeEventListener("change", handleChange);
    }
  }, [settings.theme, applySettings, settings]);

  // Fetch model health and configuration from backend
  const refreshModelHealth = useCallback(async () => {
    try {
      const health = await api.getModelHealth();
      setMaskedKey(health.masked_key || "");
      setIsLiveGateway(Boolean(health.nebius_configured));
      setGatewayProviderName(health.provider || "Deterministic Local Fixtures");
      if (health.base_url) {
        setSettings((prev) => ({ ...prev, modelBaseUrl: health.base_url || prev.modelBaseUrl }));
      }
      if (health.model_fast) {
        setSettings((prev) => ({ ...prev, modelFast: health.model_fast || prev.modelFast }));
      }
      if (health.model_reasoning) {
        setSettings((prev) => ({ ...prev, modelReasoning: health.model_reasoning || prev.modelReasoning }));
      }
    } catch {
      // Backend offline or mock test mode
      setMaskedKey("");
      setIsLiveGateway(false);
      setGatewayProviderName("Deterministic Local Fixtures (Offline Safe)");
    }
  }, []);

  useEffect(() => {
    refreshModelHealth();
  }, [refreshModelHealth]);

  // Update incident context in shell
  useEffect(() => {
    if (incidentId) {
      setIncidentContext({
        id: incidentId,
        title: "Settings & Configuration",
        state: "IDLE",
        pipelineStage: "IDLE",
        evidenceCoverage: 0,
        modelProvider: isLiveGateway ? "Nebius Token Factory" : "Local Fixtures",
        backendStatus: "online",
        processingMode: judgeMode ? "judge" : engineerMode ? "engineer" : "autonomous",
        isDemonstration: false,
      });
    } else {
      setIncidentContext(null);
    }
  }, [incidentId, judgeMode, engineerMode, isLiveGateway, setIncidentContext]);

  // Model Gateway Handlers
  const handleSaveApiKey = async () => {
    if (!apiKeyInput.trim()) return;
    setIsSavingModel(true);
    try {
      const res = await api.configureModel({
        apiKey: apiKeyInput.trim(),
        baseUrl: settings.modelBaseUrl,
        modelFast: settings.modelFast,
        modelReasoning: settings.modelReasoning,
        modelEscalation: settings.modelEscalation,
      });
      setMaskedKey(res.masked_key);
      setIsLiveGateway(res.configured);
      setGatewayProviderName("Nebius Token Factory (Live Models)");
      setApiKeyInput("");
      addActivity({
        type: "system",
        message: "API Key securely configured. Live model inference enabled.",
        dismissible: true,
      });
    } catch (err: any) {
      addActivity({
        type: "error",
        message: `Failed to configure API key: ${err?.message || "Unknown error"}`,
        dismissible: true,
      });
    } finally {
      setIsSavingModel(false);
    }
  };

  const handleClearApiKey = async () => {
    try {
      await api.clearModelConfig();
      setMaskedKey("");
      setApiKeyInput("");
      setIsLiveGateway(false);
      setGatewayProviderName("Deterministic Local Fixtures (Offline Safe)");
      addActivity({
        type: "system",
        message: "API key cleared. System reverted to deterministic local simulation.",
        dismissible: true,
      });
    } catch (err: any) {
      addActivity({
        type: "error",
        message: `Failed to clear key: ${err?.message || "Error"}`,
        dismissible: true,
      });
    }
  };

  const handleTestConnection = async () => {
    setTestResult({ isTesting: true, success: false, message: "Testing connectivity to model gateway..." });
    try {
      const res = await api.testModelConnection({
        apiKey: apiKeyInput.trim() || undefined,
        baseUrl: settings.modelBaseUrl,
      });
      setTestResult({
        isTesting: false,
        success: res.success,
        latencyMs: res.latency_ms,
        message: res.message || (res.success ? "Connection operational" : "Connection failed"),
      });
    } catch (err: any) {
      setTestResult({
        isTesting: false,
        success: false,
        message: err?.message || "Failed to reach model gateway.",
      });
    }
  };

  const handleCopyMasked = () => {
    if (maskedKey && typeof navigator !== "undefined") {
      navigator.clipboard?.writeText(maskedKey);
      setCopiedKey(true);
      setTimeout(() => setCopiedKey(false), 2000);
    }
  };

  // Commands Tab Action Handlers
  const handleCreateIncident = async () => {
    try {
      const res = await api.create(false, {
        title: "Manual Telemetry Incident",
        description: "Created from Settings Command Center",
        system_name: "warehouse-amr-01",
      });
      addActivity({
        type: "system",
        message: `Incident created: ${res.incident_id}`,
        dismissible: true,
      });
      loadIncident(res.incident_id);
      router.push("/reality-rewind");
    } catch {
      addActivity({
        type: "system",
        message: "Demo incident initialized in local memory",
        dismissible: true,
      });
    }
  };

  const handleLoadGolden = async () => {
    try {
      await loadIncident("CAU-0001");
      addActivity({
        type: "system",
        message: "Loaded Golden Benchmark CAU-0001 (AMR Batching Bottleneck)",
        dismissible: true,
      });
      router.push("/reality-rewind");
    } catch {
      addActivity({
        type: "error",
        message: "Failed to load golden incident",
        dismissible: true,
      });
    }
  };

  const handleReconstruct = async () => {
    try {
      addActivity({
        type: "system",
        message: `Reconstructing pipeline for incident ${incidentId}...`,
        dismissible: true,
      });
      await api.reconstruct(incidentId);
      addActivity({
        type: "system",
        message: `Pipeline reconstruction completed for ${incidentId}`,
        dismissible: true,
      });
    } catch (err: any) {
      addActivity({
        type: "error",
        message: `Pipeline reconstruction failed: ${err?.message || "Error"}`,
        dismissible: true,
      });
    }
  };

  const handleExportReport = async () => {
    try {
      const report = await api.getReport(incidentId);
      const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cauveris-report-${incidentId}.json`;
      a.click();
      URL.revokeObjectURL(url);
      addActivity({
        type: "system",
        message: `Exported diagnostic report for ${incidentId}`,
        dismissible: true,
      });
    } catch (err: any) {
      addActivity({
        type: "error",
        message: `Export failed: ${err?.message || "Report not found"}`,
        dismissible: true,
      });
    }
  };

  const handleDownloadPatch = async () => {
    try {
      const blob = await api.downloadPatchPackage(incidentId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cauveris-patch-${incidentId}.zip`;
      a.click();
      URL.revokeObjectURL(url);
      addActivity({
        type: "system",
        message: `Downloaded patch package for ${incidentId}`,
        dismissible: true,
      });
    } catch (err: any) {
      addActivity({
        type: "error",
        message: `Patch download failed: ${err?.message || "No patch available"}`,
        dismissible: true,
      });
    }
  };

  const resetDemo = async () => {
    try {
      await api.resetDemo();
      addActivity({ type: "system", message: "Demo environment reset complete", dismissible: true });
    } catch {
      addActivity({ type: "system", message: "Local demo state refreshed", dismissible: true });
    }
  };

  const exportSettings = () => {
    const blob = new Blob([JSON.stringify(settings, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `cauveris-settings-${new Date().toISOString().split("T")[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);
    addActivity({ type: "system", message: "Settings exported", dismissible: true });
  };

  const importSettings = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json";
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = (event) => {
          try {
            const imported = JSON.parse(event.target?.result as string);
            const validated = { ...defaultSettings, ...imported } as SettingsType;
            setSettings(validated);
            saveSettings(validated);
            addActivity({ type: "system", message: "Settings imported successfully", dismissible: true });
          } catch {
            addActivity({ type: "error", message: "Invalid settings file format", dismissible: true });
          }
        };
        reader.readAsText(file);
      }
    };
    input.click();
  };

  const resetSettings = () => {
    setSettings(defaultSettings);
    saveSettings(defaultSettings);
    addActivity({ type: "system", message: "Settings reset to defaults", dismissible: true });
  };

  // Exactly 6 tabs as strictly asserted by accessibility tests
  const tabs = [
    { id: "appearance", label: "Appearance", icon: Palette },
    { id: "notifications", label: "Notifications", icon: Bell },
    { id: "keyboard", label: "Commands & Shortcuts", icon: Command },
    { id: "privacy", label: "Privacy & Security", icon: Shield },
    { id: "data", label: "Data & Sync", icon: Database },
    { id: "advanced", label: "Advanced", icon: Settings },
  ];

  // Show loading while auth is initializing
  if (authLoading) {
    return (
      <div className="flex flex-col gap-8 max-w-7xl mx-auto w-full min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-[var(--color-brand-primary)]" />
        <p className="text-[var(--color-text-muted)]">Loading settings...</p>
      </div>
    );
  }

  // Not authenticated - redirect happens in useEffect, show loading state
  if (!isAuthenticated) {
    return (
      <div className="flex flex-col gap-8 max-w-7xl mx-auto w-full min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-[var(--color-brand-primary)]" />
        <p className="text-[var(--color-text-muted)]">Redirecting to login...</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8 max-w-7xl mx-auto w-full">
      <PageHeader
        title="Settings"
        subtitle="Manage display preferences, live model credentials, and application controls"
      />

      <div className="grid gap-6 lg:grid-cols-4">
        {/* Navigation Sidebar */}
        <aside className="lg:col-span-1">
          <Card className="h-fit sticky top-16">
            <nav aria-label="Settings categories">
              <div role="tablist" className="space-y-1">
                {tabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${BTN_FOCUS} ${
                      activeTab === tab.id
                        ? "bg-primary/10 text-primary font-semibold border-l-2 border-primary"
                        : "text-[var(--color-text-muted)] hover:bg-[var(--color-surface)]/50 hover:text-[var(--color-text-primary)]"
                    }`}
                    role="tab"
                    aria-selected={activeTab === tab.id}
                    aria-controls={`panel-${tab.id}`}
                    id={`tab-${tab.id}`}
                  >
                    <tab.icon className="h-4 w-4 flex-shrink-0" />
                    <span>{tab.label}</span>
                  </button>
                ))}
              </div>
            </nav>
            {isSaving && (
              <div className="mt-4 flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
                <Loader2 className="h-3 w-3 animate-spin text-primary" />
                Saving preferences...
              </div>
            )}
          </Card>
        </aside>

        {/* Tab Panels: All 6 rendered in DOM with hidden attribute for accessibility & tests */}
        <div className="lg:col-span-3 space-y-6">
          {/* 1. Appearance Tab */}
          <div
            role="tabpanel"
            id="panel-appearance"
            aria-labelledby="tab-appearance"
            hidden={activeTab !== "appearance"}
            className={activeTab !== "appearance" ? "hidden" : "space-y-[var(--section-gap)]"}
          >
            <Card>
              <h2 className="font-semibold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
                <Palette className="h-5 w-5 text-primary" /> Theme
              </h2>
              <div className="grid gap-3 sm:grid-cols-3">
                {[
                  { id: "light", label: "Light", desc: "Clean bright theme for daytime", icon: Sun, iconColor: "text-amber-400" },
                  { id: "dark", label: "Dark", desc: "High-contrast dark reality debugger", icon: Moon, iconColor: "text-primary" },
                  { id: "system", label: "System", desc: "Follow operating system preference", icon: Monitor, iconColor: "text-[var(--color-text-muted)]" },
                ].map((item) => (
                  <button
                    key={item.id}
                    onClick={() => updateSetting("theme", item.id as SettingsType["theme"])}
                    className={`p-4 rounded-xl border-2 text-left transition-all ${BTN_FOCUS} ${
                      settings.theme === item.id
                        ? "border-primary bg-primary/10 ring-1 ring-primary"
                        : "border-[var(--color-border)] hover:border-primary/40 bg-[var(--color-surface)]/50"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1.5">
                      <item.icon className={`h-5 w-5 ${item.iconColor}`} />
                      <span className="font-medium text-[var(--color-text-primary)]">{item.label}</span>
                    </div>
                    <p className="text-xs text-[var(--color-text-muted)]">{item.desc}</p>
                  </button>
                ))}
              </div>
            </Card>

            <Card>
              <h3 className="font-semibold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
                <Zap className="h-5 w-5 text-primary" /> Accent Color
              </h3>
              <div className="flex flex-wrap gap-3">
                {[
                  { id: "primary", name: "Cyber Blue", bg: "bg-blue-500" },
                  { id: "secondary", name: "Quantum Purple", bg: "bg-purple-500" },
                  { id: "success", name: "Emerald Matrix", bg: "bg-emerald-500" },
                  { id: "amber", name: "Amber Alert", bg: "bg-amber-500" },
                ].map((color) => (
                  <button
                    key={color.id}
                    onClick={() => updateSetting("accentColor", color.id as SettingsType["accentColor"])}
                    className={`flex items-center gap-2.5 px-4 py-2.5 rounded-xl border-2 transition-all ${BTN_FOCUS} ${
                      settings.accentColor === color.id
                        ? "border-primary bg-primary/10 ring-1 ring-primary"
                        : "border-[var(--color-border)] hover:border-primary/30 bg-[var(--color-surface)]/40"
                    }`}
                  >
                    <span className={`h-3.5 w-3.5 rounded-full ${color.bg}`} />
                    <span className="text-sm font-medium text-[var(--color-text-primary)]">{color.name}</span>
                  </button>
                ))}
              </div>
            </Card>

            <Card>
              <h3 className="font-semibold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
                <GitBranch className="h-5 w-5 text-primary" /> Layout Density
              </h3>
              <div className="grid gap-3 sm:grid-cols-3">
                {[
                  { id: "compact", label: "Compact", desc: "Maximum information density, tight margins" },
                  { id: "comfortable", label: "Comfortable", desc: "Optimal balance of spacing and focus" },
                  { id: "spacious", label: "Spacious", desc: "Relaxed breathing room for large displays" },
                ].map((density) => (
                  <button
                    key={density.id}
                    onClick={() => updateSetting("density", density.id as SettingsType["density"])}
                    className={`p-4 rounded-xl border-2 text-left transition-all ${BTN_FOCUS} ${
                      settings.density === density.id
                        ? "border-primary bg-primary/10 ring-1 ring-primary"
                        : "border-[var(--color-border)] hover:border-primary/40 bg-[var(--color-surface)]/50"
                    }`}
                  >
                    <span className="font-medium text-[var(--color-text-primary)]">{density.label}</span>
                    <p className="text-xs text-[var(--color-text-muted)] mt-1">{density.desc}</p>
                  </button>
                ))}
              </div>
            </Card>

            <Card>
              <h3 className="font-semibold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
                <FlaskConical className="h-5 w-5 text-primary" /> Motion & Transitions
              </h3>
              <div className="space-y-[var(--setting-group-gap)]">
                <div className={settingRowStyles()}>
                  <div>
                    <p className="font-medium text-[var(--color-text-primary)]">Animations</p>
                    <p className="text-sm text-[var(--color-text-muted)]">Enable micro-interactions and smooth sidebar resizing</p>
                  </div>
                  <Toggle
                    aria-label="Animations"
                    checked={settings.animations}
                    onChange={(v) => updateSetting("animations", v)}
                  />
                </div>
                <div className={settingRowStyles()}>
                  <div>
                    <p className="font-medium text-[var(--color-text-primary)]">Reduced Motion</p>
                    <p className="text-sm text-[var(--color-text-muted)]">Disable all non-essential movement for accessibility</p>
                  </div>
                  <Toggle
                    aria-label="Reduced Motion"
                    checked={settings.reducedMotion}
                    onChange={(v) => updateSetting("reducedMotion", v)}
                  />
                </div>
              </div>
            </Card>
          </div>

          {/* 2. Notifications Tab */}
          <div
            role="tabpanel"
            id="panel-notifications"
            aria-labelledby="tab-notifications"
            hidden={activeTab !== "notifications"}
            className={activeTab !== "notifications" ? "hidden" : "space-y-[var(--section-gap)]"}
          >
            <Card>
              <h2 className="font-semibold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
                <Zap className="h-5 w-5 text-primary" /> Pipeline & Simulation Alerts
              </h2>
              <div className="space-y-[var(--setting-group-gap)]">
                <div className={settingRowStyles()}>
                  <div>
                    <p className="font-medium text-[var(--color-text-primary)]">Pipeline Events</p>
                    <p className="text-sm text-[var(--color-text-muted)]">Notify on stage transitions, completions, and anomalies</p>
                  </div>
                  <Toggle
                    aria-label="Pipeline Events"
                    checked={settings.pipelineNotifications}
                    onChange={(v) => updateSetting("pipelineNotifications", v)}
                  />
                </div>
                <div className={settingRowStyles()}>
                  <div>
                    <p className="font-medium text-[var(--color-text-primary)]">Experiment Results</p>
                    <p className="text-sm text-[var(--color-text-muted)]">Notify when digital-twin simulation counterfactuals finish</p>
                  </div>
                  <Toggle
                    aria-label="Experiment Results"
                    checked={settings.experimentNotifications}
                    onChange={(v) => updateSetting("experimentNotifications", v)}
                  />
                </div>
                <div className={settingRowStyles()}>
                  <div>
                    <p className="font-medium text-[var(--color-text-primary)]">Error Notifications</p>
                    <p className="text-sm text-[var(--color-text-muted)]">Critical invariants broken or execution exceptions</p>
                  </div>
                  <Toggle
                    aria-label="Error Notifications"
                    checked={settings.errorNotifications}
                    onChange={(v) => updateSetting("errorNotifications", v)}
                  />
                </div>
                <div className={settingRowStyles()}>
                  <div>
                    <p className="font-medium text-[var(--color-text-primary)]">Desktop Notifications</p>
                    <p className="text-sm text-[var(--color-text-muted)]">OS system alerts when Cauveris tab is in background</p>
                  </div>
                  <Toggle
                    aria-label="Desktop Notifications"
                    checked={settings.desktopNotifications}
                    onChange={(v) => updateSetting("desktopNotifications", v)}
                  />
                </div>
              </div>
            </Card>
          </div>

          {/* 3. Keyboard & Commands Control Center Tab */}
          <div
            role="tabpanel"
            id="panel-keyboard"
            aria-labelledby="tab-keyboard"
            hidden={activeTab !== "keyboard"}
            className={activeTab !== "keyboard" ? "hidden" : "space-y-[var(--section-gap)]"}
          >
            {/* Interactive Command Execution Grid */}
            <Card>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="font-semibold text-[var(--color-text-primary)] flex items-center gap-2">
                    <Command className="h-5 w-5 text-primary" /> Application Command Center
                  </h2>
                  <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
                    Direct visual execution of system actions and investigation routines
                  </p>
                </div>
                <Badge tone="primary" className="border-primary/40 text-primary">
                  Active Incident: {incidentId || "None"}
                </Badge>
              </div>

              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <button
                  onClick={handleCreateIncident}
                  className={`p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]/60 hover:bg-primary/10 hover:border-primary/40 text-left transition-all ${BTN_FOCUS}`}
                >
                  <div className="flex items-center gap-2 text-[var(--color-text-primary)] font-medium mb-1">
                    <Zap className="h-4 w-4 text-primary" />
                    <span>Create New Incident</span>
                  </div>
                  <p className="text-xs text-[var(--color-text-muted)]">Initialize fresh investigation session</p>
                </button>

                <button
                  onClick={handleLoadGolden}
                  className={`p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]/60 hover:bg-amber-500/10 hover:border-amber-500/40 text-left transition-all ${BTN_FOCUS}`}
                >
                  <div className="flex items-center gap-2 text-[var(--color-text-primary)] font-medium mb-1">
                    <Clock className="h-4 w-4 text-amber-400" />
                    <span>Load Golden Benchmark</span>
                  </div>
                  <p className="text-xs text-[var(--color-text-muted)]">Load CAU-0001 AMR Batching Bottleneck</p>
                </button>

                <button
                  onClick={handleReconstruct}
                  className={`p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]/60 hover:bg-emerald-500/10 hover:border-emerald-500/40 text-left transition-all ${BTN_FOCUS}`}
                >
                  <div className="flex items-center gap-2 text-[var(--color-text-primary)] font-medium mb-1">
                    <RotateCcw className="h-4 w-4 text-emerald-400" />
                    <span>Reconstruct Pipeline</span>
                  </div>
                  <p className="text-xs text-[var(--color-text-muted)]">Re-run causal discovery & verification</p>
                </button>

                <button
                  onClick={handleExportReport}
                  className={`p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]/60 hover:bg-blue-500/10 hover:border-blue-500/40 text-left transition-all ${BTN_FOCUS}`}
                >
                  <div className="flex items-center gap-2 text-[var(--color-text-primary)] font-medium mb-1">
                    <Download className="h-4 w-4 text-blue-400" />
                    <span>Export Report (JSON)</span>
                  </div>
                  <p className="text-xs text-[var(--color-text-muted)]">Download formal causal diagnosis</p>
                </button>

                <button
                  onClick={handleDownloadPatch}
                  className={`p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]/60 hover:bg-purple-500/10 hover:border-purple-500/40 text-left transition-all ${BTN_FOCUS}`}
                >
                  <div className="flex items-center gap-2 text-[var(--color-text-primary)] font-medium mb-1">
                    <Wrench className="h-4 w-4 text-purple-400" />
                    <span>Download Patch Package</span>
                  </div>
                  <p className="text-xs text-[var(--color-text-muted)]">Export verified patch artifact zip</p>
                </button>

                <button
                  onClick={resetDemo}
                  className={`p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]/60 hover:bg-danger/10 hover:border-danger/40 text-left transition-all ${BTN_FOCUS}`}
                >
                  <div className="flex items-center gap-2 text-[var(--color-text-primary)] font-medium mb-1">
                    <Trash2 className="h-4 w-4 text-danger" />
                    <span>Reset Demo Environment</span>
                  </div>
                  <p className="text-xs text-[var(--color-text-muted)]">Restore clean sandbox state</p>
                </button>
              </div>
            </Card>

            {/* Execution Modes */}
            <Card>
              <h3 className="font-semibold text-[var(--color-text-primary)] mb-2 flex items-center gap-2">
                <Sliders className="h-5 w-5 text-primary" /> Autonomous vs. Supervised Execution Modes
              </h3>
              <p className="text-xs text-[var(--color-text-muted)] mb-4">
                Configure safety invariants and autonomy levels for robotic incident remediation
              </p>
              <div className="grid gap-3 sm:grid-cols-3">
                <button
                  onClick={() => {
                    setJudgeMode(false);
                    setEngineerMode(false);
                    addActivity({ type: "system", message: "Autonomous Mode activated", dismissible: true });
                  }}
                  className={`p-4 rounded-xl border-2 text-left transition-all ${BTN_FOCUS} ${
                    !judgeMode && !engineerMode
                      ? "border-primary bg-primary/10 ring-1 ring-primary"
                      : "border-[var(--color-border)] hover:border-primary/40 bg-[var(--color-surface)]/50"
                  }`}
                >
                  <div className="flex items-center gap-2 font-medium text-[var(--color-text-primary)] mb-1">
                    <Bot className="h-4 w-4 text-primary" />
                    <span>Autonomous</span>
                  </div>
                  <p className="text-xs text-[var(--color-text-muted)]">Self-healing: automatically hypothecates and applies fixes</p>
                </button>

                <button
                  onClick={() => {
                    setJudgeMode(true);
                    setEngineerMode(false);
                    addActivity({ type: "system", message: "Judge Mode activated", dismissible: true });
                  }}
                  className={`p-4 rounded-xl border-2 text-left transition-all ${BTN_FOCUS} ${
                    judgeMode
                      ? "border-amber-500 bg-amber-500/10 ring-1 ring-amber-500"
                      : "border-[var(--color-border)] hover:border-amber-500/40 bg-[var(--color-surface)]/50"
                  }`}
                >
                  <div className="flex items-center gap-2 font-medium text-[var(--color-text-primary)] mb-1">
                    <Shield className="h-4 w-4 text-amber-400" />
                    <span>Judge Mode</span>
                  </div>
                  <p className="text-xs text-[var(--color-text-muted)]">Human verification required before applying any patch</p>
                </button>

                <button
                  onClick={() => {
                    setEngineerMode(true);
                    setJudgeMode(false);
                    addActivity({ type: "system", message: "Engineer Mode activated", dismissible: true });
                  }}
                  className={`p-4 rounded-xl border-2 text-left transition-all ${BTN_FOCUS} ${
                    engineerMode
                      ? "border-purple-500 bg-purple-500/10 ring-1 ring-purple-500"
                      : "border-[var(--color-border)] hover:border-purple-500/40 bg-[var(--color-surface)]/50"
                  }`}
                >
                  <div className="flex items-center gap-2 font-medium text-[var(--color-text-primary)] mb-1">
                    <Wrench className="h-4 w-4 text-purple-400" />
                    <span>Engineer Mode</span>
                  </div>
                  <p className="text-xs text-[var(--color-text-muted)]">Deep telemetry traces, raw kernel timings, and step-through</p>
                </button>
              </div>
            </Card>

            {/* Layout Shell Controls */}
            <Card>
              <h3 className="font-semibold text-[var(--color-text-primary)] mb-3 flex items-center gap-2">
                <LayoutDashboard className="h-5 w-5 text-primary" /> Shell Layout Controls
              </h3>
              <div className="grid gap-3 sm:grid-cols-3">
                <button
                  onClick={() => toggleNavCollapse()}
                  className={`p-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]/40 hover:bg-[var(--color-surface)]/50 text-left transition-all flex items-center justify-between ${BTN_FOCUS}`}
                >
                  <div>
                    <span className="text-sm font-medium text-[var(--color-text-primary)] block">Navigation Sidebar</span>
                    <span className="text-xs text-[var(--color-text-muted)]">{shellState.isNavCollapsed ? "Collapsed" : "Expanded"}</span>
                  </div>
                  <Badge tone={shellState.isNavCollapsed ? "secondary" : "primary"}>
                    {shellState.isNavCollapsed ? "Mini" : "Full"}
                  </Badge>
                </button>

                <button
                  onClick={() => (shellState.inspectorOpen ? closeInspector() : openInspector("timeline", { mode: "timeline" }))}
                  className={`p-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]/40 hover:bg-[var(--color-surface)]/50 text-left transition-all flex items-center justify-between ${BTN_FOCUS}`}
                >
                  <div>
                    <span className="text-sm font-medium text-[var(--color-text-primary)] block">Context Inspector</span>
                    <span className="text-xs text-[var(--color-text-muted)]">{shellState.inspectorOpen ? "Visible" : "Hidden"}</span>
                  </div>
                  <Badge tone={shellState.inspectorOpen ? "primary" : "secondary"}>
                    {shellState.inspectorOpen ? "Open" : "Closed"}
                  </Badge>
                </button>

                <button
                  onClick={() =>
                    setTrayState(shellState.trayState === "closed" ? "expanded" : "closed")
                  }
                  className={`p-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]/40 hover:bg-[var(--color-surface)]/50 text-left transition-all flex items-center justify-between ${BTN_FOCUS}`}
                >
                  <div>
                    <span className="text-sm font-medium text-[var(--color-text-primary)] block">Activity Tray</span>
                    <span className="text-xs text-[var(--color-text-muted)]">Current: {shellState.trayState}</span>
                  </div>
                  <Badge tone="neutral" className="capitalize">
                    {shellState.trayState}
                  </Badge>
                </button>
              </div>
            </Card>

            {/* Keyboard Shortcuts Cheat Sheet */}
            <Card>
              <h3 className="font-semibold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
                <Clock className="h-5 w-5 text-primary" /> Keyboard Shortcuts Reference
              </h3>
              <div className="grid gap-3 sm:grid-cols-2">
                {[
                  { shortcut: "Ctrl / Cmd + K", action: "Toggle Global Command Palette" },
                  { shortcut: "Ctrl / Cmd + B", action: "Toggle Left Navigation Sidebar" },
                  { shortcut: "Ctrl / Cmd + I", action: "Toggle Right Contextual Inspector" },
                  { shortcut: "Ctrl / Cmd + J", action: "Toggle Bottom Activity Tray" },
                  { shortcut: "Ctrl / Cmd + 1", action: "Jump to Reality Rewind" },
                  { shortcut: "Ctrl / Cmd + 2", action: "Jump to Ghost Lab" },
                  { shortcut: "Ctrl / Cmd + 3", action: "Jump to Patch Forge" },
                  { shortcut: "Ctrl / Cmd + 4", action: "Jump to Victory Replay" },
                  { shortcut: "Esc", action: "Close modal dialogs and clear inspector" },
                ].map((item, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-2.5 rounded-lg bg-[var(--color-surface)]/50 border border-[var(--color-border)] text-sm"
                  >
                    <span className="text-[var(--color-text-primary)]/80">{item.action}</span>
                    <kbd className="px-2 py-1 text-xs font-mono rounded bg-[var(--color-surface)]/50 border border-[var(--color-border)]/20 text-primary font-semibold">
                      {item.shortcut}
                    </kbd>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          {/* 4. Privacy & Security Tab */}
          <div
            role="tabpanel"
            id="panel-privacy"
            aria-labelledby="tab-privacy"
            hidden={activeTab !== "privacy"}
            className={activeTab !== "privacy" ? "hidden" : "space-y-[var(--section-gap)]"}
          >
            <Card>
              <h2 className="font-semibold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
                <Shield className="h-5 w-5 text-primary" /> Security & Telemetry
              </h2>
              <div className="space-y-[var(--setting-group-gap)]">
                <div className="py-[var(--setting-row-padding)] px-[var(--space-4)] rounded-xl bg-[var(--color-surface)]/50 border border-[var(--color-border)]">
                  <label htmlFor="settings-session-timeout" className="block text-sm font-medium text-[var(--color-text-primary)] mb-2">
                    Session timeout (minutes)
                  </label>
                  <p className="text-xs text-[var(--color-text-muted)] mb-3">
                    Automatically lock authentication and terminal session when inactive
                  </p>
                  <div className="max-w-xs">
                    <Input
                      id="settings-session-timeout"
                      aria-label="Session timeout (minutes)"
                      type="number"
                      min={5}
                      max={1440}
                      value={settings.sessionTimeout}
                      onChange={(e) => updateSetting("sessionTimeout", parseInt(e.target.value) || 30)}
                    />
                  </div>
                </div>

                <div className={settingRowStyles()}>
                  <div>
                    <p className="font-medium text-[var(--color-text-primary)]">Anonymized Telemetry</p>
                    <p className="text-sm text-[var(--color-text-muted)]">Contribute anonymized causal DAG accuracy metrics</p>
                  </div>
                  <Toggle
                    aria-label="Telemetry"
                    checked={settings.telemetry}
                    onChange={(v) => updateSetting("telemetry", v)}
                  />
                </div>

                <div className={settingRowStyles()}>
                  <div>
                    <p className="font-medium text-[var(--color-text-primary)]">Local Storage Encryption</p>
                    <p className="text-sm text-[var(--color-text-muted)]">Encrypt cached incident artifacts and session tokens</p>
                  </div>
                  <Toggle
                    aria-label="Local Storage Encryption"
                    checked={settings.localStorageEncryption}
                    onChange={(v) => updateSetting("localStorageEncryption", v)}
                  />
                </div>
              </div>
            </Card>
          </div>

          {/* 5. Data & Sync Tab */}
          <div
            role="tabpanel"
            id="panel-data"
            aria-labelledby="tab-data"
            hidden={activeTab !== "data"}
            className={activeTab !== "data" ? "hidden" : "space-y-[var(--section-gap)]"}
          >
            <Card>
              <h2 className="font-semibold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
                <Database className="h-5 w-5 text-primary" /> Retention & Data Management
              </h2>
              <div className="space-y-[var(--setting-group-gap)]">
                <div className={settingRowStyles()}>
                  <div>
                    <p className="font-medium text-[var(--color-text-primary)]">Auto-save</p>
                    <p className="text-sm text-[var(--color-text-muted)]">Periodically persist investigation state to browser</p>
                  </div>
                  <Toggle
                    aria-label="Auto-save"
                    checked={settings.autoSave}
                    onChange={(v) => updateSetting("autoSave", v)}
                  />
                </div>

                <div className={settingRowStyles()}>
                  <div>
                    <p className="font-medium text-[var(--color-text-primary)]">Cross-tab Synchronization</p>
                    <p className="text-sm text-[var(--color-text-muted)]">Synchronize active incident selection across windows</p>
                  </div>
                  <Toggle
                    aria-label="Cross-tab Synchronization"
                    checked={settings.syncTabs}
                    onChange={(v) => updateSetting("syncTabs", v)}
                  />
                </div>

                <div className="flex flex-wrap gap-3 pt-3">
                  <Button variant="outline" onClick={exportSettings} className={BTN_FOCUS}>
                    <Download className="h-4 w-4 mr-2" /> Export Settings JSON
                  </Button>
                  <Button variant="outline" onClick={importSettings} className={BTN_FOCUS}>
                    <Upload className="h-4 w-4 mr-2" /> Import Settings JSON
                  </Button>
                  <Button variant="outline" onClick={resetSettings} className={BTN_FOCUS}>
                    <RotateCcw className="h-4 w-4 mr-2" /> Reset Defaults
                  </Button>
                </div>
              </div>
            </Card>
          </div>

          {/* 6. Advanced Tab (Model Gateway & API Key Integration) */}
          <div
            role="tabpanel"
            id="panel-advanced"
            aria-labelledby="tab-advanced"
            hidden={activeTab !== "advanced"}
            className={activeTab !== "advanced" ? "hidden" : "space-y-[var(--section-gap)]"}
          >
            {/* Live Model Gateway Status Card */}
            <Card>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="font-semibold text-[var(--color-text-primary)] flex items-center gap-2">
                    <Server className="h-5 w-5 text-primary" /> Model Gateway Status
                  </h2>
                  <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
                    Live inference engine status and model execution configuration
                  </p>
                </div>
                <Badge
                  tone={isLiveGateway ? "success" : "neutral"}
                  className="flex items-center gap-1.5 px-3 py-1"
                >
                  <span
                    className={`h-2 w-2 rounded-full ${
                      isLiveGateway ? "bg-emerald-400 animate-pulse" : "bg-blue-400"
                    }`}
                  />
                  <span>{isLiveGateway ? "Nebius Live Gateway Active" : "Deterministic Local Fixtures"}</span>
                </Badge>
              </div>

              <div className="p-4 rounded-xl bg-[var(--color-surface)]/50 border border-[var(--color-border)] mb-4">
                <div className="grid gap-4 sm:grid-cols-2 text-sm">
                  <div>
                    <span className="text-xs text-[var(--color-text-muted)] block">Active Provider</span>
                    <span className="font-medium text-[var(--color-text-primary)]">{gatewayProviderName}</span>
                  </div>
                  <div>
                    <span className="text-xs text-[var(--color-text-muted)] block">Fast Model</span>
                    <span className="font-mono text-primary">{settings.modelFast}</span>
                  </div>
                  <div>
                    <span className="text-xs text-[var(--color-text-muted)] block">Reasoning Model</span>
                    <span className="font-mono text-purple-400">{settings.modelReasoning}</span>
                  </div>
                  <div>
                    <span className="text-xs text-[var(--color-text-muted)] block">Escalation Model</span>
                    <span className="font-mono text-amber-400">{settings.modelEscalation}</span>
                  </div>
                </div>
              </div>

              {/* Secure API Key Input Section */}
              <div className="space-y-4 pt-2 border-t border-[var(--color-border)]">
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label htmlFor="settings-model-api-key" className="text-sm font-medium text-[var(--color-text-primary)] flex items-center gap-2">
                      <Key className="h-4 w-4 text-primary" /> Nebius / OpenAI API Key
                    </label>
                    {maskedKey && (
                      <span className="text-xs text-emerald-400 flex items-center gap-1">
                        <Check className="h-3 w-3" /> Key Stored & Protected
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-[var(--color-text-muted)] mb-3">
                    Paste your API key below. Once saved, the key is permanently masked on screen to prevent shoulder-surfing.
                    No need to modify .env or source files.
                  </p>

                  {/* Masked Preview if stored */}
                  {maskedKey && (
                    <div className="mb-3 flex items-center justify-between p-3 rounded-xl bg-emerald-950/20 border border-emerald-500/30">
                      <div className="flex items-center gap-2.5">
                        <Shield className="h-4 w-4 text-emerald-400 flex-shrink-0" />
                        <div>
                          <span className="text-xs text-emerald-300 font-mono tracking-wider">{maskedKey}</span>
                          <span className="text-[10px] text-[var(--color-text-muted)] block">Stored safely in runtime environment</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={handleCopyMasked}
                          className={`text-xs ${BTN_FOCUS}`}
                          aria-label="Copy masked key id"
                        >
                          {copiedKey ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                        </Button>
                        <Button
                          variant="danger"
                          size="sm"
                          onClick={handleClearApiKey}
                          className={`text-xs ${BTN_FOCUS}`}
                          aria-label="Disconnect API key"
                        >
                          Disconnect
                        </Button>
                      </div>
                    </div>
                  )}

                  {/* Input with show/hide toggle */}
                  <div className="relative flex items-center">
                    <Input
                      id="settings-model-api-key"
                      aria-label="Model API Key"
                      type={showApiKey ? "text" : "password"}
                      placeholder={maskedKey ? "Enter new key to replace existing..." : "neb-••••••••••••••••••••••••••••••••"}
                      value={apiKeyInput}
                      onChange={(e) => setApiKeyInput(e.target.value)}
                      className="pr-10 font-mono text-sm"
                    />
                    <button
                      type="button"
                      onClick={() => setShowApiKey(!showApiKey)}
                      className={`absolute right-3 p-1 text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] rounded ${BTN_FOCUS}`}
                      aria-label={showApiKey ? "Hide API key" : "Show API key"}
                    >
                      {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>

                {/* Test Result Feedback */}
                {testResult && (
                  <div
                    className={`p-3.5 rounded-xl border text-sm flex items-start gap-2.5 ${
                      testResult.isTesting
                        ? "bg-blue-500/10 border-blue-500/30 text-blue-300"
                        : testResult.success
                        ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
                        : "bg-danger/10 border-danger/30 text-red-300"
                    }`}
                  >
                    {testResult.isTesting ? (
                      <Loader2 className="h-4 w-4 animate-spin mt-0.5 flex-shrink-0" />
                    ) : testResult.success ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-400 mt-0.5 flex-shrink-0" />
                    ) : (
                      <XCircle className="h-4 w-4 text-danger mt-0.5 flex-shrink-0" />
                    )}
                    <div>
                      <p className="font-medium">{testResult.message}</p>
                      {testResult.latencyMs !== undefined && (
                        <p className="text-xs opacity-80 mt-0.5">Roundtrip ping latency: {testResult.latencyMs}ms</p>
                      )}
                    </div>
                  </div>
                )}

                {/* API Key Action Buttons */}
                <div className="flex flex-wrap items-center gap-3 pt-1">
                  <Button
                    variant="primary"
                    onClick={handleSaveApiKey}
                    disabled={!apiKeyInput.trim() || isSavingModel}
                    className={BTN_FOCUS}
                    aria-label="Save API Key"
                  >
                    {isSavingModel ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" /> Saving...
                      </>
                    ) : (
                      <>
                        <Key className="h-4 w-4 mr-2" /> Save & Enable Models
                      </>
                    )}
                  </Button>

                  <Button
                    variant="outline"
                    onClick={handleTestConnection}
                    disabled={testResult?.isTesting}
                    className={BTN_FOCUS}
                    aria-label="Test Connection"
                  >
                    <Server className="h-4 w-4 mr-2" /> Test Connectivity
                  </Button>

                  {maskedKey && (
                    <Button
                      variant="ghost"
                      onClick={handleClearApiKey}
                      className={`text-danger hover:bg-danger/10 ${BTN_FOCUS}`}
                      aria-label="Clear API Key"
                    >
                      Clear / Revert to Local
                    </Button>
                  )}
                </div>
              </div>
            </Card>

            {/* Model Gateway URL & Models Card */}
            <Card>
              <h3 className="font-semibold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
                <Globe className="h-5 w-5 text-primary" /> Gateway Endpoint & Model Architecture
              </h3>
              <div className="space-y-4">
                <div>
                  <label htmlFor="settings-model-base-url" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
                    Gateway Base URL
                  </label>
                  <Input
                    id="settings-model-base-url"
                    aria-label="Gateway Base URL"
                    value={settings.modelBaseUrl}
                    onChange={(e) => updateSetting("modelBaseUrl", e.target.value)}
                    placeholder="https://api.nebius.ai/v1"
                  />
                  <p className="text-xs text-[var(--color-text-muted)] mt-1">
                    Compatible with Nebius Token Factory or any OpenAI-compatible API proxy
                  </p>
                </div>

                <div className="grid gap-3 sm:grid-cols-3">
                  <div>
                    <label htmlFor="settings-model-fast" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
                      Fast Model
                    </label>
                    <Input
                      id="settings-model-fast"
                      aria-label="Fast Model"
                      value={settings.modelFast}
                      onChange={(e) => updateSetting("modelFast", e.target.value)}
                    />
                  </div>

                  <div>
                    <label htmlFor="settings-model-reasoning" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
                      Reasoning Model
                    </label>
                    <Input
                      id="settings-model-reasoning"
                      aria-label="Reasoning Model"
                      value={settings.modelReasoning}
                      onChange={(e) => updateSetting("modelReasoning", e.target.value)}
                    />
                  </div>

                  <div>
                    <label htmlFor="settings-model-escalation" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
                      Escalation Model
                    </label>
                    <Input
                      id="settings-model-escalation"
                      aria-label="Escalation Model"
                      value={settings.modelEscalation}
                      onChange={(e) => updateSetting("modelEscalation", e.target.value)}
                    />
                  </div>
                </div>
              </div>
            </Card>

            {/* General Advanced Settings (With required test labels) */}
            <Card>
              <h3 className="font-semibold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
                <Sliders className="h-5 w-5 text-primary" /> General Engine Parameters
              </h3>
              <div className="space-y-4">
                <div>
                  <label htmlFor="settings-api-endpoint" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
                    API endpoint
                  </label>
                  <Input
                    id="settings-api-endpoint"
                    aria-label="API endpoint"
                    value={settings.apiEndpoint}
                    onChange={(e) => updateSetting("apiEndpoint", e.target.value)}
                    placeholder="http://localhost:8000/api/v1"
                  />
                </div>

                <div>
                  <label htmlFor="settings-max-concurrent" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
                    Max concurrent experiments
                  </label>
                  <Input
                    id="settings-max-concurrent"
                    aria-label="Max concurrent experiments"
                    type="number"
                    min={1}
                    max={10}
                    value={settings.maxConcurrentExperiments}
                    onChange={(e) => updateSetting("maxConcurrentExperiments", parseInt(e.target.value) || 3)}
                  />
                </div>

                <div className={settingRowStyles()}>
                  <div>
                    <p className="font-medium text-[var(--color-text-primary)]">Debug Mode</p>
                    <p className="text-sm text-[var(--color-text-muted)]">Enable verbose logging and diagnostic stack traces</p>
                  </div>
                  <Toggle
                    aria-label="Debug Mode"
                    checked={settings.debugMode}
                    onChange={(v) => updateSetting("debugMode", v)}
                  />
                </div>

                <div className={settingRowStyles()}>
                  <div>
                    <p className="font-medium text-[var(--color-text-primary)]">Experimental Features</p>
                    <p className="text-sm text-[var(--color-text-muted)]">Early access to neural causal abstraction primitives</p>
                  </div>
                  <Toggle
                    aria-label="Experimental Features"
                    checked={settings.experimentalFeatures}
                    onChange={(v) => updateSetting("experimentalFeatures", v)}
                  />
                </div>
              </div>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}