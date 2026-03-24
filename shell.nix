{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  name = "midimixer";

  buildInputs = with pkgs; [
    # Python + runtime deps
    (python3.withPackages (ps: with ps; [
      pyside6
      mido
      python-rtmidi
      pulsectl
    ]))

    # Native libs needed by rtmidi and pulsectl
    alsa-lib
    rtmidi
    pulseaudio # provides libpulse for pulsectl even on PipeWire systems
  ];

  shellHook = ''
    echo "🎚  midimixer dev shell ready"
    echo "    run:  python main.py"
  '';
}
