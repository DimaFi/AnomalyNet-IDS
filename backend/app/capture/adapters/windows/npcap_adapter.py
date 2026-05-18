"""
Windows live capture adapter using Scapy + Npcap.

Requires:
  - Npcap installed: https://npcap.com/
  - scapy installed: pip install scapy
  - Administrator privileges (UAC elevation)

Packets are captured by scapy's AsyncSniffer in a background thread.
call_soon_threadsafe bridges scapy callbacks to the asyncio event loop.
Completed flows are pushed into an asyncio.Queue and served via next_event().
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

_log = logging.getLogger("app.capture.windows")

from app.capture.base import CaptureAdapter
from app.contracts.schemas import NormalizedFlowEvent
from app.capture.adapters.linux.flow_aggregator import FlowAggregator
from app.capture.adapters.linux.feature_computer import compute_cicflow_features
from app.capture.adapters.linux.feature_computer_cic2023 import compute_cic2023_features
from app.capture.adapters.linux.flow_record import FlowRecord


PROTO_MAP = {6: "TCP", 17: "UDP", 1: "ICMP"}


def _check_admin() -> bool:
    """Check Administrator privileges via Windows API."""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0  # type: ignore[attr-defined]
    except Exception:
        return False


def _check_npcap_available() -> bool:
    """Check Npcap is installed and Scapy can enumerate Windows interfaces."""
    try:
        from scapy.arch.windows import get_windows_if_list  # type: ignore[import]
        ifaces = get_windows_if_list()
        return isinstance(ifaces, list) and len(ifaces) > 0
    except Exception:
        return False


def _resolve_interface(name: str) -> str:
    """
    Resolve human-readable interface name to Npcap GUID notation.

    Npcap uses \\Device\\NPF_{GUID} format internally.  Scapy 2.5+ can accept
    a description string directly, but being explicit avoids ambiguity when
    multiple adapters share similar names.  Falls back to the original name if
    no match is found — Scapy may still accept it.
    """
    # Already in GUID / NPF notation — return unchanged
    if name.startswith("{") or "NPF_" in name or name.startswith("\\Device\\"):
        return name

    try:
        from scapy.arch.windows import get_windows_if_list  # type: ignore[import]
        ifaces = get_windows_if_list()
        name_lower = name.lower()
        for iface in ifaces:
            iface_name = iface.get("name", "").lower()
            iface_desc = iface.get("description", "").lower()
            if iface_name == name_lower or iface_desc == name_lower:
                guid = iface.get("guid", "")
                if guid:
                    return f"\\Device\\NPF_{guid}"
    except Exception as exc:
        _log.debug("Interface resolution failed for %r: %s", name, exc)

    return name


class WindowsNpcapCapture(CaptureAdapter):
    mode = "windows_live"
    name = "Windows Npcap Live Capture"

    def __init__(
        self,
        interfaces: list[str] | str = "Ethernet",
        detection_mode: str = "simple",
        bpf_filter: str = "",
    ) -> None:
        self._interfaces: list[str] = [interfaces] if isinstance(interfaces, str) else interfaces
        self._detection_mode = detection_mode
        self._bpf_filter = bpf_filter.strip()
        self._queue: asyncio.Queue[NormalizedFlowEvent] = asyncio.Queue(maxsize=500)
        self._aggregator = FlowAggregator(on_flow_complete=self._on_flow_ready)
        self._sniffer = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._dns_monitor = None   # set via set_dns_monitor() after construction
        self._tls_monitor = None   # set via set_tls_monitor() after construction
        self._device_tracker = None
        self._sniffer_kwargs: dict = {}
        self._watchdog_task: asyncio.Task | None = None
        self._last_pkt_time: float = 0.0
        self._tls_stats = {
            "tls_ports_seen": 0,
            "raw_tls_like_seen": 0,
            "tls_fingerprint_seen": 0,
            "tls_parse_success_scapy": 0,
            "tls_parse_success_raw": 0,
            "tls_parse_failed": 0,
            "tls_alerts_emitted": 0,
        }

    def set_dns_monitor(self, monitor) -> None:
        self._dns_monitor = monitor

    def set_tls_monitor(self, monitor) -> None:
        self._tls_monitor = monitor

    def set_device_tracker(self, tracker) -> None:
        self._device_tracker = tracker

    def get_tls_stats(self) -> dict:
        return dict(self._tls_stats)

    async def start(self) -> None:
        """Check prerequisites, then start Npcap AsyncSniffer and flow reaper."""
        self._loop = asyncio.get_running_loop()

        if not _check_admin():
            raise RuntimeError(
                "Windows live capture requires Administrator privileges. "
                "Restart AnomalyNet as Administrator (right-click → Run as administrator)."
            )

        if not _check_npcap_available():
            raise RuntimeError(
                "Npcap is not installed or Scapy cannot enumerate network interfaces. "
                "Install Npcap from https://npcap.com/ and restart."
            )

        await self._aggregator.start()

        try:
            from scapy.all import AsyncSniffer
        except ImportError as exc:
            raise RuntimeError("scapy is not installed. Run: pip install scapy") from exc

        # Load TLS layer so bind_layers(TCP, TLS, dport=443) is registered
        try:
            import scapy.layers.tls  # noqa: F401
        except Exception:
            pass

        # SSLSession (Scapy 2.5+) > TCPSession (Scapy 2.4+) > no session
        _TLSSession = None
        try:
            from scapy.layers.tls.session import SSLSession as _TLSSession  # type: ignore[assignment]
        except ImportError:
            try:
                from scapy.sessions import TCPSession as _TLSSession  # type: ignore[assignment]
            except ImportError:
                pass

        resolved = [_resolve_interface(iface) for iface in self._interfaces]
        _log.info("[Windows capture] interfaces: %s → resolved: %s", self._interfaces, resolved)

        iface_arg = resolved[0] if len(resolved) == 1 else resolved

        _bpf = f"({self._bpf_filter}) and (ip or ip6)" if self._bpf_filter else "ip or ip6"
        sniffer_kwargs: dict = dict(
            iface=iface_arg,
            filter=_bpf,
            prn=self._packet_callback,
            store=False,
        )
        _log.info("[Windows capture] BPF filter: %s", _bpf)
        if _TLSSession is not None:
            sniffer_kwargs["session"] = _TLSSession

        self._sniffer_kwargs = sniffer_kwargs
        self._sniffer = AsyncSniffer(**sniffer_kwargs)
        self._sniffer.start()
        _log.info("[Windows capture] sniffer started on %s", resolved)
        self._watchdog_task = asyncio.create_task(self._sniffer_watchdog())

    async def _sniffer_watchdog(self) -> None:
        """Restart sniffer if dead OR stuck (no packets for 90s)."""
        import time
        while True:
            await asyncio.sleep(30)
            if self._sniffer is None:
                return
            try:
                dead = not getattr(self._sniffer, "running", True)
                since_last = time.monotonic() - self._last_pkt_time
                stuck = self._last_pkt_time > 0 and since_last > 90
                if dead or stuck:
                    reason = "dead" if dead else f"stuck ({since_last:.0f}s no packets)"
                    _log.warning("[Windows capture] sniffer %s — restarting", reason)
                    try:
                        self._sniffer.stop(join=False)
                    except Exception:
                        pass
                    from scapy.all import AsyncSniffer
                    self._sniffer = AsyncSniffer(**self._sniffer_kwargs)
                    self._sniffer.start()
                    self._last_pkt_time = time.monotonic()
                    _log.info("[Windows capture] sniffer restarted")
            except Exception as exc:
                _log.error("[Windows capture] watchdog restart failed: %s", exc)

    async def stop(self) -> None:
        if self._watchdog_task is not None:
            self._watchdog_task.cancel()
            self._watchdog_task = None
        if self._sniffer is not None:
            try:
                self._sniffer.stop(join=False)
            except Exception:
                pass
            self._sniffer = None
        _log.info("[TLS stats] %s", self._tls_stats)
        await self._aggregator.stop()

    def _packet_callback(self, pkt) -> None:
        """Called by scapy in its capture thread — thread-safe via FlowAggregator lock."""
        import time
        self._last_pkt_time = time.monotonic()
        self._aggregator.ingest(pkt)
        if self._dns_monitor is not None:
            try:
                self._process_dns(pkt)
            except Exception:
                pass
        if self._tls_monitor is not None:
            try:
                self._process_tls(pkt)
            except Exception:
                pass
        if self._device_tracker is not None:
            try:
                self._process_passive_discovery(pkt)
            except Exception:
                pass

    def _process_passive_discovery(self, pkt) -> None:
        """Extract IP→MAC mapping from any frame for passive device discovery."""
        try:
            from scapy.layers.inet import IP
            from scapy.layers.l2 import ARP, Ether
        except ImportError:
            return
        mac = ""
        ip = ""
        hostname = ""
        if pkt.haslayer(ARP):
            arp = pkt[ARP]
            if arp.op in (1, 2) and arp.psrc and arp.psrc != "0.0.0.0":
                mac = arp.hwsrc
                ip = arp.psrc
        elif pkt.haslayer(Ether) and pkt.haslayer(IP):
            ip = pkt[IP].src
            mac = pkt[Ether].src
        if ip and mac:
            self._loop.call_soon_threadsafe(
                self._device_tracker.on_passive_arp, ip, mac, hostname
            )

    _QTYPE_MAP = {1: "A", 2: "NS", 5: "CNAME", 15: "MX", 16: "TXT", 28: "AAAA", 255: "ANY"}

    def _process_dns(self, pkt) -> None:
        """Extract DNS query from packet and pass to DnsMonitor (scapy thread)."""
        try:
            from scapy.layers.dns import DNS
            from scapy.layers.inet import IP
        except ImportError:
            return
        if not pkt.haslayer(DNS):
            return
        dns = pkt[DNS]
        if dns.qr != 0 or dns.qd is None:
            return
        src_ip = pkt[IP].src if pkt.haslayer(IP) else "0.0.0.0"
        try:
            qname_raw = dns.qd.qname
            domain = (qname_raw.decode() if isinstance(qname_raw, bytes) else qname_raw).rstrip(".")
            if not domain:
                return
            qtype = self._QTYPE_MAP.get(dns.qd.qtype, str(dns.qd.qtype))
        except Exception:
            return
        self._dns_monitor.on_dns_packet(src_ip, domain, qtype)

    _TLS_PORTS: frozenset[int] = frozenset({
        443, 8443, 465, 993, 995, 636,
        2087, 2096, 3269, 5671, 6514, 8883,
    })

    def _process_tls(self, pkt) -> None:
        """Extract TLS ClientHello fingerprint and pass to TLSMonitor (scapy thread)."""
        if not pkt.haslayer("IP") or not pkt.haslayer("TCP"):
            return
        dport = pkt["TCP"].dport
        if dport not in self._TLS_PORTS:
            return
        self._tls_stats["tls_ports_seen"] += 1

        if pkt.haslayer("Raw"):
            raw_load = bytes(pkt["Raw"].load)
            if raw_load and raw_load[0] == 0x16:
                self._tls_stats["raw_tls_like_seen"] += 1

        from app.tls.fingerprint import compute_tls_fingerprint_from_scapy
        fp = compute_tls_fingerprint_from_scapy(pkt)
        if fp is None:
            self._tls_stats["tls_parse_failed"] += 1
            return

        self._tls_stats["tls_fingerprint_seen"] += 1
        source = fp.get("ja4_source")
        if source == "scapy_tls":
            self._tls_stats["tls_parse_success_scapy"] += 1
        elif source == "raw_tcp":
            self._tls_stats["tls_parse_success_raw"] += 1

        src_ip: str = pkt["IP"].src
        dst_ip: str = pkt["IP"].dst
        alert = self._tls_monitor.on_fingerprint(src_ip, dst_ip, dport, fp)
        if alert is not None:
            self._tls_stats["tls_alerts_emitted"] += 1

    async def _on_flow_ready(self, record: FlowRecord) -> None:
        """Called by FlowAggregator when a flow is finalized."""
        try:
            raw_features = compute_cicflow_features(record)
        except Exception:
            return

        raw_features_cic2023 = None
        if self._detection_mode == "advanced":
            try:
                raw_features_cic2023 = compute_cic2023_features(record)
            except Exception:
                pass

        protocol = PROTO_MAP.get(record.protocol, "OTHER")
        n_fwd = len(record.fwd_lengths)
        n_bwd = len(record.bwd_lengths)
        total_bytes = int(sum(record.fwd_lengths) + sum(record.bwd_lengths))
        duration_ms = max(int((record.last_time - record.start_time) * 1000), 1)

        event = NormalizedFlowEvent(
            event_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            source=f"iface:{','.join(self._interfaces)}",
            direction="inbound",
            protocol=protocol,
            src_ip=record.src_ip,
            dst_ip=record.dst_ip,
            src_port=record.src_port,
            dst_port=record.dst_port,
            packet_count=max(n_fwd + n_bwd, 1),
            byte_count=max(total_bytes, 1),
            duration_ms=duration_ms,
            risk_hint=0.0,
            raw_features=raw_features,
            raw_features_cic2023=raw_features_cic2023,
        )

        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    async def next_event(self) -> NormalizedFlowEvent:
        return await self._queue.get()
