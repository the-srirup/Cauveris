"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { PageHeader, Card, Badge, Button, Input, Toggle, Slider } from "@/components/ui";
import { AuthGate } from "@/components/AuthGate";
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
  RotateCcw,
  Clock,
  Settings,
  Loader2,
  Key,
  Eye,
  EyeOff,
  Check,
  Server,
  Command,
  CheckCircle2,
  XCircle,
  Copy,
  Sliders,
  LogOut,
  User,
  GitBranch,
  FileCode,
  Download,
  Upload,
} from "lucide-react";
import { api, type IngestCapabilities } from "@/lib/api";
import { useActiveIncident } from "@/lib/useIncident";
import { useShell } from "@/lib/useShell";
import { useAuthStore } from "@/lib/auth";
import { APP_VERSION_TAG, APP_FULL_VERSION } from "@/lib/version";

const BTN_FOCUS = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]";

const settingRowStyles = "flex items-center justify-between py-3.5 px-4 rounded-[var(--radius-md)] bg-[var(--color-canvas-subtle)]/50 border border-[var(--color-border-default)] transition-all duration-150 hover:bg-[var(--color-canvas-subtle)]/70";

export type SettingsType = {
  theme: "light" | "dark" | "system";
  animations: boolean;
  reducedMotion: boolean;
  debugMode: boolean;
  maxConcurrentExperiments: number;
  apiEndpoint: string;
  modelBaseUrl: string;
  modelFast: string;
  modelReasoning: string;
  modelEscalation: string;
};

const defaultSettings: SettingsType = {
  theme: "dark",
  animations: true,
  reducedMotion: false,
  debugMode: false,
  maxConcurrentExperiments: 3,
  apiEndpoint: "http://localhost:8000/api/v1",
  modelBaseUrl: "https://api.tokenfactory.nebius.com/v1",
  modelFast: "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
  modelReasoning: "nvidia/Nemotron-3_5-Lightning",
  modelEscalation: "nvidia/Nemotron-3-Ultra-550b-a55b",
};

