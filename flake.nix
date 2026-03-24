{
  description = "midimixer — per-app MIDI volume control for Linux";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }: let
    system = "x86_64-linux";
    pkgs   = nixpkgs.legacyPackages.${system};

    midimixer = pkgs.python3Packages.buildPythonApplication {
      pname   = "midimixer";
      version = "0.1.0";

      src = ./.;

      # Tell the builder where main.py lives (no setup.py / pyproject.toml)
      format = "other";

      buildInputs = with pkgs; [ alsa-lib pulseaudio ];

      propagatedBuildInputs = with pkgs.python3Packages; [
        pyside6
        mido
        python-rtmidi
        pulsectl
      ];

      # Wrap the entry point manually since we're not using setuptools
      installPhase = ''
        mkdir -p $out/lib/midimixer $out/bin

        cp ${./main.py}    $out/lib/midimixer/main.py
        cp ${./audio.py}   $out/lib/midimixer/audio.py
        cp ${./midi.py}    $out/lib/midimixer/midi.py
        cp ${./mapping.py} $out/lib/midimixer/mapping.py
        cp ${./gui.py}     $out/lib/midimixer/gui.py

        makeWrapper ${pkgs.python3}/bin/python $out/bin/midimixer \
          --add-flags "$out/lib/midimixer/main.py" \
          --set PYTHONPATH "$out/lib/midimixer:${pkgs.python3Packages.makePythonPath (with pkgs.python3Packages; [ pyside6 mido python-rtmidi pulsectl ])}"
      '';

      nativeBuildInputs = [ pkgs.makeWrapper ];

      meta = {
        description = "Per-app MIDI volume mixer for PipeWire/PulseAudio";
        homepage    = "https://github.com/YOUR_USERNAME/midimixer";
        license     = pkgs.lib.licenses.mit;
        mainProgram = "midimixer";
      };
    };

  in {
    packages.${system}.default = midimixer;
    packages.${system}.midimixer = midimixer;

    # Keep the dev shell working
    devShells.${system}.default = import ./shell.nix { inherit pkgs; };
  };
}
