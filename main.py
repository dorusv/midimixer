"""
main.py — midimixer entry point. Runs as a system tray application.
"""

import sys
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QPainter, QColor, QPixmap, QPen, QBrush
from PySide6.QtCore import Qt

from audio import AudioManager
from midi import MidiListener
from mapping import MappingConfig


def make_tray_icon() -> QIcon:
    """Draw a simple mixer icon: three vertical fader lines."""
    size = 22
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)

    amber = QColor("#c8860a")
    dim   = QColor("#555555")

    # Three fader tracks
    track_w, track_h = 3, 14
    positions = [3, 9, 15]   # x positions
    handles   = [4, 10, 7]   # y positions of handles (varied heights)

    for x, hy in zip(positions, handles):
        # Track background
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(dim))
        p.drawRoundedRect(x, 4, track_w, track_h, 1, 1)
        # Handle
        p.setBrush(QBrush(amber))
        p.drawRoundedRect(x - 1, hy, track_w + 2, 4, 1, 1)

    p.end()
    return QIcon(px)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("midimixer")
    # Don't quit when the last window is closed — we live in the tray
    app.setQuitOnLastWindowClosed(False)

    audio  = AudioManager()
    config = MappingConfig()
    midi   = MidiListener(port_name=config.midi_port)

    from gui import MixerWindow
    window = MixerWindow(audio=audio, config=config, midi=midi)

    # --- Tray icon ---
    icon = make_tray_icon()
    tray = QSystemTrayIcon(icon, parent=app)
    tray.setToolTip("midimixer")

    menu = QMenu()
    show_action = menu.addAction("Show / Hide")
    menu.addSeparator()
    quit_action = menu.addAction("Quit")
    tray.setContextMenu(menu)

    def toggle_window():
        if window.isVisible():
            window.hide()
        else:
            window.show()
            window.raise_()
            window.activateWindow()

    def quit_app():
        tray.hide()
        window._poll_timer.stop()
        midi.stop()
        audio.close()
        app.quit()

    tray.activated.connect(lambda reason:
        toggle_window() if reason == QSystemTrayIcon.Trigger else None)
    show_action.triggered.connect(toggle_window)
    quit_action.triggered.connect(quit_app)

    tray.show()

    # --- MIDI ---
    midi.add_cc_callback(window.emit_cc)
    midi.add_note_callback(window.emit_note)
    midi.start()

    # Start audio event listener + volume enforcer threads
    audio.add_event_callback(window.emit_sink_event)
    audio.start_event_listener()

    ports = midi.available_ports()
    if ports:
        print(f"[midi] Available ports: {ports}")
    else:
        print("[midi] No MIDI ports found — running in GUI-only mode.")

    # Sync LEDs to saved state on startup
    for note, binding in config.all_button_bindings().items():
        if binding.type == "function":
            midi.set_led(note, config.get_function(binding.target))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
