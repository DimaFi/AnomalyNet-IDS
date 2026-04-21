# AnomalyNet Plugin Guide

Система плагинов позволяет подключать собственные препроцессоры и модели без изменения основного кода.

---

## Быстрый старт

1. Создай `.py` файл в папке `plugins/` (рядом с этим файлом)
2. Унаследуй от `BasePreprocessor` или `BaseModel`
3. Реализуй все абстрактные методы
4. Перезапусти сервер **или** вызови `POST /api/plugins/reload`

Готово — плагин появится в `/api/plugins/preprocessors` или `/api/plugins/models`.

---

## Препроцессор

```python
from app.plugins.base_preprocessor import BasePreprocessor
from app.plugins.contracts import RAW_FLOW, PluginFeatureVector

class MyPreprocessor(BasePreprocessor):
    def get_name(self) -> str:
        return "my_preprocessor"          # уникальный ключ

    def get_description(self) -> str:
        return "Описание для UI"

    def get_version(self) -> str:
        return "1.0.0"

    def get_input_type(self) -> str:
        return RAW_FLOW

    def get_output_schema_id(self) -> str:
        return "my_schema_v1"             # ID схемы признаков

    def get_feature_names(self) -> list[str]:
        return ["feat1", "feat2", ...]

    def on_load(self) -> None:
        pass  # загрузи артефакты здесь

    def transform(self, raw_input) -> PluginFeatureVector:
        # raw_input — NormalizedFlowEvent
        features = [...]
        return PluginFeatureVector(
            features=features,
            feature_names=self.get_feature_names(),
            schema_id=self.get_output_schema_id(),
            meta={"event_id": raw_input.event_id, "src_ip": raw_input.src_ip},
        )
```

### Поля NormalizedFlowEvent (raw_input)

| Поле | Тип | Описание |
|------|-----|---------|
| `event_id` | str | UUID события |
| `src_ip`, `dst_ip` | str | IP-адреса |
| `src_port`, `dst_port` | int | Порты |
| `protocol` | str | TCP / UDP / ICMP / OTHER |
| `packet_count` | int | Число пакетов |
| `byte_count` | int | Число байт |
| `duration_ms` | int | Длительность потока, мс |
| `raw_features` | dict\[str, float\] \| None | 71 CICFlowMeter признак |
| `raw_features_cic2023` | dict\[str, float\] \| None | 46 CIC IoT 2023 признаков |

`raw_features` заполнен только в `run_mode=linux_live`.
`raw_features_cic2023` заполнен только при `detection_mode=advanced`.

---

## Модель

```python
from app.plugins.base_model import BaseModel
from app.plugins.contracts import PluginFeatureVector, PluginVerdict

class MyModel(BaseModel):
    def get_name(self) -> str:
        return "my_model"

    def get_description(self) -> str:
        return "Описание"

    def get_version(self) -> str:
        return "1.0.0"

    def get_accepted_schema_ids(self) -> list[str]:
        return ["my_schema_v1"]          # должно совпасть с препроцессором

    def get_output_classes(self) -> list[str]:
        return ["Benign", "Attack"]

    def on_load(self) -> None:
        pass  # загрузи model.cbm / model.pkl здесь

    def predict(self, features: PluginFeatureVector) -> PluginVerdict:
        ok, reason = self.check_compatibility(features.schema_id)
        if not ok:
            raise ValueError(reason)

        score = ...  # твоя логика
        return PluginVerdict(
            score=score,
            verdict="anomaly" if score >= 0.85 else "warning" if score >= 0.70 else "normal",
            attack_class="DoS",          # или None
            model_name=self.get_name(),
            stage="custom",
            reason=f"score={score:.3f}",
        )
```

---

## Pipeline конфиги

Pipeline описывает цепочку стадий. Создать через API:

```bash
curl -X POST http://localhost:8000/api/plugins/pipelines \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my_pipeline",
    "description": "Мой пайплайн",
    "entry_stage": "prefilter",
    "stages": {
      "prefilter": {
        "preprocessor_name": "my_preprocessor",
        "model_name": "my_model",
        "threshold": 0.70,
        "is_gate": false,
        "next_stage": null
      }
    }
  }'
```

### Встроенные пресеты

| Имя | Описание |
|-----|---------|
| `fast` | Stage1 binary gate — максимальная скорость |
| `simple` | Stage1 gate → Stage2 multiclass (71 признак) |
| `advanced` | Stage1 gate → Stage3 IoT2023 (46 признаков, Macro F1=0.819) |

Builtin пресеты нельзя удалить или перезаписать через API.

---

## REST API

| Метод | URL | Описание |
|-------|-----|---------|
| GET | `/api/plugins/preprocessors` | Список препроцессоров |
| GET | `/api/plugins/models` | Список моделей |
| GET | `/api/plugins/pipelines` | Список пайплайнов |
| POST | `/api/plugins/pipelines` | Создать пайплайн |
| DELETE | `/api/plugins/pipelines/{name}` | Удалить пайплайн |
| POST | `/api/plugins/pipelines/{name}/validate` | Проверить пайплайн |
| POST | `/api/plugins/reload` | Перезагрузить плагины из `plugins/` |

---

## Совместимость схем

`schema_id` — это строковый ключ совместимости:

```
preprocessor.get_output_schema_id()  →  model.get_accepted_schema_ids()
```

Встроенные схемы:
- `cicflowmeter_71` — 71 CICFlowMeter признак
- `cic_iot2023_46` — 46 CIC IoT 2023 признаков
- `cascade_dual` — оба набора одновременно (Stage1+Stage3)

Для своих моделей используй `custom_<name>`.

---

## Важные замечания

- Плагин **не должен** изменять объекты из `app.contracts.schemas` — только использовать типы из `app.plugins.contracts`
- Если `on_load()` бросит исключение — плагин не зарегистрируется, остальные продолжат работу
- Плагины из `plugins/` не перекрывают builtin плагины с тем же именем — они перезаписывают их (порядок: builtin → discover)
- Пользовательские пайплайны сохраняются в `config/user_pipelines.json` и переживают перезапуск
