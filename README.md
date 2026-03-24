# midimixer


Just to preface, this whole project (including the rest of this readme) is created by an LLM so I could just get it working quickly for my personal use.



A MIDI Mixer clone for Linux. Maps MIDI CC knobs/faders to per-application
PulseAudio/PipeWire volume controls.

## Requirements

- PipeWire with `pipewire-pulse` (standard on NixOS/Wayland) **or** PulseAudio
- A MIDI controller with knobs or faders

## Setup

```bash
nix-shell        # drops you into the dev environment
python main.py   # launch
```

## Usage

1. Open the app — a fader strip appears for each active audio stream plus a **MASTER** strip.
2. Click a strip's CC button (shows `--` if unbound) to enter **learn mode**.
3. Move a knob or fader on your MIDI controller — it binds automatically.
4. The binding is saved to `~/.config/midimixer/config.json`.

## Config file

```json
{
  "midi_port": "APC Key 25",
  "mappings": {
    "0": "__master__",
    "1": "Firefox",
    "2": "Spotify"
  }
}
```

- `midi_port`: optional, pins a specific MIDI device by name. Leave null to use the first available.
- `mappings`: CC number → application name (or `__master__` for master output volume).

## Project structure

```
midimixer/
├── shell.nix      # Nix dev shell (Python + deps)
├── main.py        # Entry point
├── audio.py       # pulsectl wrapper (sink input control)
├── midi.py        # mido MIDI listener thread
├── mapping.py     # CC→target config, JSON persistence
└── gui.py         # PySide6 vertical fader UI
```

## Adding to your NixOS flake

If you want to add this as a proper package later, the dependencies to declare are:
`python3Packages.pyside6`, `python3Packages.mido`, `python3Packages.python-rtmidi`,
`python3Packages.pulsectl`, `alsa-lib`, `pulseaudio`.


Restart service:
`systemctl --user restart midimixer`

List PipeWire sinks:
`pw-dump | grep -A2 "application.name"`