function SettingsContent() {
  const { addActivity, setIncidentContext } = useShell();
  const { incidentId, judgeMode, setJudgeMode, engineerMode, setEngineerMode, loadIncident } = useActiveIncident();
  const { user: authUser, isAuthenticated, isLoading: authLoading, logout } = useAuthStore();
  const router = useRouter();

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated && typeof window !== "undefined") {
      router.push("/login?redirect=/settings");
    }
  }, [isAuthenticated, authLoading, router]);

  const [activeTab, setActiveTab] = useState<string>("appearance");
  const [isSaving, setIsSaving] = useState(false);

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
  const [capabilities, setCapabilities] = useState<IngestCapabilities | null>(null);
  const [capabilitiesLoading, setCapabilitiesLoading] = useState(false);

  useEffect(() => {
    if (activeTab === "intake" && !capabilities) {
      setCapabilitiesLoading(true);
      api.getIngestCapabilities()
        .then((data) => setCapabilities(data))
        .catch((err) => console.warn("Failed to load intake capabilities", err))
        .finally(() => setCapabilitiesLoading(false));
    }
  }, [activeTab, capabilities]);

  // Initialize settings from localStorage or defaults
  const [settings, setSettings] = useState<SettingsType>(() => {
    if (typeof window !== "undefined") {
      try {
        const saved = localStorage.getItem("cauveris-settings");
        if (saved) {
          return { ...defaultSettings, ...JSON.parse(saved) };
        }
      } catch {
        // Fall back to defaults
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

  const refreshModelHealth = useCallback(async () => {
    try {
      const health = await api.getModelHealth();
      setMaskedKey(health.masked_key || "");
      setIsLiveGateway(Boolean(health.nebius_configured));
      setGatewayProviderName(health.provider || "Deterministic Local Fixtures");
      setSettings((prev) => ({ ...prev, apiEndpoint: api.getBaseUrl() || prev.apiEndpoint }));
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
      setMaskedKey("");
      setIsLiveGateway(false);
      setGatewayProviderName("Deterministic Local Fixtures (Offline Safe)");
    }
  }, []);

  useEffect(() => {
    refreshModelHealth();
  }, [refreshModelHealth]);

  useEffect(() => {
    if (incidentId) {
      setIncidentContext({
        id: incidentId,
        title: "Settings & System Status",
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
    if (!incidentId) return;
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
    if (!incidentId) return;
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
    if (!incidentId) return;
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

  // 7 Settings categories corresponding to accessible tabs
  const tabs = [
    { id: "appearance", label: "Display & Theme", icon: Palette },
    { id: "notifications", label: "Engine & Modes", icon: Zap },
    { id: "keyboard", label: "Commands & Shortcuts", icon: Command },
    { id: "privacy", label: "Identity & Security", icon: Shield },
    { id: "data", label: "Workspace & Storage", icon: Database },
    { id: "advanced", label: "Model Gateway", icon: Server },
    { id: "intake", label: "Universal Intake", icon: Globe },
  ];

  if (authLoading) {
    return (
      <div className="flex flex-col gap-8 max-w-7xl mx-auto w-full min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-[var(--color-accent-fg)]" />
        <p className="text-[var(--color-fg-muted)]">Loading system configuration...</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="flex flex-col gap-8 max-w-7xl mx-auto w-full min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-[var(--color-accent-fg)]" />
        <p className="text-[var(--color-fg-muted)]">Redirecting to login...</p>
      </div>
    );
  }

  return (
    <div className="w-full space-y-5">
      <PageHeader
        title="System Status & Preferences"
        ariaLabel="Settings"
        subtitle="Model inference gateway, causal verification engine parameters, and runtime security"
        breadcrumbs={[{ label: "Overview", href: "/" }, { label: "System Status" }]}
      />

      <div className="grid gap-5 lg:grid-cols-4">
        {/* Navigation Sidebar */}
        <aside className="lg:col-span-1">
          <Card className="h-fit sticky top-16">
            <nav aria-label="Settings categories">
              <div role="tablist" className="space-y-1">
                {tabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-[var(--radius-md)] text-sm font-medium transition-all ${BTN_FOCUS} ${
                      activeTab === tab.id
                        ? "bg-[var(--color-accent-muted)]/10 text-[var(--color-accent-fg)] font-semibold border-l-2 border-[var(--color-accent-fg)]"
                        : "text-[var(--color-fg-muted)] hover:bg-[var(--color-canvas-subtle)]/50 hover:text-[var(--color-fg-default)]"
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
              <div className="mt-4 flex items-center gap-2 text-xs text-[var(--color-fg-muted)]">
                <Loader2 className="h-3 w-3 animate-spin text-[var(--color-accent-fg)]" />
                Saving preferences...
              </div>
            )}
          </Card>
        </aside>

        {/* Tab Panels: All 7 rendered in DOM with hidden attribute for accessibility & tests */}
        <div className="lg:col-span-3 space-y-5">
          {/* 1. Appearance Tab */}
          <div
            role="tabpanel"
            id="panel-appearance"
            aria-labelledby="tab-appearance"
            hidden={activeTab !== "appearance"}
            className={activeTab !== "appearance" ? "hidden" : "space-y-5"}
          >
            <Card>
              <h2 className="font-semibold text-[var(--color-fg-default)] mb-4 flex items-center gap-2">
                <Palette className="h-5 w-5 text-[var(--color-accent-fg)]" /> Theme Mode
              </h2>
              <div className="grid gap-3 sm:grid-cols-3">
                {[
                  { id: "light", label: "Light", desc: "Clean bright theme for daytime environments", icon: Sun, iconColor: "text-amber-400" },
                  { id: "dark", label: "Dark", desc: "High-contrast dark reality debugger theme", icon: Moon, iconColor: "text-[var(--color-accent-fg)]" },
                  { id: "system", label: "System", desc: "Follow operating system theme preference", icon: Monitor, iconColor: "text-[var(--color-fg-muted)]" },
                ].map((item) => (
                  <button
                    key={item.id}
                    onClick={() => updateSetting("theme", item.id as SettingsType["theme"])}
                    className={`p-4 rounded-[var(--radius-lg)] border-2 text-left transition-all ${BTN_FOCUS} ${
                      settings.theme === item.id
                        ? "border-[var(--color-accent-fg)] bg-[var(--color-accent-muted)]/10 ring-1 ring-[var(--color-accent-fg)]"
                        : "border-[var(--color-border-default)] hover:border-[var(--color-accent-muted)]/40 bg-[var(--color-canvas-subtle)]/50"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1.5">
                      <item.icon className={`h-5 w-5 ${item.iconColor}`} />
                      <span className="font-medium text-[var(--color-fg-default)]">{item.label}</span>
                    </div>
                    <p className="text-xs text-[var(--color-fg-muted)]">{item.desc}</p>
                  </button>
                ))}
              </div>
            </Card>

            <Card>
              <h3 className="font-semibold text-[var(--color-fg-default)] mb-4 flex items-center gap-2">
                <Sliders className="h-5 w-5 text-[var(--color-accent-fg)]" /> Motion & Accessibility
              </h3>
              <div className="space-y-3">
                <div className={settingRowStyles}>
                  <div>
                    <p className="font-medium text-[var(--color-fg-default)]">Animations</p>
                    <p className="text-sm text-[var(--color-fg-muted)]">Enable micro-interactions and smooth UI transitions</p>
                  </div>
                  <Toggle
                    aria-label="Animations"
                    checked={settings.animations}
                    onChange={(v) => updateSetting("animations", v)}
                  />
                </div>
                <div className={settingRowStyles}>
                  <div>
                    <p className="font-medium text-[var(--color-fg-default)]">Reduced Motion</p>
                    <p className="text-sm text-[var(--color-fg-muted)]">Disable non-essential motion effects for accessibility compliance</p>
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

          {/* 2. Notifications / Engine Tab */}
          <div
            role="tabpanel"
            id="panel-notifications"
            aria-labelledby="tab-notifications"
            hidden={activeTab !== "notifications"}
            className={activeTab !== "notifications" ? "hidden" : "space-y-5"}
          >
            <Card>
              <h2 className="font-semibold text-[var(--color-fg-default)] mb-4 flex items-center gap-2">
                <Zap className="h-5 w-5 text-[var(--color-accent-fg)]" /> Causal Verification & Engine Modes
              </h2>
              <div className="space-y-3">
                <div className={settingRowStyles}>
                  <div className="pr-4">
                    <div className="flex items-center gap-2">
                      <p className="font-medium text-[var(--color-fg-default)]">Judge Mode</p>
                      <Badge tone={judgeMode ? "primary" : "neutral"} className="text-[10px]">
                        {judgeMode ? "Enforcing Invariant Proofs" : "Disabled"}
                      </Badge>
                    </div>
                    <p className="text-sm text-[var(--color-fg-muted)] mt-0.5">
                      Enforces formal mathematical verification of causal claims. Automatically rejects unverified repair patches and requires counterfactual ablation proofs.
                    </p>
                  </div>
                  <Toggle
                    aria-label="Judge Mode"
                    checked={judgeMode}
                    onChange={(v) => setJudgeMode(v)}
                  />
                </div>

                <div className={settingRowStyles}>
                  <div className="pr-4">
                    <div className="flex items-center gap-2">
                      <p className="font-medium text-[var(--color-fg-default)]">Engineer Mode</p>
                      <Badge tone={engineerMode ? "success" : "neutral"} className="text-[10px]">
                        {engineerMode ? "Raw Signal Diagnostic" : "Standard View"}
                      </Badge>
                    </div>
                    <p className="text-sm text-[var(--color-fg-muted)] mt-0.5">
                      Direct microsecond diagnostic telemetry. Exposes raw node logs, micro-second ROS topic frames, and kernel memory metrics across timeline and holographic views.
                    </p>
                  </div>
                  <Toggle
                    aria-label="Engineer Mode"
                    checked={engineerMode}
                    onChange={(v) => setEngineerMode(v)}
                  />
                </div>
              </div>
            </Card>

            <Card>
              <h3 className="font-semibold text-[var(--color-fg-default)] mb-4 flex items-center gap-2">
                <Bell className="h-5 w-5 text-[var(--color-accent-fg)]" /> Runtime Invariant Alerts
              </h3>
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="p-3.5 rounded-[var(--radius-md)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/40">
                  <span className="text-xs font-mono font-bold text-[var(--color-fg-default)] block mb-1">Critical Halts</span>
                  <p className="text-xs text-[var(--color-fg-muted)]">Immediate toast alert on safety invariant violation or emergency stop detection.</p>
                </div>
                <div className="p-3.5 rounded-[var(--radius-md)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/40">
                  <span className="text-xs font-mono font-bold text-[var(--color-fg-default)] block mb-1">Verification Refusal</span>
                  <p className="text-xs text-[var(--color-fg-muted)]">Alerts if an experimental intervention fails to reproduce or falsify the target claim.</p>
                </div>
                <div className="p-3.5 rounded-[var(--radius-md)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/40">
                  <span className="text-xs font-mono font-bold text-[var(--color-fg-default)] block mb-1">Gateway Fallback</span>
                  <p className="text-xs text-[var(--color-fg-muted)]">Notifies when token quotas or connection drops trigger local fixture playback.</p>
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
            className={activeTab !== "keyboard" ? "hidden" : "space-y-5"}
          >
            <Card>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="font-semibold text-[var(--color-fg-default)] flex items-center gap-2">
                    <Command className="h-5 w-5 text-[var(--color-accent-fg)]" /> Interactive Command Center
                  </h2>
                  <p className="text-xs text-[var(--color-fg-muted)] mt-0.5">
                    Direct execution of system routines on the active incident workspace
                  </p>
                </div>
                <Badge tone="primary" className="border-[var(--color-accent-muted)]/40 text-[var(--color-accent-fg)]">
                  Active Incident: {incidentId || "None"}
                </Badge>
              </div>

              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <button
                  onClick={handleLoadGolden}
                  className={`p-4 rounded-[var(--radius-lg)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/60 hover:bg-[var(--color-accent-muted)]/10 hover:border-[var(--color-accent-muted)]/40 text-left transition-all ${BTN_FOCUS}`}
                >
                  <div className="flex items-center gap-2 text-[var(--color-fg-default)] font-medium mb-1">
                    <Clock className="h-4 w-4 text-[var(--color-accent-fg)]" />
                    <span>Load Benchmark</span>
                  </div>
                  <p className="text-xs text-[var(--color-fg-muted)]">Load CAU-0001 Golden Incident</p>
                </button>

                <button
                  onClick={handleReconstruct}
                  disabled={!incidentId}
                  className={`p-4 rounded-[var(--radius-lg)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/60 hover:bg-[var(--color-accent-muted)]/10 hover:border-[var(--color-accent-muted)]/40 text-left transition-all disabled:opacity-50 ${BTN_FOCUS}`}
                >
                  <div className="flex items-center gap-2 text-[var(--color-fg-default)] font-medium mb-1">
                    <RotateCcw className="h-4 w-4 text-[var(--color-accent-fg)]" />
                    <span>Reconstruct</span>
                  </div>
                  <p className="text-xs text-[var(--color-fg-muted)]">Re-execute causal discovery</p>
                </button>

                <button
                  onClick={handleExportReport}
                  disabled={!incidentId}
                  className={`p-4 rounded-[var(--radius-lg)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/60 hover:bg-[var(--color-accent-muted)]/10 hover:border-[var(--color-accent-muted)]/40 text-left transition-all disabled:opacity-50 ${BTN_FOCUS}`}
                >
                  <div className="flex items-center gap-2 text-[var(--color-fg-default)] font-medium mb-1">
                    <Download className="h-4 w-4 text-[var(--color-accent-fg)]" />
                    <span>Export Report</span>
                  </div>
                  <p className="text-xs text-[var(--color-fg-muted)]">Download incident report JSON</p>
                </button>

                <button
                  onClick={handleDownloadPatch}
                  disabled={!incidentId}
                  className={`p-4 rounded-[var(--radius-lg)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/60 hover:bg-[var(--color-accent-muted)]/10 hover:border-[var(--color-accent-muted)]/40 text-left transition-all disabled:opacity-50 ${BTN_FOCUS}`}
                >
                  <div className="flex items-center gap-2 text-[var(--color-fg-default)] font-medium mb-1">
                    <FileCode className="h-4 w-4 text-[var(--color-accent-fg)]" />
                    <span>Download Patch</span>
                  </div>
                  <p className="text-xs text-[var(--color-fg-muted)]">Get verified ZIP patch bundle</p>
                </button>
              </div>
            </Card>

            <Card>
              <h3 className="font-semibold text-[var(--color-fg-default)] mb-4 flex items-center gap-2">
                <Command className="h-5 w-5 text-[var(--color-accent-fg)]" /> Global Keyboard Shortcuts
              </h3>
              <div className="grid gap-2 sm:grid-cols-2 text-xs font-mono">
                <div className="flex items-center justify-between p-2.5 rounded bg-[var(--color-canvas-subtle)]/50 border border-[var(--color-border-default)]">
                  <span className="text-[var(--color-fg-muted)]">Command Palette</span>
                  <kbd className="px-2 py-0.5 rounded bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)] font-bold">⌘ / Ctrl + K</kbd>
                </div>
                <div className="flex items-center justify-between p-2.5 rounded bg-[var(--color-canvas-subtle)]/50 border border-[var(--color-border-default)]">
                  <span className="text-[var(--color-fg-muted)]">Toggle Right Inspector</span>
                  <kbd className="px-2 py-0.5 rounded bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)] font-bold">⌘ / Ctrl + I</kbd>
                </div>
                <div className="flex items-center justify-between p-2.5 rounded bg-[var(--color-canvas-subtle)]/50 border border-[var(--color-border-default)]">
                  <span className="text-[var(--color-fg-muted)]">Toggle Left Sidebar</span>
                  <kbd className="px-2 py-0.5 rounded bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)] font-bold">⌘ / Ctrl + B</kbd>
                </div>
                <div className="flex items-center justify-between p-2.5 rounded bg-[var(--color-canvas-subtle)]/50 border border-[var(--color-border-default)]">
                  <span className="text-[var(--color-fg-muted)]">Play / Pause Timeline</span>
                  <kbd className="px-2 py-0.5 rounded bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)] font-bold">Space</kbd>
                </div>
                <div className="flex items-center justify-between p-2.5 rounded bg-[var(--color-canvas-subtle)]/50 border border-[var(--color-border-default)]">
                  <span className="text-[var(--color-fg-muted)]">Step Timeline Forward/Back</span>
                  <kbd className="px-2 py-0.5 rounded bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)] font-bold">← / →</kbd>
                </div>
                <div className="flex items-center justify-between p-2.5 rounded bg-[var(--color-canvas-subtle)]/50 border border-[var(--color-border-default)]">
                  <span className="text-[var(--color-fg-muted)]">Jump to Failure</span>
                  <kbd className="px-2 py-0.5 rounded bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)] font-bold">F</kbd>
                </div>
              </div>
            </Card>
          </div>

          {/* 4. Privacy & Security Tab */}
          <div
            role="tabpanel"
            id="panel-privacy"
            aria-labelledby="tab-privacy"
            hidden={activeTab !== "privacy"}
            className={activeTab !== "privacy" ? "hidden" : "space-y-5"}
          >
            <Card>
              <div className="flex items-center justify-between mb-4">
                <h2 className="font-semibold text-[var(--color-fg-default)] flex items-center gap-2">
                  <User className="h-5 w-5 text-[var(--color-accent-fg)]" /> Authenticated Operator Identity
                </h2>
                <Badge tone="success" className="flex items-center gap-1.5">
                  <Check className="h-3 w-3" /> Session Active
                </Badge>
              </div>

              <div className="p-4 rounded-[var(--radius-lg)] bg-[var(--color-canvas-subtle)]/50 border border-[var(--color-border-default)] mb-4">
                <div className="grid gap-4 sm:grid-cols-2 text-sm">
                  <div>
                    <span className="text-xs text-[var(--color-fg-muted)] block">Operator Name</span>
                    <span className="font-medium text-[var(--color-fg-default)]">{authUser?.full_name || "Lead Operator"}</span>
                  </div>
                  <div>
                    <span className="text-xs text-[var(--color-fg-muted)] block">Email</span>
                    <span className="font-mono text-[var(--color-fg-default)]">{authUser?.email || "operator@cauveris.ai"}</span>
                  </div>
                  <div>
                    <span className="text-xs text-[var(--color-fg-muted)] block">Role & Permissions</span>
                    <span className="font-mono text-[var(--color-accent-fg)] uppercase">{authUser?.role || "ENGINEER"}</span>
                  </div>
                  <div>
                    <span className="text-xs text-[var(--color-fg-muted)] block">Organization Slug</span>
                    <span className="font-mono text-[var(--color-fg-default)]">{authUser?.org_id || "org_demo"}</span>
                  </div>
                  <div>
                    <span className="text-xs text-[var(--color-fg-muted)] block">Platform Release</span>
                    <span className="font-mono text-xs font-semibold text-[var(--color-accent-fg)]">{APP_FULL_VERSION}</span>
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-[var(--color-border-default)]">
                <p className="text-xs text-[var(--color-fg-muted)]">
                  Session secured with cryptographically signed HS256 JWT tokens with automatic silent refresh.
                </p>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={async () => {
                    await logout();
                    router.push("/login");
                  }}
                  className={BTN_FOCUS}
                >
                  <LogOut className="h-4 w-4 mr-1.5" /> Sign Out
                </Button>
              </div>
            </Card>

            <Card>
              <h3 className="font-semibold text-[var(--color-fg-default)] mb-4 flex items-center gap-2">
                <Shield className="h-5 w-5 text-[var(--color-accent-fg)]" /> API Security & Protection Perimeter
              </h3>
              <div className="grid gap-3 sm:grid-cols-3 text-xs">
                <div className="p-3.5 rounded-[var(--radius-md)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/40">
                  <div className="flex items-center gap-1.5 font-bold font-mono text-[var(--color-fg-default)] mb-1">
                    <Shield className="h-3.5 w-3.5 text-emerald-400" /> Rate Limiting
                  </div>
                  <p className="text-[var(--color-fg-muted)]">Sliding-window token bucket enforced per client IP and organization token.</p>
                </div>
                <div className="p-3.5 rounded-[var(--radius-md)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/40">
                  <div className="flex items-center gap-1.5 font-bold font-mono text-[var(--color-fg-default)] mb-1">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" /> Idempotency Keys
                  </div>
                  <p className="text-[var(--color-fg-muted)]">Automated deduplication prevents accidental duplicate incident creation or runs.</p>
                </div>
                <div className="p-3.5 rounded-[var(--radius-md)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/40">
                  <div className="flex items-center gap-1.5 font-bold font-mono text-[var(--color-fg-default)] mb-1">
                    <Shield className="h-3.5 w-3.5 text-emerald-400" /> Sandboxed Execution
                  </div>
                  <p className="text-[var(--color-fg-muted)]">Digital twin interventions execute in isolated runtime contexts with zero network access.</p>
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
            className={activeTab !== "data" ? "hidden" : "space-y-5"}
          >
            <Card>
              <h2 className="font-semibold text-[var(--color-fg-default)] mb-4 flex items-center gap-2">
                <Database className="h-5 w-5 text-[var(--color-accent-fg)]" /> Workspace & Local Incident Storage
              </h2>
              <div className="space-y-4">
                <div className="p-4 rounded-[var(--radius-lg)] bg-[var(--color-canvas-subtle)]/50 border border-[var(--color-border-default)]">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-mono font-bold text-[var(--color-fg-default)]">Active Incident Workspace</span>
                    <Badge tone="primary">{incidentId || "None"}</Badge>
                  </div>
                  <p className="text-xs text-[var(--color-fg-muted)] leading-relaxed">
                    Cauveris uses browser-local persistent storage to maintain active timeline positions, visual inspection parameters, and current incident state. Resetting demo data clears temporary memory without deleting package evidence on disk.
                  </p>
                </div>

                <div className="flex flex-wrap gap-3 pt-1">
                  <Button variant="outline" size="sm" onClick={exportSettings} className={BTN_FOCUS}>
                    <Download className="h-4 w-4 mr-2" /> Export Settings JSON
                  </Button>
                  <Button variant="outline" size="sm" onClick={importSettings} className={BTN_FOCUS}>
                    <Upload className="h-4 w-4 mr-2" /> Import Settings JSON
                  </Button>
                  <Button variant="outline" size="sm" onClick={resetSettings} className={BTN_FOCUS}>
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
            className={activeTab !== "advanced" ? "hidden" : "space-y-5"}
          >
            {/* Live Model Gateway Status Card */}
            <Card>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="font-semibold text-[var(--color-fg-default)] flex items-center gap-2">
                    <Server className="h-5 w-5 text-[var(--color-accent-fg)]" /> Model Gateway Status
                  </h2>
                  <p className="text-xs text-[var(--color-fg-muted)] mt-0.5">
                    Live inference engine status and model execution configuration
                  </p>
                </div>
                <Badge
                  tone={isLiveGateway ? "success" : "neutral"}
                  className="flex items-center gap-1.5 px-3 py-1"
                >
                  <span
                    className={`h-2 w-2 rounded-full ${
                      isLiveGateway ? "bg-zinc-200 animate-pulse" : "bg-[var(--color-fg-muted)]"
                    }`}
                  />
                  <span>{isLiveGateway ? "Nebius Live Gateway Active" : "Deterministic Local Fixtures"}</span>
                </Badge>
              </div>

              <div className="p-4 rounded-[var(--radius-lg)] bg-[var(--color-canvas-subtle)]/50 border border-[var(--color-border-default)] mb-4">
                <div className="grid gap-4 sm:grid-cols-2 text-sm">
                  <div>
                    <span className="text-xs text-[var(--color-fg-muted)] block">Active Provider</span>
                    <span className="font-medium text-[var(--color-fg-default)]">{gatewayProviderName}</span>
                  </div>
                  <div>
                    <span className="text-xs text-[var(--color-fg-muted)] block">Fast Model</span>
                    <span className="font-mono text-[var(--color-accent-fg)]">{settings.modelFast}</span>
                  </div>
                  <div>
                    <span className="text-xs text-[var(--color-fg-muted)] block">Reasoning Model</span>
                    <span className="font-mono text-zinc-200">{settings.modelReasoning}</span>
                  </div>
                  <div>
                    <span className="text-xs text-[var(--color-fg-muted)] block">Escalation Model</span>
                    <span className="font-mono text-zinc-200">{settings.modelEscalation}</span>
                  </div>
                </div>
              </div>

              {/* Secure API Key Input Section */}
              <div className="space-y-4 pt-2 border-t border-[var(--color-border-default)]">
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label htmlFor="settings-model-api-key" className="text-sm font-medium text-[var(--color-fg-default)] flex items-center gap-2">
                      <Key className="h-4 w-4 text-[var(--color-accent-fg)]" /> Model API Key
                    </label>
                    {maskedKey && (
                      <span className="text-xs text-zinc-300 flex items-center gap-1">
                        <Check className="h-3 w-3" /> Key Stored & Protected
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-[var(--color-fg-muted)] mb-3">
                    Paste your Nebius or OpenAI API key below. Once saved, the key is permanently masked on screen to prevent shoulder-surfing.
                  </p>

                  {/* Masked Preview if stored */}
                  {maskedKey && (
                    <div className="mb-3 flex items-center justify-between p-3 rounded-[var(--radius-lg)] bg-zinc-900 border border-zinc-700">
                      <div className="flex items-center gap-2.5">
                        <Shield className="h-4 w-4 text-zinc-300 flex-shrink-0" />
                        <div>
                          <span className="text-xs text-zinc-200 font-mono tracking-wider">{maskedKey}</span>
                          <span className="text-[10px] text-[var(--color-fg-muted)] block">Stored safely in runtime environment</span>
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
                          {copiedKey ? <Check className="h-3.5 w-3.5 text-zinc-100" /> : <Copy className="h-3.5 w-3.5" />}
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
                      className={`absolute right-3 p-1 text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] rounded ${BTN_FOCUS}`}
                      aria-label={showApiKey ? "Hide API key" : "Show API key"}
                    >
                      {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>

                {/* Test Result Feedback */}
                {testResult && (
                  <div
                    className={`p-3.5 rounded-[var(--radius-lg)] border text-sm flex items-start gap-2.5 ${
                      testResult.isTesting
                        ? "bg-[var(--color-canvas-subtle)] border-[var(--color-border-default)] text-[var(--color-fg-default)]"
                        : testResult.success
                        ? "bg-zinc-800 border-zinc-700 text-zinc-200"
                        : "bg-[var(--color-danger-muted)] border-[var(--color-danger-muted)]/30 text-zinc-200"
                    }`}
                  >
                    {testResult.isTesting ? (
                      <Loader2 className="h-4 w-4 animate-spin mt-0.5 flex-shrink-0" />
                    ) : testResult.success ? (
                      <CheckCircle2 className="h-4 w-4 text-zinc-200 mt-0.5 flex-shrink-0" />
                    ) : (
                      <XCircle className="h-4 w-4 text-[var(--color-danger-fg)] mt-0.5 flex-shrink-0" />
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
                      className={`text-[var(--color-danger-fg)] hover:bg-[var(--color-danger-muted)] ${BTN_FOCUS}`}
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
              <h3 className="font-semibold text-[var(--color-fg-default)] mb-4 flex items-center gap-2">
                <Globe className="h-5 w-5 text-[var(--color-accent-fg)]" /> Gateway Endpoint & Model Architecture
              </h3>
              <div className="space-y-4">
                <div>
                  <label htmlFor="settings-model-base-url" className="block text-sm font-medium text-[var(--color-fg-default)] mb-1">
                    Gateway Base URL
                  </label>
                  <Input
                    id="settings-model-base-url"
                    aria-label="Gateway Base URL"
                    value={settings.modelBaseUrl}
                    onChange={(e) => updateSetting("modelBaseUrl", e.target.value)}
                    placeholder="https://api.tokenfactory.nebius.com/v1"
                  />
                  <p className="text-xs text-[var(--color-fg-muted)] mt-1">
                    Compatible with Nebius Token Factory or any OpenAI-compatible API proxy
                  </p>
                </div>

                <div className="grid gap-3 sm:grid-cols-3">
                  <div>
                    <label htmlFor="settings-model-fast" className="block text-sm font-medium text-[var(--color-fg-default)] mb-1">
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
                    <label htmlFor="settings-model-reasoning" className="block text-sm font-medium text-[var(--color-fg-default)] mb-1">
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
                    <label htmlFor="settings-model-escalation" className="block text-sm font-medium text-[var(--color-fg-default)] mb-1">
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

            {/* General Engine Parameters */}
            <Card>
              <h3 className="font-semibold text-[var(--color-fg-default)] mb-4 flex items-center gap-2">
                <Sliders className="h-5 w-5 text-[var(--color-accent-fg)]" /> Engine Execution Parameters
              </h3>
              <div className="space-y-4">
                <div>
                  <label htmlFor="settings-api-endpoint" className="block text-sm font-medium text-[var(--color-fg-default)] mb-1">
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
                  <label htmlFor="settings-max-concurrent" className="block text-sm font-medium text-[var(--color-fg-default)] mb-1">
                    Max concurrent experiments
                  </label>
                  <Slider
                    id="settings-max-concurrent"
                    aria-label="Max concurrent experiments"
                    value={settings.maxConcurrentExperiments}
                    min={1}
                    max={10}
                    step={1}
                    showValue
                    onValueChange={(v) => updateSetting("maxConcurrentExperiments", v)}
                  />
                </div>

                <div className={settingRowStyles}>
                  <div>
                    <p className="font-medium text-[var(--color-fg-default)]">Debug Mode</p>
                    <p className="text-sm text-[var(--color-fg-muted)]">Enable verbose logging and diagnostic stack traces</p>
                  </div>
                  <Toggle
                    aria-label="Debug Mode"
                    checked={settings.debugMode}
                    onChange={(v) => updateSetting("debugMode", v)}
                  />
                </div>
              </div>
            </Card>
          </div>

          {/* 7. Intake Tab */}
          <div
            role="tabpanel"
            id="panel-intake"
            aria-labelledby="tab-intake"
            hidden={activeTab !== "intake"}
            className={activeTab !== "intake" ? "hidden" : "space-y-5"}
          >
            <Card>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="font-semibold text-[var(--color-fg-default)] flex items-center gap-2">
                    <Globe className="h-5 w-5 text-[var(--color-accent-fg)]" /> Universal Source Intake & Security Perimeter
                  </h2>
                  <p className="text-xs text-[var(--color-fg-muted)] mt-0.5">
                    Read-only capabilities, accepted source specifications, format support, and security boundaries
                  </p>
                </div>
                {capabilities && (
                  <Badge
                    tone={capabilities.url_ingestion_enabled ? "success" : "neutral"}
                    className="flex items-center gap-1.5 px-3 py-1"
                  >
                    <span
                      className={`h-2 w-2 rounded-full ${
                        capabilities.url_ingestion_enabled ? "bg-emerald-400" : "bg-zinc-400"
                      }`}
                    />
                    <span>{capabilities.url_ingestion_enabled ? "URL Ingestion Active" : "URL Ingestion Disabled"}</span>
                  </Badge>
                )}
              </div>

              {capabilitiesLoading && !capabilities && (
                <div className="flex items-center justify-center py-12 text-[var(--color-fg-muted)] gap-2">
                  <Loader2 className="h-5 w-5 animate-spin text-[var(--color-accent-fg)]" />
                  <span className="text-sm">Querying intake subsystem...</span>
                </div>
              )}

              {capabilities && (
                <div className="space-y-4">
                  {/* Capabilities Status Grid */}
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <div className="p-3.5 rounded-[var(--radius-md)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/40">
                      <span className="text-[11px] font-mono text-[var(--color-fg-muted)] block mb-1 uppercase tracking-wider">
                        Remote URL Ingest
                      </span>
                      <span className={`font-semibold text-sm ${capabilities.url_ingestion_enabled ? "text-emerald-400" : "text-zinc-400"}`}>
                        {capabilities.url_ingestion_enabled ? "Enabled" : "Disabled (local only)"}
                      </span>
                    </div>

                    <div className="p-3.5 rounded-[var(--radius-md)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/40">
                      <span className="text-[11px] font-mono text-[var(--color-fg-muted)] block mb-1 uppercase tracking-wider">
                        Git Clone Ingest
                      </span>
                      <span className={`font-semibold text-sm ${capabilities.allow_git_clone ? "text-emerald-400" : "text-zinc-400"}`}>
                        {capabilities.allow_git_clone ? "Enabled" : "Disabled"}
                      </span>
                    </div>

                    <div className="p-3.5 rounded-[var(--radius-md)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/40">
                      <span className="text-[11px] font-mono text-[var(--color-fg-muted)] block mb-1 uppercase tracking-wider">
                        Max Archive Size
                      </span>
                      <span className="font-semibold text-sm text-[var(--color-fg-default)]">
                        {(capabilities.limits.max_archive_file_size / (1024 * 1024)).toFixed(0)} MB
                      </span>
                    </div>

                    <div className="p-3.5 rounded-[var(--radius-md)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/40">
                      <span className="text-[11px] font-mono text-[var(--color-fg-muted)] block mb-1 uppercase tracking-wider">
                        Decompression Cap
                      </span>
                      <span className="font-semibold text-sm text-[var(--color-fg-default)]">
                        {(capabilities.limits.max_archive_uncompressed_size / (1024 * 1024)).toFixed(0)} MB
                      </span>
                    </div>
                  </div>

                  {/* Accepted Archive Formats */}
                  <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted)] mb-2">
                      Supported Archive & Compression Formats
                    </h3>
                    <div className="flex flex-wrap gap-1.5 font-mono text-xs">
                      {capabilities.supported_archive_formats.map((fmt: string, idx: number) => (
                        <span
                          key={idx}
                          className="px-2.5 py-1 rounded bg-[var(--color-canvas-subtle)] border border-[var(--color-border-default)] text-[var(--color-fg-default)] font-medium"
                        >
                          {fmt}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Accepted Source Specs */}
                  <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted)] mb-2">
                      Supported Source Specifications
                    </h3>
                    <div className="border border-[var(--color-border-default)] rounded-[var(--radius-md)] overflow-hidden">
                      <table className="w-full text-left text-xs font-mono">
                        <thead className="bg-[var(--color-canvas-subtle)] border-b border-[var(--color-border-default)] text-[var(--color-fg-muted)]">
                          <tr>
                            <th className="py-2 px-3 font-semibold">Specification Format</th>
                            <th className="py-2 px-3 font-semibold">Example Spec</th>
                            <th className="py-2 px-3 font-semibold font-sans">Description</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[var(--color-border-default)]">
                          {capabilities.spec_forms.map((item, idx: number) => (
                            <tr key={idx} className="hover:bg-[var(--color-canvas-subtle)]/30">
                              <td className="py-2 px-3 text-[var(--color-accent-fg)] font-bold">{item.form}</td>
                              <td className="py-2 px-3 text-[var(--color-fg-default)]">{item.example}</td>
                              <td className="py-2 px-3 font-sans text-[var(--color-fg-muted)] text-[11px]">{item.description}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Built-in Allowed Hosts */}
                  <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted)] mb-2">
                      Built-in Trusted Host Allowlist
                    </h3>
                    <div className="flex flex-wrap gap-1.5 font-mono text-[11px]">
                      {capabilities.host_policy.builtin_allowed_hosts.map((host, idx) => (
                        <span
                          key={idx}
                          className="px-2 py-0.5 rounded bg-[var(--color-canvas-subtle)] border border-[var(--color-border-default)] text-[var(--color-fg-default)]"
                        >
                          {host}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <AuthGate redirect="/settings" loadingLabel="Loading settings...">
      <SettingsContent />
    </AuthGate>
  );
}
