"""
midi.py — MIDI input/output using mido + python-rtmidi backend.

Listens for CC (knobs/faders) and note_on (buttons) messages.
Sends note_on back to the device to control LEDs.
"""

import threading
import mido
from typing import Callable, Optional


CCCallback   = Callable[[int, int], None]   # (cc_number, value 0-127)
NoteCallback = Callable[[int], None]        # (note_number) — fires on button press


class MidiListener:
    def __init__(self, port_name: Optional[str] = None):
        self._port_name = port_name
        self._in_port  = None
        self._out_port = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._cc_callbacks:   list[CCCallback]   = []
        self._note_callbacks: list[NoteCallback] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def available_ports(self) -> list[str]:
        return mido.get_input_names()

    def add_cc_callback(self, cb: CCCallback) -> None:
        self._cc_callbacks.append(cb)

    # Legacy alias so main.py keeps working unchanged
    def add_callback(self, cb: CCCallback) -> None:
        self.add_cc_callback(cb)

    def add_note_callback(self, cb: NoteCallback) -> None:
        self._note_callbacks.append(cb)

    def set_led(self, cc: int, on: bool, channel: int = 0) -> None:
        """Light or extinguish the LED for a button by CC number.
        nanoKONTROL2 uses control_change to control LEDs (same CC as the button).
        Falls back to note_on for controllers that use note-based LEDs.
        """
        if self._out_port is None:
            return
        value = 127 if on else 0
        try:
            self._out_port.send(mido.Message("control_change", channel=channel,
                                             control=cc, value=value))
        except Exception as e:
            print(f"[midi] LED send error: {e}")

    def start(self) -> None:
        ports_in  = mido.get_input_names()
        ports_out = mido.get_output_names()

        if not ports_in:
            print("[midi] No MIDI input ports found.")
            return

        name = self._port_name if self._port_name in ports_in else ports_in[0]
        print(f"[midi] Opening input:  {name}")
        self._in_port = mido.open_input(name)

        # Try to open a matching output port for LED feedback
        out_name = next((p for p in ports_out if name.split(":")[0] in p), None)
        if out_name:
            print(f"[midi] Opening output: {out_name}")
            self._out_port = mido.open_output(out_name)
        else:
            print("[midi] No matching output port found — LEDs disabled.")

        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._in_port:
            self._in_port.close()
        if self._out_port:
            self._out_port.close()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _listen(self) -> None:
        for msg in self._in_port:
            if not self._running:
                break
            if msg.type == "control_change":
                for cb in self._cc_callbacks:
                    cb(msg.control, msg.value)
            elif msg.type == "note_on":
                # Many controllers (incl. nanoKONTROL2) send note_on vel=0 for press.
                # Fire on any note_on regardless of velocity.
                for cb in self._note_callbacks:
                    cb(msg.note)
            elif msg.type == "note_off":
                # Some controllers send a real note_off — treat as press too.
                for cb in self._note_callbacks:
                    cb(msg.note)
