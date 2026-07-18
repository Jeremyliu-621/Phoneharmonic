// ONE vocabulary for what the conductor's hand did. The engine reports the
// device it ACTUALLY engaged each bar (ENGINE_STATE `device`); every surface —
// the moves card, the wand panel, the camera flash — speaks these exact words.
// No client-side guessing: if the engine didn't do it, we don't say it.

const BY_HEAD = {
  // song-mode devices (the arrangement layer)
  hush: { icon: "🤫", label: "Hush — softer & simpler" },
  swelling: { icon: "🙌", label: "Swelling up…" },
  harmonize: { icon: "⚡", label: "Harmony layer added" },
  arpeggio: { icon: "🎶", label: "Arpeggios sprinkled in" },
  passing: { icon: "🏃", label: "Runs between the notes" },
  // free-play devices (the built-in loop's responder line)
  lower_imitation: { icon: "🎻", label: "Lower imitation" },
  contrary_motion: { icon: "🔀", label: "Contrary motion" },
  sustained: { icon: "🌊", label: "Sustained chords" },
  delayed: { icon: "🫧", label: "Delayed echo" },
  rhythmic_dense: { icon: "🥁", label: "Busy rhythm" },
  rest: { icon: "🤫", label: "Rest — silence" },
  generated: { icon: "🤖", label: "AI-written line" },
};

export function effectLabel(device) {
  if (!device || device === "verbatim") return { icon: "🎼", label: "As written" };
  // devices compose as "<head> · <detail>" (arpeggio · theory, sustained ·
  // octave up, …) — name the head; an octave detail is worth saying out loud.
  const parts = String(device).split("·").map((s) => s.trim());
  const base = BY_HEAD[parts[0]] || { icon: "✨", label: parts[0].replace(/_/g, " ") };
  const oct = parts.find((p) => p.startsWith("octave"));
  if (oct) return { icon: base.icon, label: `${base.label} — ${oct === "octave up" ? "⬆" : "⬇"} an ${oct}` };
  return base;
}
