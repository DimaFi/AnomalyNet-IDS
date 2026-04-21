"""
PluginPipelineRunner — мост между plugin registry и service.py.

Реализует интерфейс, совместимый с service.py:
  preprocess.transform(event) → FeatureVector
  model.infer(features)       → InferenceResult

Один объект PluginPipelineRunner играет роль и препроцессора, и модели:
  transform() запускает весь pipeline (все стадии), кэширует InferenceResult
  infer()     возвращает закэшированный результат

Использование в service.py:
  if active_model_id.startswith("plugin:"):
      runner = PluginPipelineRunner(pipeline_name)
      preprocess = model = runner

Примечание о входных данных препроцессора:
  transform() получает NormalizedFlowEvent (не RawFlow) — это полный объект события
  с атрибутами .src_ip, .dst_ip, .raw_features (dict 71 признак),
  .raw_features_cic2023, .protocol, .packet_count, .byte_count, .duration_ms.
  Пользовательские препроцессоры получают его в аргументе transform(raw_input).
"""
from __future__ import annotations

from app.contracts.schemas import FeatureVector, InferenceResult, NormalizedFlowEvent
from app.plugins.contracts import PluginFeatureVector, PluginVerdict


def _plugin_fv_to_fv(pfv: PluginFeatureVector, event_id: str) -> FeatureVector:
    return FeatureVector(
        event_id=event_id,
        contract_version="plugin_v1",
        profile_name=pfv.schema_id,
        values=dict(zip(pfv.feature_names, pfv.features)),
    )


def _verdict_to_inference(verdict: PluginVerdict, event_id: str) -> InferenceResult:
    label = verdict.verdict
    if label not in ("normal", "warning", "anomaly"):
        label = "normal"
    return InferenceResult(
        event_id=event_id,
        label=label,
        score=float(verdict.score),
        reason=verdict.reason,
        model_id=verdict.model_name,
        attack_class=verdict.attack_class,
    )


class PluginPipelineRunner:
    """
    Единый объект-адаптер, совместимый с интерфейсом service.py.

    transform(event) → FeatureVector   — запускает все стадии pipeline, кэширует результат
    infer(features)  → InferenceResult — возвращает кэш и очищает его

    Оба метода должны вызываться поочерёдно (так и делает service.py).
    """

    def __init__(self, pipeline_name: str) -> None:
        self._pipeline_name = pipeline_name
        self._cached_inference: InferenceResult | None = None

    def transform(self, event: NormalizedFlowEvent) -> FeatureVector:
        from app.plugins.registry import get_registry
        registry = get_registry()

        config = registry.pipelines.get(self._pipeline_name)
        if config is None:
            raise ValueError(f"Plugin pipeline '{self._pipeline_name}' не найден в реестре")

        # Передаём event напрямую: и builtin-, и пользовательские препроцессоры
        # ожидают NormalizedFlowEvent с атрибутами .raw_features, .protocol и т.д.
        current_stage_name: str | None = config.entry_stage
        last_fv: PluginFeatureVector | None = None
        last_verdict: PluginVerdict | None = None

        while current_stage_name:
            stage = config.stages[current_stage_name]

            preprocessor = registry.preprocessors.get(stage.preprocessor_name)
            if preprocessor is None:
                raise ValueError(
                    f"Препроцессор '{stage.preprocessor_name}' не зарегистрирован. "
                    "Проверьте настройки путей к артефактам."
                )
            model = registry.models.get(stage.model_name)
            if model is None:
                raise ValueError(
                    f"Модель '{stage.model_name}' не зарегистрирована. "
                    "Проверьте настройки путей к модели."
                )

            fv = preprocessor.transform(event)
            verdict = model.predict(fv)

            last_fv = fv
            last_verdict = verdict

            # Gate: если нормальный трафик — не запускаем следующие стадии
            if stage.is_gate and verdict.verdict == "normal":
                break

            current_stage_name = stage.next_stage

        if last_fv is None or last_verdict is None:
            raise ValueError(f"Pipeline '{self._pipeline_name}' не произвёл результата")

        self._cached_inference = _verdict_to_inference(last_verdict, event.event_id)
        return _plugin_fv_to_fv(last_fv, event.event_id)

    def infer(self, features: FeatureVector) -> InferenceResult:
        if self._cached_inference is None:
            raise ValueError("infer() вызван до transform() — нарушение порядка вызовов")
        result = self._cached_inference
        self._cached_inference = None
        return result
