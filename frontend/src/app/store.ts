import { create } from "zustand";
import type {
  AppSettings,
  AppView,
  HealthResponse,
  LanguageCode,
  ModelsRegistry,
  PipelineEvent,
  ThemeMode,
  ToastItem
} from "./types";

interface AppState {
  view: AppView;
  health: HealthResponse | null;
  settings: AppSettings | null;
  models: ModelsRegistry | null;
  stream: PipelineEvent[];
  toasts: ToastItem[];
  blockedIps: Set<string>;

  setView: (view: AppView) => void;
  setHealth: (health: HealthResponse) => void;
  setSettings: (settings: AppSettings) => void;
  setModels: (models: ModelsRegistry) => void;
  pushStreamItem: (item: PipelineEvent) => void;
  replaceStream: (items: PipelineEvent[]) => void;
  setTheme: (theme: ThemeMode) => void;
  setLanguage: (language: LanguageCode) => void;
  addToast: (payload: Omit<ToastItem, "id" | "timestamp">) => void;
  dismissToast: (id: string) => void;
  markBlocked: (ip: string) => void;
}

export const useAppStore = create<AppState>((set) => ({
  view: "dashboard",
  health: null,
  settings: null,
  models: null,
  stream: [],
  toasts: [],
  blockedIps: new Set(),

  setView: (view) => set({ view }),
  setHealth: (health) => set({ health }),
  setSettings: (settings) => set({ settings }),
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
    }))
}));
