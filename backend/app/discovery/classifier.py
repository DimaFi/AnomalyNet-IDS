from __future__ import annotations

_VENDOR_TYPE_MAP: list[tuple[str, str]] = [
    # IP cameras
    ("hikvision",  "iot_camera"),
    ("reolink",    "iot_camera"),
    ("dahua",      "iot_camera"),
    ("axis",       "iot_camera"),
    ("hanwha",     "iot_camera"),
    ("vivotek",    "iot_camera"),
    ("foscam",     "iot_camera"),
    # Routers / gateways
    ("tp-link",    "router"),
    ("tplink",     "router"),
    ("asus",       "router"),
    ("netgear",    "router"),
    ("d-link",     "router"),
    ("dlink",      "router"),
    ("mikrotik",   "router"),
    ("ubiquiti",   "router"),
    ("cisco",      "router"),
    ("zyxel",      "router"),
    ("huawei",     "router"),
    ("keenetic",   "router"),
    # IoT sensors / MCUs
    ("espressif",  "iot_sensor"),
    ("arduino",    "iot_sensor"),
    ("raspberry",  "iot_sensor"),
    ("particle",   "iot_sensor"),
    ("tuya",       "iot_sensor"),
    # Smart lights
    ("philips",    "iot_bulb"),
    ("signify",    "iot_bulb"),
    ("lifx",       "iot_bulb"),
    ("yeelight",   "iot_bulb"),
    ("nanoleaf",   "iot_bulb"),
    # Smart plugs
    ("tp-link kasa", "iot_plug"),
    # PCs / servers
    ("microsoft",  "pc_windows"),
    ("dell",       "pc_windows"),
    ("hp",         "pc_windows"),
    ("lenovo",     "pc_windows"),
    ("intel",      "pc_windows"),
    ("realtek",    "pc_windows"),
    # Apple devices
    ("apple",      "pc_mac"),
    # Linux / servers
    ("canonical",  "pc_linux"),
    ("supermicro", "pc_linux"),
    # Phones
    ("samsung",    "phone"),
    ("xiaomi",     "phone"),
    ("oneplus",    "phone"),
    ("oppo",       "phone"),
    ("vivo",       "phone"),
    # Printers
    ("xerox",      "printer"),
    ("canon",      "printer"),
    ("epson",      "printer"),
    ("brother",    "printer"),
    ("lexmark",    "printer"),
    # NAS
    ("synology",   "nas"),
    ("qnap",       "nas"),
    ("western digital", "nas"),
    # Game consoles
    ("nintendo",   "game_console"),
    ("sony interactive", "game_console"),
    ("microsoft xbox", "game_console"),
    # Smart TVs
    ("lg electronics", "tv"),
    ("samsung tv", "tv"),
    ("sony",       "tv"),
    ("hisense",    "tv"),
]

_HOSTNAME_PREFIX_MAP: list[tuple[str, str]] = [
    ("cam",        "iot_camera"),
    ("camera",     "iot_camera"),
    ("ipcam",      "iot_camera"),
    ("nvr",        "iot_camera"),
    ("dvr",        "iot_camera"),
    ("router",     "router"),
    ("gateway",    "router"),
    ("gw",         "router"),
    ("ap-",        "router"),
    ("sensor",     "iot_sensor"),
    ("esp",        "iot_sensor"),
    ("arduino",    "iot_sensor"),
    ("rpi",        "iot_sensor"),
    ("pi-",        "iot_sensor"),
    ("hue",        "iot_bulb"),
    ("lifx",       "iot_bulb"),
    ("plug",       "iot_plug"),
    ("switch",     "iot_plug"),
    ("desktop",    "pc_windows"),
    ("laptop",     "pc_windows"),
    ("pc-",        "pc_windows"),
    ("win-",       "pc_windows"),
    ("iphone",     "phone"),
    ("ipad",       "phone"),
    ("android",    "phone"),
    ("pixel",      "phone"),
    ("galaxy",     "phone"),
    ("printer",    "printer"),
    ("nas",        "nas"),
    ("diskstation","nas"),
    ("ps4",        "game_console"),
    ("ps5",        "game_console"),
    ("xbox",       "game_console"),
    ("switch",     "game_console"),
    ("bravia",     "tv"),
    ("appletv",    "tv"),
    ("firetv",     "tv"),
    ("roku",       "tv"),
]

_PORT_TYPE_MAP: dict[int, str] = {
    554:  "iot_camera",   # RTSP
    8554: "iot_camera",
    80:   None,           # too generic
    443:  None,
    22:   "pc_linux",     # SSH
    3389: "pc_windows",   # RDP
    445:  "pc_windows",   # SMB
    9100: "printer",      # JetDirect
    631:  "printer",      # IPP
    548:  "pc_mac",       # AFP
    5353: None,           # mDNS
    1900: None,           # SSDP
    8080: None,
}


def guess_device_type(
    vendor: str = "",
    hostname: str = "",
    open_ports: list[int] | None = None,
) -> str:
    v = vendor.lower()
    h = hostname.lower()
    ports = open_ports or []

    for kw, dtype in _VENDOR_TYPE_MAP:
        if kw in v:
            return dtype

    for prefix, dtype in _HOSTNAME_PREFIX_MAP:
        if h.startswith(prefix) or prefix in h:
            return dtype

    for port in ports:
        mapped = _PORT_TYPE_MAP.get(port)
        if mapped:
            return mapped

    return "unknown"
