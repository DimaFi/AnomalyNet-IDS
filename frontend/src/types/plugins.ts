// Plugin system types — mirrors app/plugins/contracts.py and pipeline_config.py

export interface PreprocessorMeta {
  name: string;
  description: string;
  version: string;
  input_type: string;
  output_schema_id: string;
  feature_count: number;
  feature_names: string[];
  is_builtin: boolean;
}

export interface ModelMeta {
  name: string;
  description: string;
  version: string;
  accepted_schema_ids: string[];
  output_classes: string[];
  is_builtin: boolean;
}

export interface StageConfig {
  preprocessor_name: string;
  model_name: string;
  threshold: number;
  is_gate: boolean;
  next_stage: string | null;
}

export interface PipelineConfig {
  name: string;
  description: string;
  entry_stage: string;
  is_builtin: boolean;
  stages: Record<string, StageConfig>;
}

export interface PluginsState {
  preprocessors: PreprocessorMeta[];
  models: ModelMeta[];
  pipelines: PipelineConfig[];
  loading: boolean;
  error: string | null;
}

export interface CreatePipelinePayload {
  name: string;
  description: string;
  entry_stage: string;
  stages: Record<string, StageConfig>;
}

export interface ValidateResponse {
  valid: boolean;
  errors: string[];
}
