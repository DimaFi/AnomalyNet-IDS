export const DEVICE_EMOJI: Record<string, string> = {
  iot_camera:   "📷",
  iot_sensor:   "📡",
  iot_bulb:     "💡",
  iot_plug:     "🔌",
  router:       "🌐",
  pc_windows:   "💻",
  pc_linux:     "🐧",
  pc_mac:       "🍎",
  phone:        "📱",
  printer:      "🖨",
  nas:          "💾",
  game_console: "🎮",
  tv:           "📺",
  unknown:      "❓",
};

export function deviceEmoji(deviceType: string | null | undefined): string {
  if (!deviceType) return "❓";
  return DEVICE_EMOJI[deviceType] ?? "❓";
}
