"""
gui.py — PySide6 mixer GUI with vertical fader strips and button rows.

Aesthetic: dark industrial — think hardware rack unit meets terminal.
Monospace labels, amber accents, tight layout.
"""

from __future__ import annotations
from typing import Callable, Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSlider, QLabel, QPushButton, QSizePolicy, QScrollArea,
    QFrame, QInputDialog,
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject

from audio import AudioManager, SinkInput
from mapping import MappingConfig, ButtonBinding, MASTER


# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------

STYLESHEET = """
QMainWindow, QWidget#root {
    background: #111111;
}

QWidget#strip {
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 4px;
}

QWidget#strip:hover {
    border-color: #c8860a;
}

QLabel#app_name {
    color: #c8860a;
    font-family: "Iosevka", "Fira Mono", "Courier New", monospace;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1px;
}

QLabel#vol_label {
    color: #666666;
    font-family: "Iosevka", "Fira Mono", "Courier New", monospace;
    font-size: 10px;
}

QSlider::groove:vertical {
    background: #252525;
    width: 6px;
    border-radius: 3px;
}

QSlider::handle:vertical {
    background: #c8860a;
    border: none;
    height: 18px;
    width: 28px;
    margin: 0 -11px;
    border-radius: 3px;
}

QSlider::handle:vertical:hover {
    background: #e09a10;
}

QSlider::sub-page:vertical {
    background: #c8860a44;
    border-radius: 3px;
}

QPushButton#bind_btn {
    background: transparent;
    color: #444444;
    border: 1px solid #2a2a2a;
    border-radius: 3px;
    font-family: "Iosevka", "Fira Mono", monospace;
    font-size: 9px;
    padding: 2px 4px;
}

QPushButton#bind_btn:hover {
    color: #c8860a;
    border-color: #c8860a;
}

QPushButton#bind_btn[active="true"] {
    color: #c8860a;
    border-color: #c8860a55;
}

QPushButton#action_btn {
    background: #1a1a1a;
    color: #444444;
    border: 1px solid #2a2a2a;
    border-radius: 3px;
    font-family: "Iosevka", "Fira Mono", monospace;
    font-size: 9px;
    padding: 3px 6px;
    min-width: 60px;
}

QPushButton#action_btn:hover {
    color: #c8860a;
    border-color: #c8860a;
}

QPushButton#action_btn[state="on"] {
    background: #c8860a;
    color: #111111;
    border-color: #c8860a;
    font-weight: bold;
}

QPushButton#action_btn[note_bound="true"] {
    border-color: #c8860a55;
    color: #888888;
}

QScrollArea {
    border: none;
    background: #111111;
}

QLabel#title {
    color: #333333;
    font-family: "Iosevka", "Fira Mono", monospace;
    font-size: 10px;
    letter-spacing: 3px;
}

QLabel#section_label {
    color: #2a2a2a;
    font-family: "Iosevka", "Fira Mono", monospace;
    font-size: 9px;
    letter-spacing: 2px;
}
"""


# ---------------------------------------------------------------------------
# Signals bridge (MIDI → GUI thread safe)
# ---------------------------------------------------------------------------

class MixerSignals(QObject):
    cc_received          = Signal(int, int)   # cc, value
    note_received        = Signal(int)        # note number
    sink_input_changed   = Signal()


# ---------------------------------------------------------------------------
# Single fader strip widget
# ---------------------------------------------------------------------------

