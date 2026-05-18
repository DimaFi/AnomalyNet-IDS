"""
Linux live capture adapter using scapy.

Requires:
  - scapy installed: pip install scapy
  - Root privileges or CAP_NET_RAW: sudo uvicorn ...

Packets are captured by scapy's AsyncSniffer in a background thread.
call_soon_threadsafe bridges scapy callbacks to the asyncio event loop.
Completed flows are pushed into an asyncio.Queue and served via next_event().
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

_log = logging.getLogger("app.capture.linux")

from app.capture.base import CaptureAdapter
from app.contracts.schemas import NormalizedFlowEvent
from app.capture.adapters.linux.flow_aggregator import FlowAggregator
from app.capture.adapters.linux.feature_computer import compute_cicflow_features
from app.capture.adapters.linux.feature_computer_cic2023 import compute_cic2023_features
from app.capture.adapters.linux.flow_record import FlowRecord


PROTO_MAP = {6: "TCP", 17: "UDP", 1: "ICMP"}


class LinuxScapyAdapter(CaptureAdapter):
    mode = "linux_live"
    name = "Linux Scapy Live Capture"

    def __init__(self, interfaces: list[str] | str = "eth0", detection_mode: str = "simple") -> None:
        self._interfaces: list[str] = [interfaces] if isinstance(interfaces, str) else interfaces
        self._detection_mode = detection_mode
        self._queue: asyncio.Queue[NormalizedFlowEvent] = asyncio.Queue(maxsize=500)
        self._aggregator = FlowAggregator(on_flow_complete=self._on_flow_ready)
        self._sniffer = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._dns_monitor = None   # set via set_dns_monitor() after construction
        self._tls_monitor = None   # set via set_tls_monitor() after construction
        self._device_tracker = None  # set via set_device_tracker() after construction
        self._tls_stats = {
            "tls_ports_seen": 0,        # TCP packets on any TLS port
            "raw_tls_like_seen": 0,     # raw bytes starting with 0x16
            "tls_fingerprint_seen": 0,  # successfully parsed ClientHello
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
        """Start scapy AsyncSniffer and flow reaper."""
        self._loop = asyncio.get_running_loop()
        await self._aggregator.start()

        try:
            from scapy.all import AsyncSniffer
        except ImportError as exc:
            raise RuntimeError(
                "scapy is not installed. Run: pip install scapy"
            ) from exc

        # Load TLS layer explicitly so bind_layers(TCP, TLS, dport=443) is registered.
        # Importing only scapy.layers.tls.handshake skips __init__.py where bind_layers lives.
        try:
            import scapy.layers.tls  # noqa: F401 — side-effect: registers TLS dissector
        except Exception:
            pass

        # Resolve the best available session class for TCP stream reassembly.
        # Without a session, packets arrive as IP/TCP/Raw and haslayer(TLSClientHello) is False.
        # SSLSession (Scapy 2.5+) > TCPSession (Scapy 2.4+) > no session (TLS won't work).
        _TLSSession = None
        try:
            from scapy.layers.tls.session import SSLSession as _TLSSession  # type: ignore[assignment]
        except ImportError:
            try:
                from scapy.sessions import TCPSession as _TLSSession  # type: ignore[assignment]
            except ImportError:
                pass

        iface_arg = self._interfaces[0] if len(self._interfaces) == 1 else self._interfaces

        sniffer_kwargs: dict = dict(
            iface=iface_arg,
            filter="ip",
            prn=self._packet_callback,
            store=False,
        )
        if _TLSSession is not None:
            sniffer_kwargs["session"] = _TLSSession

        self._sniffer = AsyncSniffer(**sniffer_kwargs)
        self._sniffer.start()

    async def stop(self) -> None:
        """Stop sniffer and aggregator.
        join=False avoids blocking on socket.recv() in the scapy capture thread."""
        if self._sniffer is not None:
            try:
                self._sniffer.stop(join=False)
            except Exception:
                pass
            self._sniffer = None
        _log.info("[TLS stats] %s", self._tls_stats)
        await self._aggregator.stop()

    def _packet_callback(self, pkt) -> None:
        """
        Called by scapy in its capture thread.
        ingest() is thread-safe (threading.Lock inside FlowAggregator) — call
        directly here so the asyncio event loop is NOT touched per-packet.
        This eliminates asyncio saturation under flood (2000+ pps).
        """
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
        """Passive device discovery from broadcast/multicast traffic.

        Works even with strict WiFi client isolation because:
        - ARP requests are L2 broadcast (AP always forwards)
        - DHCP is L2 broadcast (AP always forwards)
        - mDNS/SSDP/NetBIOS use multicast/broadcast (AP forwards)

        Priority order (best hostname wins):
        1. DHCP DISCOVER/REQUEST — MAC + hostname (option 12) + requested IP
        2. ARP — MAC + IP, no hostname
        3. mDNS/SSDP/NetBIOS — MAC + IP (+ name parsed from payload)
        4. Any Ethernet+IP frame — MAC + IP, no hostname
        """
        src_ip: str | None = None
        src_mac: str | None = None
        hostname: str = ""

        # ── 1. DHCP broadcast (op=1 DISCOVER, op=3 REQUEST) ─────────────────
        # Most informative: gives MAC + hostname in a single broadcast packet.
        # Fires when a device connects/reconnects to the network.
        try:
            if pkt.haslayer("BOOTP") and pkt.haslayer("Ether"):
                bootp = pkt["BOOTP"]
                # chaddr = client hardware address (MAC, 6 bytes)
                if bootp.chaddr and bootp.chaddr != b"\x00" * 16:
                    raw_mac = bootp.chaddr[:6]
                    src_mac = ":".join(f"{b:02X}" for b in raw_mac)
                    # ciaddr (client IP) may be 0.0.0.0 on DISCOVER
                    # use src IP from IP layer instead
                    if pkt.haslayer("IP") and pkt["IP"].src != "0.0.0.0":
                        src_ip = pkt["IP"].src
                    # Extract hostname from DHCP option 12
                    if pkt.haslayer("DHCP"):
                        for opt in pkt["DHCP"].options:
                            if isinstance(opt, tuple) and opt[0] == "hostname":
                                raw = opt[1]
                                hostname = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)
                                break
        except Exception:
            pass

        # ── 2. ARP request/reply (broadcast) ────────────────────────────────
        # Fires whenever a device needs to resolve a MAC address on the network.
        if src_ip is None:
            try:
                from scapy.layers.l2 import ARP
                if pkt.haslayer(ARP):
                    arp = pkt[ARP]
                    if arp.hwsrc and arp.psrc and arp.psrc != "0.0.0.0":
                        src_ip = arp.psrc
                        src_mac = arp.hwsrc
            except Exception:
                pass

        # ── 3. mDNS / SSDP / NetBIOS (multicast/broadcast) ─────────────────
        # mDNS  → 224.0.0.251:5353  (Apple, Linux, Android, Chromecasts)
        # SSDP  → 239.255.255.250:1900  (Windows, smart TVs, routers, printers)
        # NBNS  → x.x.x.255:137  (Windows NetBIOS name broadcasts)
        if src_ip is None:
            try:
                if pkt.haslayer("UDP") and pkt.haslayer("IP") and pkt.haslayer("Ether"):
                    udp = pkt["UDP"]
                    dst_port = udp.dport
                    if dst_port in (5353, 1900, 137):
                        src_ip = pkt["IP"].src
                        src_mac = pkt["Ether"].src
                        # mDNS: try to extract hostname from DNS PTR/A records
                        if dst_port == 5353 and not hostname:
                            try:
                                from scapy.layers.dns import DNS
                                if pkt.haslayer(DNS):
                                    dns = pkt[DNS]
                                    # Walk answer + additional records for A/AAAA PTR
                                    for section in (dns.an, dns.ar):
                                        rec = section
                                        while rec and rec.type != 0:
                                            if rec.type in (1, 28) and hasattr(rec, "rrname"):
                                                # A/AAAA record — rrname is the hostname
                                                name = rec.rrname
                                                if isinstance(name, bytes):
                                                    name = name.decode(errors="replace")
                                                name = name.rstrip(".")
                                                # Take only simple hostnames, skip _service._tcp.local
                                                if name and "._" not in name and ".local" in name:
                                                    hostname = name.replace(".local", "")
                                                    break
                                            rec = getattr(rec, "payload", None)
                                            if not hasattr(rec, "type"):
                                                break
                            except Exception:
                                pass
            except Exception:
                pass

        # ── 4. Any Ethernet+IP frame addressed to/from us ───────────────────
        if src_ip is None:
            try:
                if pkt.haslayer("Ether") and pkt.haslayer("IP"):
                    eth_src = pkt["Ether"].src
                    ip_src = pkt["IP"].src
                    if eth_src and eth_src not in ("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00"):
                        src_ip = ip_src
                        src_mac = eth_src
            except Exception:
                pass

        if src_ip and src_mac:
            self._device_tracker.on_passive_arp(src_ip, src_mac, hostname=hostname)

    _QTYPE_MAP = {1: "A", 2: "NS", 5: "CNAME", 15: "MX", 16: "TXT", 28: "AAAA", 255: "ANY"}

    def _process_dns(self, pkt) -> None:
        """Extract DNS query from packet and pass to DnsMonitor (scapy thread)."""
        try:
            from scapy.layers.dns import DNS, DNSQR
            from scapy.layers.inet import IP
        except ImportError:
            return
        if not pkt.haslayer(DNS):
            return
        dns = pkt[DNS]
        if dns.qr != 0 or dns.qd is None:  # only outgoing queries
            return
        src_ip = pkt[IP].src if pkt.haslayer(IP) else "0.0.0.0"
        try:
            qname_raw = dns.qd.qname
            domain = (qname_raw.decode() if isinstance(qname_raw, bytes) else qname_raw).rstrip(".")
            if not domain:
                return
            qtype_num = dns.qd.qtype
            qtype = self._QTYPE_MAP.get(qtype_num, str(qtype_num))
        except Exception:
            return
        self._dns_monitor.on_dns_packet(src_ip, domain, qtype)

    # Common TLS ports — covers HTTPS, SMTPS, IMAPS, POP3S, LDAPS,
    # AMQP TLS, MQTT TLS, RDP TLS, alternate HTTPS, syslog TLS.
    _TLS_PORTS: frozenset[int] = frozenset({
        443,    # HTTPS
        8443,   # alt-HTTPS
        465,    # SMTPS
        993,    # IMAPS
        995,    # POP3S
        636,    # LDAPS
        2087,   # cPanel HTTPS
        2096,   # cPanel webmail
        3269,   # LDAPS Global Catalog
        5671,   # AMQP TLS
        6514,   # Syslog TLS
        8883,   # MQTT TLS
    })

    def _process_tls(self, pkt) -> None:
        """Extract TLS ClientHello fingerprint and pass to TLSMonitor (scapy thread)."""
        if not pkt.haslayer("IP") or not pkt.haslayer("TCP"):
            return
        dport = pkt["TCP"].dport
        if dport not in self._TLS_PORTS:
            return
        self._tls_stats["tls_ports_seen"] += 1

        # Diagnostic: count raw packets that look like TLS handshake (0x16)
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
            return  # Skip malformed flows

        # Compute CIC2023 features only in advanced mode (saves CPU in simple mode)
        raw_features_cic2023 = None
        if self._detection_mode == "advanced":
            try:
                raw_features_cic2023 = compute_cic2023_features(record)
            except Exception:
                pass  # Missing secondary features → cascade will fallback to binary result

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
            pass  # Drop oldest event if queue is full under heavy traffic

    async def next_event(self) -> NormalizedFlowEvent:
        return await self._queue.get()
