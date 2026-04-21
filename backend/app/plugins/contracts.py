"""
Контракты данных плагинов AnomalyNet.

Определяет типы которые передаются между блоками pipeline:
  захват трафика → препроцессор → модель → вердикт

Эти типы НЕ заменяют app.contracts.schemas — они существуют параллельно
и используются только внутри системы плагинов.
Встроенные обёртки (builtin/) конвертируют между старыми и новыми типами.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ── Идентификаторы входных типов ──────────────────────────────────────────────

RAW_FLOW    = "raw_flow"      # выход FlowAggregator — один двунаправленный поток
RAW_PACKETS = "raw_packets"   # список сырых пакетов до агрегации
HOST_EVENTS = "host_events"   # события хоста (процессы, файлы)


@dataclass
class RawFlow:
    """
    Один двунаправленный сетевой поток от FlowAggregator.

    Поля data — dict с ключами:
      src_ip: str, dst_ip: str, src_port: int, dst_port: int
      protocol: str ("TCP" | "UDP" | "ICMP")
      packets_fwd: int, packets_bwd: int
      bytes_fwd: int, bytes_bwd: int
      duration_ms: float   — длительность потока в мс
      timestamp: float     — unix timestamp начала потока
      syn_count: int, rst_count: int, fin_count: int, ack_count: int
      iat_mean_ms: float, iat_max_ms: float, iat_min_ms: float
      raw_features: dict[str, float]           — 71 CICFlowMeter признак
      raw_features_cic2023: dict[str, float]   — 46 CIC IoT 2023 признаков (если advanced)
    """
    type_id: str = RAW_FLOW
    data: dict = field(default_factory=dict)


@dataclass
class RawPackets:
    """
    Список сырых пакетов до агрегации в flow.
    Для глубокого анализа (DPI, payload).
    data: list[scapy.Packet]
    """
    type_id: str = RAW_PACKETS
    data: list = field(default_factory=list)


@dataclass
class HostEvents:
    """
    События хоста: процессы, системные вызовы, открытые файлы.
    Для защиты ПК (не сетевой трафик).
    data: dict с полями pid, name, cmdline, connections, files
    """
    type_id: str = HOST_EVENTS
    data: dict = field(default_factory=dict)


# ── Выходной тип препроцессора ────────────────────────────────────────────────

FEATURE_VECTOR = "feature_vector"


@dataclass
class PluginFeatureVector:
    """
    Числовой вектор признаков — выход препроцессора, вход модели.

    features:       list[float] длиной N — значения признаков по порядку
                    (используем list вместо numpy для независимости от numpy в плагинах)
    feature_names:  list[str] длиной N — имена признаков
    schema_id:      str — идентификатор схемы, например:
                    "cicflowmeter_71"  — 71 CICFlowMeter признак
                    "cic_iot2023_46"   — 46 CIC IoT 2023 признаков
                    "cascade_dual"     — оба набора одновременно (special)
                    "custom_<name>"    — пользовательская схема
    meta:           dict — дополнительные метаданные (src_ip, event_id и т.д.)
    """
    type_id: str = FEATURE_VECTOR
    features: list = field(default_factory=list)
    feature_names: list = field(default_factory=list)
    schema_id: str = ""
    meta: dict = field(default_factory=dict)


# ── Выходной тип модели ────────────────────────────────────────────────────────

VERDICT = "verdict"


@dataclass
class PluginVerdict:
    """
    Результат работы модели.

    score:        float 0.0–1.0, вероятность аномалии
    verdict:      str "normal" | "warning" | "anomaly"
    attack_class: str | None — тип атаки или None
    model_name:   str — какая модель вынесла вердикт
    stage:        str — "stage1" | "stage2" | "stage3" | "custom"
    reason:       str — текстовое объяснение
    """
    type_id: str = VERDICT
    score: float = 0.0
    verdict: str = "normal"
    attack_class: str | None = None
    model_name: str = ""
    stage: str = ""
    reason: str = ""
