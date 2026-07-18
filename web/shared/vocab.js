// ONE vocabulary for what the conductor's hand did. The engine reports the
// device it ACTUALLY engaged each bar (ENGINE_STATE `device`); every surface —
// the moves card, the wand panel, the camera flash — speaks these exact words.
// No client-side guessing: if the engine didn't do it, we don't say it.

export function effectLabel(device) {
  if (!device || device === "verbatim") return { icon: "🎼", label: "As written" };
  if (device === "hush") return { icon: "🤫", label: "Hush — softer & simpler" };
  if (device === "swelling") return { icon: "🙌", label: "Swelling up…" };
  // harmony devices come as "<style> · <source>" (harmonize · pad, arpeggio ·
  // theory, passing · model, …) — name the style, the source is a detail.
  const style = device.split(" ·")[0].trim();
  const BY_STYLE = {
    harmonize: { icon: "⚡", label: "Harmony layer added" },
    arpeggio: { icon: "🎶", label: "Arpeggios sprinkled in" },
    passing: { icon: "🏃", label: "Runs between the notes" },
  };
  return BY_STYLE[style] || { icon: "✨", label: device };
}
