"""
Конфигурация pipeline плагинов.

PipelineConfig описывает цепочку стадий: каждая стадия — это
пара (препроцессор, модель) с параметрами.

Пример простого каскада:
    gate (Stage1, is_gate=True) → classifier (Stage2/Stage3)
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StageConfig:
    """
    Один шаг каскада.

    preprocessor_name: имя зарегистрированного препроцессора
    model_name:        имя зарегистрированной модели
    threshold:         порог срабатывания (score ≥ threshold → warning/anomaly)
    is_gate:           True → это бинарный фильтр: если verdict=="anomaly" или "warning",
                       передать событие в next_stage для классификации
    next_stage:        имя следующей StageConfig или None (конец pipeline)
    """
    preprocessor_name: str
    model_name: str
    threshold: float = 0.70
    is_gate: bool = False
    next_stage: str | None = None


@dataclass
class PipelineConfig:
    """
    Полная конфигурация pipeline.

    name:         уникальное имя, например "simple", "advanced", "my_custom"
    description:  описание для UI
    entry_stage:  имя первой стадии (ключ в stages)
    stages:       dict имя → StageConfig
    is_builtin:   True → встроенный пресет, нельзя удалить через API
    """
    name: str
    description: str
    entry_stage: str
    stages: dict[str, StageConfig] = field(default_factory=dict)
    is_builtin: bool = True

    def validate(self, registry) -> list[str]:
        """
        Проверяет корректность конфига относительно реестра плагинов.
        Возвращает список ошибок (пустой список = всё OK).

        Проверки:
        1. entry_stage существует в stages
        2. Все имена препроцессоров и моделей зарегистрированы
        3. Для каждой стадии preprocessor.output_schema_id in model.accepted_schema_ids
        4. Нет циклических зависимостей через next_stage
        """
        errors: list[str] = []

        # Проверка 1: entry_stage
        if self.entry_stage not in self.stages:
            errors.append(
                f"entry_stage '{self.entry_stage}' не найден в stages: "
                f"{list(self.stages.keys())}"
            )

        visited: set[str] = set()
        for stage_name, stage in self.stages.items():

            # Проверка 2: препроцессор зарегистрирован
            if stage.preprocessor_name not in registry.preprocessors:
                errors.append(
                    f"Стадия '{stage_name}': препроцессор '{stage.preprocessor_name}' "
                    f"не зарегистрирован"
                )
            # Проверка 2: модель зарегистрирована
            if stage.model_name not in registry.models:
                errors.append(
                    f"Стадия '{stage_name}': модель '{stage.model_name}' "
                    f"не зарегистрирована"
                )

            # Проверка 3: совместимость схем
            prep = registry.preprocessors.get(stage.preprocessor_name)
            model = registry.models.get(stage.model_name)
            if prep and model:
                schema_id = prep.get_output_schema_id()
                accepted  = model.get_accepted_schema_ids()
                if accepted and schema_id not in accepted:
                    errors.append(
                        f"Стадия '{stage_name}': несовместимость — "
                        f"препроцессор '{stage.preprocessor_name}' "
                        f"отдаёт схему '{schema_id}', "
                        f"но модель '{stage.model_name}' "
                        f"принимает только {accepted}"
                    )

            # Проверка 4: нет циклов через next_stage
            if stage.next_stage is not None:
                if stage.next_stage in visited:
                    errors.append(
                        f"Обнаружен цикл: стадия '{stage_name}' "
                        f"ссылается на уже посещённую '{stage.next_stage}'"
                    )
                if stage.next_stage not in self.stages:
                    errors.append(
                        f"Стадия '{stage_name}': next_stage '{stage.next_stage}' "
                        f"не найдена в stages"
                    )
            visited.add(stage_name)

        return errors

    def to_dict(self) -> dict:
        """Сериализация для API и хранения в JSON."""
        return {
            "name":        self.name,
            "description": self.description,
            "entry_stage": self.entry_stage,
            "is_builtin":  self.is_builtin,
            "stages": {
                k: {
                    "preprocessor_name": v.preprocessor_name,
                    "model_name":        v.model_name,
                    "threshold":         v.threshold,
                    "is_gate":           v.is_gate,
                    "next_stage":        v.next_stage,
                }
                for k, v in self.stages.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineConfig":
        """Десериализация из JSON (для пользовательских pipeline)."""
        stages = {
            k: StageConfig(
                preprocessor_name=v["preprocessor_name"],
                model_name=v["model_name"],
                threshold=float(v.get("threshold", 0.70)),
                is_gate=bool(v.get("is_gate", False)),
                next_stage=v.get("next_stage"),
            )
            for k, v in data.get("stages", {}).items()
        }
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            entry_stage=data["entry_stage"],
            stages=stages,
            is_builtin=bool(data.get("is_builtin", False)),
        )
