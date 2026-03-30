# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Run the application:**
```bash
nix-shell --run "python main.py"
# or inside nix-shell:
python main.py
```

**Build with Nix:**
```bash
nix build
```

**Enter development shell:**
```bash
nix-shell
```

There are no automated tests or linting configured.

## Architecture

MIDI Mixer maps MIDI controller knobs/faders to per-application PulseAudio/PipeWire volume controls on Linux. It runs as a Qt system tray application.

### Components

**`main.py`** — Entry point. Initializes Qt app, system tray icon, instantiates the three core managers and the GUI window, wires Qt signals between components.

**`audio.py` (`AudioManager`)** — Wraps `pulsectl` to control PulseAudio/PipeWire sink inputs (per-app audio streams). Runs two background threads:
- *Event thread*: detects apps connecting/disconnecting via PulseAudio event subscription
- *Enforce thread*: polls every 0.2s and corrects volume drift if an app changes its own volume

**`midi.py` (`MidiListener`)** — Wraps `mido` + `python-rtmidi`. Runs a listener thread that dispatches CC messages (knobs/faders) and note on/off messages (buttons) to registered callbacks. Sends CC/note_on back to controller for LED feedback.

**`mapping.py` (`MappingConfig`)** — JSON persistence at `~/.config/midimixer/config.json`. Stores CC→app bindings (one CC can map to multiple app names), button→action bindings, volume memory, and toggleable function states. Auto-upgrades legacy single-string mappings to list format.

**`gui.py` (`MixerWindow`, `FaderStrip`, `ActionButton`)** — PySide6 dark UI. Fader strips have a vertical slider and a CC bind button. Clicking the bind button enters learn mode: the next MIDI CC or note received binds to that control. Uses Qt signal/slot pattern to bridge MIDI/audio threads safely to the GUI thread.

### Thread model

- **Main thread**: Qt event loop + GUI rendering
- **Audio event thread**: blocks on PulseAudio event subscription
- **Audio enforce thread**: polling loop (0.2s interval)
- **MIDI listener thread**: blocks on `mido` port read

### Config format (`~/.config/midimixer/config.json`)

```json
{
  "midi_port": "APC Key 25",
  "mappings": {
    "0": ["__master__"],
    "1": ["Firefox", "Spotify"]
  },
  "button_mappings": {
    "53": {"type": "mute", "target": "Spotify"},
    "49": {"type": "function", "name": "my_func"}
  },
  "volumes": {"__master__": 0.8, "Spotify": 0.6},
  "functions": {"my_func": false}
}
```

The special target `__master__` controls the PulseAudio master sink volume. Omitting `midi_port` causes auto-selection of the first available MIDI port.
