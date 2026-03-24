"""
mapping.py — Binds MIDI CC and note numbers to audio targets and functions.

Config format:
{
  "midi_port": "nanoKONTROL2",
  "mappings": {
    "0": "__master__",
    "1": "Spotify"
  },
  "button_mappings": {
    "53": {"type": "mute",     "target": "Spotify"},
    "49": {"type": "function", "name":   "my_func"}
  },
  "volumes": {
    "__master__": 0.8,
    "Spotify": 0.6
  },
  "functions": {
    "my_func": false
  }
}

Note: button_mappings keys are CC numbers (same protocol as fader mappings).
The nanoKONTROL2 and most Korg controllers use control_change for buttons.
"""

import json
from pathlib import Path
from dataclasses import dataclass
from typing import Literal, Optional

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "midimixer" / "config.json"

MASTER = "__master__"


@dataclass
class ButtonBinding:
    type: Literal["mute", "function"]
    # for mute: the app name or MASTER; for function: the function name
    target: str


class MappingConfig:
    def __init__(self, path: Path = DEFAULT_CONFIG_PATH):
        self.path = path
        self.midi_port: Optional[str] = None
        self.mappings: dict[int, str] = {}              # cc → target
        self.button_mappings: dict[int, ButtonBinding] = {}  # note → ButtonBinding
        self.volumes: dict[str, float] = {}             # target → volume
        self.functions: dict[str, bool] = {}            # function name → on/off state
        self._load()

    # ------------------------------------------------------------------
    # CC fader bindings
    # ------------------------------------------------------------------

    def target_for_cc(self, cc: int) -> Optional[str]:
        return self.mappings.get(cc)

    def bind(self, cc: int, target: str) -> None:
        self.mappings[cc] = target
        self._save()

    def unbind(self, cc: int) -> None:
        self.mappings.pop(cc, None)
        self._save()

    def all_bindings(self) -> dict[int, str]:
        return dict(self.mappings)

    # ------------------------------------------------------------------
    # Button bindings
    # ------------------------------------------------------------------

    def binding_for_note(self, note: int) -> Optional[ButtonBinding]:
        return self.button_mappings.get(note)

    def bind_button(self, note: int, binding: ButtonBinding) -> None:
        self.button_mappings[note] = binding
        self._save()

    def unbind_button(self, note: int) -> None:
        self.button_mappings.pop(note, None)
        self._save()

    def all_button_bindings(self) -> dict[int, ButtonBinding]:
        return dict(self.button_mappings)

    def note_for_binding(self, btype: str, target: str) -> Optional[int]:
        """Reverse lookup: find the note bound to a specific action."""
        for note, b in self.button_mappings.items():
            if b.type == btype and b.target == target:
                return note
        return None

    # ------------------------------------------------------------------
    # Functions (named on/off toggles)
    # ------------------------------------------------------------------

    def get_function(self, name: str) -> bool:
        return self.functions.get(name, False)

    def set_function(self, name: str, state: bool) -> None:
        self.functions[name] = state
        self._save()

    def toggle_function(self, name: str) -> bool:
        new_state = not self.functions.get(name, False)
        self.functions[name] = new_state
        self._save()
        return new_state

    def all_functions(self) -> dict[str, bool]:
        return dict(self.functions)

    # ------------------------------------------------------------------
    # Volume memory
    # ------------------------------------------------------------------

    def remember_volume(self, target: str, volume: float) -> None:
        self.volumes[target] = round(volume, 4)
        self._save()

    def recalled_volume(self, target: str) -> Optional[float]:
        return self.volumes.get(target)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
            self.midi_port = data.get("midi_port")
            raw = data.get("mappings", {})
            self.mappings = {int(k): v for k, v in raw.items()}
            self.volumes = data.get("volumes", {})
            self.functions = data.get("functions", {})
            raw_buttons = data.get("button_mappings", {})
            self.button_mappings = {
                int(k): ButtonBinding(type=v["type"], target=v.get("target") or v.get("name", ""))
                for k, v in raw_buttons.items()
            }
        except Exception as e:
            print(f"[mapping] Failed to load config: {e}")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw_buttons = {}
        for note, b in self.button_mappings.items():
            if b.type == "mute":
                raw_buttons[str(note)] = {"type": "mute", "target": b.target}
            else:
                raw_buttons[str(note)] = {"type": "function", "name": b.target}
        data = {
            "midi_port": self.midi_port,
            "mappings": {str(k): v for k, v in self.mappings.items()},
            "button_mappings": raw_buttons,
            "volumes": self.volumes,
            "functions": self.functions,
        }
        self.path.write_text(json.dumps(data, indent=2))
