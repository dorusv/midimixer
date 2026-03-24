"""
audio.py — PulseAudio/PipeWire sink input control via pulsectl.

Works on both PulseAudio and PipeWire (via pipewire-pulse compat layer).
"""

import time
import threading
import pulsectl
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class SinkInput:
    index: int
    name: str          # application name
    volume: float      # 0.0 – 1.0
    muted: bool


# Called whenever a sink input is added or removed: (facility, index)
EventCallback = Callable[[str, int], None]

# How often the enforcer thread checks and corrects volumes (seconds)
_ENFORCE_INTERVAL = 0.2


class AudioManager:
    def __init__(self):
        self._pulse = pulsectl.Pulse("midimixer")
        self._pulse_events = pulsectl.Pulse("midimixer-events")
        self._pulse_enforce = pulsectl.Pulse("midimixer-enforce")
        self._event_callbacks: list[EventCallback] = []
        self._event_thread: Optional[threading.Thread] = None
        self._enforce_thread: Optional[threading.Thread] = None
        self._running = False

        # app name -> target volume; enforcer keeps all matching streams at this level
        self._enforced: dict[str, float] = {}
        self._enforce_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Volume enforcement
    # ------------------------------------------------------------------

    def set_enforced_volume(self, app_name: str, volume: float) -> None:
        """Register a volume that should always be maintained for this app."""
        with self._enforce_lock:
            self._enforced[app_name] = volume

    def clear_enforced_volume(self, app_name: str) -> None:
        with self._enforce_lock:
            self._enforced.pop(app_name, None)

    def _enforce_loop(self) -> None:
        """Poll all sink inputs and correct any that have drifted from target."""
        while self._running:
            try:
                with self._enforce_lock:
                    targets = dict(self._enforced)

                if targets:
                    for si in self._pulse_enforce.sink_input_list():
                        name = (
                            si.proplist.get("application.name")
                            or si.proplist.get("media.name")
                            or ""
                        )
                        if name in targets:
                            current = self._pulse_enforce.volume_get_all_chans(si)
                            target = targets[name]
                            if abs(current - target) > 0.01:
                                self._pulse_enforce.volume_set_all_chans(si, target)
            except Exception as e:
                print(f"[audio] Enforcer error: {e}")

            time.sleep(_ENFORCE_INTERVAL)

    # ------------------------------------------------------------------
    # Event listener
    # ------------------------------------------------------------------

    def add_event_callback(self, cb: EventCallback) -> None:
        self._event_callbacks.append(cb)

    def start_event_listener(self) -> None:
        self._running = True

        self._event_thread = threading.Thread(target=self._event_loop, daemon=True)
        self._event_thread.start()

        self._enforce_thread = threading.Thread(target=self._enforce_loop, daemon=True)
        self._enforce_thread.start()

    def _event_loop(self) -> None:
        def handler(ev):
            if ev.facility == "sink_input":
                for cb in self._event_callbacks:
                    cb(ev.facility, ev.index)

        self._pulse_events.event_mask_set("sink_input")
        self._pulse_events.event_callback_set(handler)
        try:
            while self._running:
                self._pulse_events.event_listen(timeout=1.0)
        except Exception as e:
            print(f"[audio] Event loop error: {e}")

    # ------------------------------------------------------------------
    # Audio control
    # ------------------------------------------------------------------

    def get_sink_inputs(self) -> list[SinkInput]:
        inputs = []
        for si in self._pulse.sink_input_list():
            name = (
                si.proplist.get("application.name")
                or si.proplist.get("media.name")
                or f"stream-{si.index}"
            )
            vol = self._pulse.volume_get_all_chans(si)
            inputs.append(SinkInput(
                index=si.index,
                name=name,
                volume=min(vol, 1.5),
                muted=bool(si.mute),
            ))
        return inputs

    def get_master_volume(self) -> float:
        sink = self._default_sink()
        if sink is None:
            return 1.0
        return self._pulse.volume_get_all_chans(sink)

    def set_sink_input_volume(self, index: int, volume: float) -> None:
        volume = max(0.0, min(volume, 1.0))
        try:
            si = self._pulse.sink_input_info(index)
            self._pulse.volume_set_all_chans(si, volume)
        except pulsectl.PulseOperationFailed:
            pass

    def set_master_volume(self, volume: float) -> None:
        volume = max(0.0, min(volume, 1.0))
        sink = self._default_sink()
        if sink:
            self._pulse.volume_set_all_chans(sink, volume)

    def toggle_mute_sink_input(self, index: int) -> Optional[bool]:
        try:
            si = self._pulse.sink_input_info(index)
            new_mute = not si.mute
            self._pulse.sink_input_mute(index, new_mute)
            return new_mute
        except pulsectl.PulseOperationFailed:
            return None

    def _default_sink(self):
        server_info = self._pulse.server_info()
        default_name = server_info.default_sink_name
        for sink in self._pulse.sink_list():
            if sink.name == default_name:
                return sink
        return None

    def close(self):
        self._running = False
        self._pulse.close()
        self._pulse_events.close()
        self._pulse_enforce.close()
