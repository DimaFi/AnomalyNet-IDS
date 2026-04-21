import { create } from "zustand";
import { api } from "../lib/api";
import type {
  CreatePipelinePayload,
  ModelMeta,
  PipelineConfig,
  PreprocessorMeta,
} from "../types/plugins";

interface PluginsStore {
  preprocessors: PreprocessorMeta[];
  models: ModelMeta[];
  pipelines: PipelineConfig[];
  loading: boolean;
  error: string | null;

  fetchAll: () => Promise<void>;
  createPipeline: (payload: CreatePipelinePayload) => Promise<PipelineConfig>;
  deletePipeline: (name: string) => Promise<void>;
  reloadPlugins: () => Promise<{ discovered: number; message: string }>;
}

export const usePluginsStore = create<PluginsStore>((set, get) => ({
  preprocessors: [],
  models: [],
  pipelines: [],
  loading: false,
  error: null,

  fetchAll: async () => {
    set({ loading: true, error: null });
    try {
      const [preprocessors, models, pipelines] = await Promise.all([
        api.getPluginPreprocessors(),
        api.getPluginModels(),
        api.getPluginPipelines(),
      ]);
      set({ preprocessors, models, pipelines, loading: false });
    } catch (err) {
      set({ error: String(err), loading: false });
    }
  },

  createPipeline: async (payload) => {
    const created = await api.createPluginPipeline(payload);
    set((s) => ({ pipelines: [...s.pipelines, created] }));
    return created;
  },

  deletePipeline: async (name) => {
    await api.deletePluginPipeline(name);
    set((s) => ({ pipelines: s.pipelines.filter((p) => p.name !== name) }));
  },

  reloadPlugins: async () => {
    const result = await api.reloadPlugins();
    // Refresh all after reload
    await get().fetchAll();
    return result;
  },
}));