class FaderStrip(QWidget):
    def __init__(
        self,
        label: str,
        on_volume_change: Callable[[float], None],
        on_bind_request: Callable[[], None],
        cc_hint: Optional[int] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("strip")
        self.setFixedWidth(80)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self._on_volume_change = on_volume_change
        self._suppress_signal = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(4)

        cc_text = f"CC{cc_hint}" if cc_hint is not None else "-- "
        self.bind_btn = QPushButton(cc_text)
        self.bind_btn.setObjectName("bind_btn")
        self.bind_btn.setFixedHeight(18)
        self.bind_btn.clicked.connect(on_bind_request)
        if cc_hint is not None:
            self.bind_btn.setProperty("active", "true")
        layout.addWidget(self.bind_btn, alignment=Qt.AlignHCenter)

        self.slider = QSlider(Qt.Vertical)
        self.slider.setRange(0, 100)
        self.slider.setValue(100)
        self.slider.setTickPosition(QSlider.NoTicks)
        self.slider.valueChanged.connect(self._slider_moved)
        layout.addWidget(self.slider, stretch=1, alignment=Qt.AlignHCenter)

        self.vol_label = QLabel("100%")
        self.vol_label.setObjectName("vol_label")
        self.vol_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.vol_label)

        self.name_label = QLabel(label[:8])
        self.name_label.setObjectName("app_name")
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setToolTip(label)
        layout.addWidget(self.name_label)

    def set_volume(self, volume: float) -> None:
        self._suppress_signal = True
        self.slider.setValue(int(volume * 100))
        self.vol_label.setText(f"{int(volume * 100)}%")
        self._suppress_signal = False

    def set_cc(self, cc: Optional[int]) -> None:
        text = f"CC{cc}" if cc is not None else "-- "
        self.bind_btn.setText(text)
        self.bind_btn.setProperty("active", "true" if cc is not None else "false")
        self.bind_btn.style().unpolish(self.bind_btn)
        self.bind_btn.style().polish(self.bind_btn)

    def _slider_moved(self, value: int) -> None:
        if self._suppress_signal:
            return
        self.vol_label.setText(f"{value}%")
        self._on_volume_change(value / 100.0)


# ---------------------------------------------------------------------------
# Action button widget (mute or function)
# ---------------------------------------------------------------------------

