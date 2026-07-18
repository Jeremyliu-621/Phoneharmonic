// The orchestra's pixel performers (web/assets/<name>.png — the elegant
// full-body set). Every instrument the engine can deal has a musician;
// anything unknown gets the synth player.
const ARTISTS = ["violin", "viola", "cello", "bass", "flute", "clarinet",
  "trumpet", "harp", "bell", "drums", "piano", "synth"];

export const artistFor = (inst) =>
  `../assets/${ARTISTS.includes(inst) ? inst : "synth"}.png`;
