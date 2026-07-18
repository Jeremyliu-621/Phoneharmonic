"""Session state: the orchestra roster, wand slot, and transport flag.

Kept deliberately small for P1 (sections + playing flag). Instrument
assignment, placement azimuths, and JSON persistence arrive with P2.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from engine_api import SectionInfo


@dataclass
class Section:
    section_id: str
    client_id: str
    instrument: str = "synth"
    azimuth_deg: float = 0.0
    connected: bool = True
    ready: bool = False


@dataclass
class WandSlot:
    connected: bool = False
    variant: str = "none"     # "sim" | "hw" | "none"
    aim_mode: str = "cycle"   # "cycle" (tap to select) | "yaw" (pointing)


@dataclass
class SessionState:
    name: str
    playing: bool = False
    sections: dict[str, Section] = field(default_factory=dict)  # keyed by section_id
    wand: WandSlot = field(default_factory=WandSlot)
    _next_section_num: int = 1

    def new_section_id(self) -> str:
        sid = f"s{self._next_section_num}"
        self._next_section_num += 1
        return sid

    def engine_sections(self) -> list[SectionInfo]:
        return [
            SectionInfo(s.section_id, s.instrument, s.azimuth_deg, s.ready)
            for s in self.sections.values()
            if s.connected
        ]

    def roster_payload(self) -> dict:
        return {
            "playing": self.playing,
            "sections": [
                {
                    "id": s.section_id,
                    "instrument": s.instrument,
                    "azimuth_deg": s.azimuth_deg,
                    "connected": s.connected,
                    "ready": s.ready,
                }
                for s in self.sections.values()
            ],
            "wand": {
                "connected": self.wand.connected,
                "variant": self.wand.variant,
                "aim_mode": self.wand.aim_mode,
            },
        }
