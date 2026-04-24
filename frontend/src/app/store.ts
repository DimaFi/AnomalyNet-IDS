import { create } from "zustand";
import type {
  AppSettings,
  AppView,
  HealthResponse,
  LanguageCode,
  ModelPreset,
  ModelsRegistry,
  PipelineEvent,
  ThemeMode,
  ToastItem
} from "./types";
import type { Device, DeviceStats } from "../types/device";

interface AppState {
  view: AppView;
  health: HealthResponse | null;
  settings: AppSettings | null;
  models: ModelsRegistry | null;
  presets: ModelPreset[];
  stream: PipelineEvent[];
  toasts: ToastItem[];
  blockedIps: Set<string>;
  // Network map
  devices: Device[];
  selectedMac: string | null;
  deviceStats: DeviceStats | null;

  setView: (view: AppView) => void;
  setHealth: (health: HealthResponse) => void;
  setSettings: (settings: AppSettings) => void;
  setModels: (models: ModelsRegistry) => void;
  setPresets: (presets: ModelPreset[]) => void;
  pushStreamItem: (item: PipelineEvent) => void;
  replaceStream: (items: PipelineEvent[]) => void;
  setTheme: (theme: ThemeMode) => void;
  setLanguage: (language: LanguageCode) => void;
  addToast: (payload: Omit<ToastItem, "id" | "timestamp">) => void;
  dismissToast: (id: string) => void;
  markBlocked: (ip: string) => void;
  markUnblocked: (ip: string) => void;
  setDevices: (devices: Device[]) => void;
  setSelectedMac: (mac: string | null) => void;
  setDeviceStats: (stats: DeviceStats) => void;
}

export const useAppStore = create<AppState>((set) => ({
  view: "dashboard",
  health: null,
  settings: null,
  models: null,
  presets: [],
  stream: [],
  toasts: [],
  blockedIps: new Set(),
  devices: [],
  selectedMac: null,
  deviceStats: null,

  setView: (view) => set({ view }),
  setHealth: (health) => set({ health }),
  setPresets: (presets) => set({ presets }),
  setSettings: (settings) => set((state) => {
    const prevMode = state.settings?.run_mode;
    const switchingFromMock = prevMode === "mock" && settings.run_mode !== "mock";
    return {
      settings,
      ...(switchingFromMock ? { stream: [] } : {}),
    };
  }),
  setModels: (models) => set({ models }),

  pushStreamItem: (item) =>
    set((state) => ({
      stream: [item, ...state.stream].slice(0, 30)
    })),

  replaceStream: (items) => set({ stream: items }),

  setTheme: (theme) =>
    set((state) => ({
      settings: state.settings ? { ...state.settings, theme } : state.settings
    })),

  setLanguage: (language) =>
    set((state) => ({
      settings: state.settings ? { ...state.settings, language } : state.settings
    })),

  addToast: (payload) =>
    set((state) => ({
      toasts: [
        ...state.toasts,
        { ...payload, id: crypto.randomUUID(), timestamp: Date.now() }
      ].slice(-5)
    })),

  dismissToast: (id) =>
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id)
    })),

  markBlocked: (ip) =>
    set((state) => ({
      blockedIps: new Set([...state.blockedIps, ip])
    })),

  markUnblocked: (ip) =>
    set((state) => {
      const next = new Set(state.blockedIps);
      next.delete(ip);
      return { blockedIps: next };
    }),

  setDevices: (devices) => set({ devices }),
  setSelectedMac: (selectedMac) => set({ selectedMac }),
  setDeviceStats: (deviceStats) => set({ deviceStats }),
}));