class ActionButton(QWidget):
    """A labelled button with a note-bind indicator, used for mute/function rows."""

    def __init__(
        self,
        label: str,
        on_press: Callable[[], None],
        on_bind_request: Callable[[], None],
        note_hint: Optional[int] = None,
        parent=None,
    ):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        # The main action button
        self.btn = QPushButton(label[:10])
        self.btn.setObjectName("action_btn")
        self.btn.setProperty("state", "off")
        self.btn.setProperty("note_bound", "true" if note_hint is not None else "false")
        self.btn.setToolTip(label)
        self.btn.clicked.connect(on_press)
        layout.addWidget(self.btn)

        # Small note-bind indicator below
        note_text = f"N{note_hint}" if note_hint is not None else "·"
        self.note_btn = QPushButton(note_text)
        self.note_btn.setObjectName("bind_btn")
        self.note_btn.setFixedHeight(14)
        self.note_btn.setProperty("active", "true" if note_hint is not None else "false")
        self.note_btn.clicked.connect(on_bind_request)
        layout.addWidget(self.note_btn, alignment=Qt.AlignHCenter)

    def set_state(self, on: bool) -> None:
        self.btn.setProperty("state", "on" if on else "off")
        self.btn.style().unpolish(self.btn)
        self.btn.style().polish(self.btn)

    def set_note(self, note: Optional[int]) -> None:
        text = f"N{note}" if note is not None else "·"
        self.note_btn.setText(text)
        self.note_btn.setProperty("active", "true" if note is not None else "false")
        self.note_btn.style().unpolish(self.note_btn)
        self.note_btn.style().polish(self.note_btn)
        self.btn.setProperty("note_bound", "true" if note is not None else "false")
        self.btn.style().unpolish(self.btn)
        self.btn.style().polish(self.btn)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MixerWindow(QMainWindow):
    def __init__(self, audio: AudioManager, config: MappingConfig, midi=None):
        super().__init__()
        self.audio  = audio
        self.config = config
        self.midi   = midi   # for LED feedback
        self.signals = MixerSignals()

        self._strips: dict[str, FaderStrip] = {}
        self._sink_map: dict[str, int] = {}
        self._binding_target: Optional[str] = None   # CC learn target
        self._button_learn_target: Optional[tuple[str, str]] = None  # (type, target)

        # action button widgets: key = "mute:AppName" or "func:FuncName"
        self._action_btns: dict[str, ActionButton] = {}

        self.setWindowTitle("midimixer")
        self.setMinimumHeight(420)
        self.setStyleSheet(STYLESHEET)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(8)

        title = QLabel("MIDIMIXER")
        title.setObjectName("title")
        root_layout.addWidget(title, alignment=Qt.AlignLeft)

        # Fader scroll area
        self._scroll_content = QWidget()
        self._strips_layout = QHBoxLayout(self._scroll_content)
        self._strips_layout.setContentsMargins(0, 0, 0, 0)
        self._strips_layout.setSpacing(6)
        self._strips_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._scroll_content)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root_layout.addWidget(scroll, stretch=1)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #1e1e1e;")
        root_layout.addWidget(sep)

        # Button rows (mute + functions)
        btn_header_row = QHBoxLayout()
        mute_label = QLabel("MUTE")
        mute_label.setObjectName("section_label")
        btn_header_row.addWidget(mute_label)
        btn_header_row.addStretch()
        add_func_btn = QPushButton("+ function")
        add_func_btn.setObjectName("bind_btn")
        add_func_btn.setFixedHeight(16)
        add_func_btn.clicked.connect(self._add_function_dialog)
        btn_header_row.addWidget(add_func_btn)
        root_layout.addLayout(btn_header_row)

        self._btns_widget = QWidget()
        self._btns_layout = QHBoxLayout(self._btns_widget)
        self._btns_layout.setContentsMargins(0, 0, 0, 0)
        self._btns_layout.setSpacing(4)
        self._btns_layout.addStretch()
        root_layout.addWidget(self._btns_widget)

        # Status bar
        self._status = QLabel("")
        self._status.setObjectName("vol_label")
        root_layout.addWidget(self._status)

        # Signals
        self.signals.cc_received.connect(self._on_cc)
        self.signals.note_received.connect(self._on_note)
        self.signals.sink_input_changed.connect(self._refresh_strips)

        self._add_master_strip()

        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._refresh_strips)
        self._poll_timer.start(1500)
        self._refresh_strips()

        # Build button rows from saved config
        self._rebuild_action_buttons()

    # ------------------------------------------------------------------
    # Fader strips
    # ------------------------------------------------------------------

    def _add_master_strip(self) -> None:
        cc = self._cc_for_target(MASTER)
        strip = FaderStrip(
            label="MASTER",
            on_volume_change=self._master_volume_changed,
            on_bind_request=lambda: self._start_learn(MASTER),
            cc_hint=cc,
        )
        recalled = self.config.recalled_volume(MASTER)
        if recalled is not None:
            self.audio.set_master_volume(recalled)
            strip.set_volume(recalled)
        else:
            strip.set_volume(self.audio.get_master_volume())
        self._strips_layout.insertWidget(0, strip)
        self._strips["master"] = strip

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: #2a2a2a;")
        self._strips_layout.insertWidget(1, sep)

    def _refresh_strips(self) -> None:
        sink_inputs = self.audio.get_sink_inputs()
        current_keys = {str(si.index) for si in sink_inputs}

        for key in list(self._strips.keys()):
            if key == "master":
                continue
            if key not in current_keys:
                strip = self._strips.pop(key)
                self._strips_layout.removeWidget(strip)
                strip.deleteLater()
                self._sink_map = {n: i for n, i in self._sink_map.items() if str(i) != key}

        for si in sink_inputs:
            key = str(si.index)
            if key not in self._strips:
                cc = self._cc_for_target(si.name)
                strip = FaderStrip(
                    label=si.name,
                    on_volume_change=lambda vol, idx=si.index, n=si.name: self._sink_volume_changed(idx, vol, n),
                    on_bind_request=lambda n=si.name: self._start_learn(n),
                    cc_hint=cc,
                )
                pos = self._strips_layout.count() - 1
                self._strips_layout.insertWidget(pos, strip)
                self._strips[key] = strip
                self._sink_map[si.name] = si.index

                recalled = self.config.recalled_volume(si.name)
                if recalled is not None:
                    self.audio.set_enforced_volume(si.name, recalled)
                    self.audio.set_sink_input_volume(si.index, recalled)
                    strip.set_volume(recalled)
                    # Refresh mute buttons now that this app is active
                    self._rebuild_action_buttons()
                    continue

            self._strips[key].set_volume(si.volume)

        if "master" in self._strips:
            self._strips["master"].set_volume(self.audio.get_master_volume())

    # ------------------------------------------------------------------
    # Action buttons (mute + functions)
    # ------------------------------------------------------------------

    def _rebuild_action_buttons(self) -> None:
        """Rebuild the entire action button row from config + active streams."""
        # Clear existing
        for key, btn in list(self._action_btns.items()):
            self._btns_layout.removeWidget(btn)
            btn.deleteLater()
        self._action_btns.clear()

        # Mute button per active sink input
        for name in list(self._sink_map.keys()):
            self._add_mute_button(name)

        # Function buttons
        for fname, state in self.config.all_functions().items():
            self._add_function_button(fname, state)

    def _add_mute_button(self, app_name: str) -> None:
        key = f"mute:{app_name}"
        if key in self._action_btns:
            return
        note = self.config.note_for_binding("mute", app_name)
        # Check current mute state
        muted = self._is_muted(app_name)
        btn = ActionButton(
            label=f"M {app_name[:8]}",
            on_press=lambda n=app_name: self._toggle_mute(n),
            on_bind_request=lambda n=app_name: self._start_button_learn("mute", n),
            note_hint=note,
        )
        btn.set_state(muted)
        pos = self._btns_layout.count() - 1
        self._btns_layout.insertWidget(pos, btn)
        self._action_btns[key] = btn

    def _add_function_button(self, fname: str, state: bool) -> None:
        key = f"func:{fname}"
        if key in self._action_btns:
            return
        note = self.config.note_for_binding("function", fname)
        btn = ActionButton(
            label=fname[:10],
            on_press=lambda n=fname: self._toggle_function(n),
            on_bind_request=lambda n=fname: self._start_button_learn("function", n),
            note_hint=note,
        )
        btn.set_state(state)
        pos = self._btns_layout.count() - 1
        self._btns_layout.insertWidget(pos, btn)
        self._action_btns[key] = btn

    def _add_function_dialog(self) -> None:
        name, ok = QInputDialog.getText(self, "New Function", "Function name:")
        if ok and name.strip():
            name = name.strip()
            self.config.set_function(name, False)
            self._add_function_button(name, False)

    # ------------------------------------------------------------------
    # Mute + function logic
    # ------------------------------------------------------------------

    def _is_muted(self, app_name: str) -> bool:
        idx = self._sink_map.get(app_name)
        if idx is None:
            return False
        for si in self.audio.get_sink_inputs():
            if si.index == idx:
                return si.muted
        return False

    def _toggle_mute(self, app_name: str) -> None:
        idx = self._sink_map.get(app_name)
        if idx is None:
            return
        new_mute = self.audio.toggle_mute_sink_input(idx)
        if new_mute is None:
            return
        key = f"mute:{app_name}"
        if key in self._action_btns:
            self._action_btns[key].set_state(new_mute)
        # LED feedback
        note = self.config.note_for_binding("mute", app_name)
        if note is not None and self.midi:
            self.midi.set_led(note, new_mute)

    def _toggle_function(self, fname: str) -> None:
        new_state = self.config.toggle_function(fname)
        key = f"func:{fname}"
        if key in self._action_btns:
            self._action_btns[key].set_state(new_state)
        # LED feedback
        note = self.config.note_for_binding("function", fname)
        if note is not None and self.midi:
            self.midi.set_led(note, new_state)

    # ------------------------------------------------------------------
    # Volume callbacks
    # ------------------------------------------------------------------

    def _master_volume_changed(self, vol: float) -> None:
        self.audio.set_master_volume(vol)
        self.config.remember_volume(MASTER, vol)

    def _sink_volume_changed(self, index: int, vol: float, name: str = "") -> None:
        self.audio.set_sink_input_volume(index, vol)
        if name:
            self.config.remember_volume(name, vol)
            self.audio.set_enforced_volume(name, vol)

    # ------------------------------------------------------------------
    # CC learn (faders/knobs)
    # ------------------------------------------------------------------

    def _start_learn(self, target: str) -> None:
        self._button_learn_target = None
        self._binding_target = target
        label = "MASTER" if target == MASTER else target
        self._status.setText(f"⏳ move a knob/fader → {label}")

    def _on_cc(self, cc: int, value: int) -> None:
        # Fader learn mode — grab next CC regardless of value
        if self._binding_target is not None:
            target = self._binding_target
            self._binding_target = None
            self.config.unbind(cc)
            self.config.bind(cc, target)
            self._update_bind_buttons()
            label = "MASTER" if target == MASTER else target
            self._status.setText(f"✓ CC{cc} → {label}")
            return

        # Button learn mode — only trigger on press (value=127)
        if self._button_learn_target is not None and value == 127:
            btype, target = self._button_learn_target
            self._button_learn_target = None
            self.config.unbind_button(cc)
            self.config.bind_button(cc, ButtonBinding(type=btype, target=target))
            self._update_action_btn_notes()
            self._status.setText(f"✓ CC{cc} → {btype}:{target}")
            if self.midi:
                state = (self.config.get_function(target) if btype == "function"
                         else self._is_muted(target))
                self.midi.set_led(cc, state)
            return

        # Button dispatch — CC bound as button, only fire on press (value=127)
        if value == 127:
            binding = self.config.binding_for_note(cc)
            if binding is not None:
                if binding.type == "mute":
                    self._toggle_mute(binding.target)
                elif binding.type == "function":
                    self._toggle_function(binding.target)
                return

        # Fader dispatch
        target = self.config.target_for_cc(cc)
        if target is None:
            return
        vol = value / 127.0

        if target == MASTER:
            self.audio.set_master_volume(vol)
            self.config.remember_volume(MASTER, vol)
            if "master" in self._strips:
                self._strips["master"].set_volume(vol)
        else:
            idx = self._sink_map.get(target)
            if idx is not None:
                self.audio.set_sink_input_volume(idx, vol)
                self.config.remember_volume(target, vol)
                self.audio.set_enforced_volume(target, vol)
                key = str(idx)
                if key in self._strips:
                    self._strips[key].set_volume(vol)

    # ------------------------------------------------------------------
    # Note learn (buttons) and dispatch
    # ------------------------------------------------------------------

    def _start_button_learn(self, btype: str, target: str) -> None:
        self._binding_target = None
        self._button_learn_target = (btype, target)
        self._status.setText(f"⏳ press a button → {btype}:{target}")

    def _on_note(self, note: int) -> None:
        # Learn mode
        if self._button_learn_target is not None:
            btype, target = self._button_learn_target
            self._button_learn_target = None
            # Remove old binding for this note if any
            self.config.unbind_button(note)
            self.config.bind_button(note, ButtonBinding(type=btype, target=target))
            # Update button note indicators
            self._update_action_btn_notes()
            self._status.setText(f"✓ N{note} → {btype}:{target}")
            # Light the LED to confirm
            if self.midi:
                state = (self.config.get_function(target) if btype == "function"
                         else self._is_muted(target))
                self.midi.set_led(note, state)
            return

        # Normal dispatch
        binding = self.config.binding_for_note(note)
        if binding is None:
            return

        if binding.type == "mute":
            self._toggle_mute(binding.target)
        elif binding.type == "function":
            self._toggle_function(binding.target)

    # ------------------------------------------------------------------
    # Sync UI labels
    # ------------------------------------------------------------------

    def _update_bind_buttons(self) -> None:
        bindings = self.config.all_bindings()
        reverse = {v: k for k, v in bindings.items()}
        if "master" in self._strips:
            self._strips["master"].set_cc(reverse.get(MASTER))
        for key, strip in self._strips.items():
            if key == "master":
                continue
            name = strip.name_label.toolTip()
            strip.set_cc(reverse.get(name))

    def _update_action_btn_notes(self) -> None:
        for key, btn in self._action_btns.items():
            btype, target = key.split(":", 1)
            note = self.config.note_for_binding(btype, target)
            btn.set_note(note)

    def _cc_for_target(self, target: str) -> Optional[int]:
        for cc, t in self.config.all_bindings().items():
            if t == target:
                return cc
        return None

    # ------------------------------------------------------------------
    # MIDI bridge (called from non-GUI thread)
    # ------------------------------------------------------------------

    def emit_cc(self, cc: int, value: int) -> None:
        self.signals.cc_received.emit(cc, value)

    def emit_note(self, note: int) -> None:
        self.signals.note_received.emit(note)

    def emit_sink_event(self, facility: str, index: int) -> None:
        self.signals.sink_input_changed.emit()

    def closeEvent(self, event):
        # Hide to tray instead of closing
        event.ignore()
        self.hide()
