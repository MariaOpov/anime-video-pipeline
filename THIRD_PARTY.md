# Third-party tools and assets

This repository does not redistribute Piper, Rhubarb Lip Sync, Piper voice
models, or FFmpeg binaries. Setup scripts install or download them into ignored
local directories.

## Piper

- Project: OHF-Voice Piper
- License: GPL-3.0
- Use: offline text-to-speech subprocess

## Rhubarb Lip Sync

- Project: DanielSWolf/rhubarb-lip-sync
- License: MIT
- Use: offline WAV-to-mouth-cue subprocess

## Demo Vietnamese voice

- Model: `vi_VN-vais1000-medium`
- Dataset: VAIS-1000 Vietnamese Speech Synthesis Corpus
- Dataset license: CC BY 4.0
- Attribution is required when the generated voice is used in distributed work.

Voice licenses differ. Review each voice's `MODEL_CARD` before replacing the
demo voice, especially for commercial projects.

## imageio-ffmpeg and FFmpeg

- Wrapper project: imageio/imageio-ffmpeg
- Wrapper license: BSD-2-Clause
- Use: locate a project-local FFmpeg executable for Phase 4 finishing
- FFmpeg license: depends on the bundled build and enabled codecs; inspect with
  `ffmpeg -L` when distributing a binary

`setup_phase4.ps1` installs the wheel inside the ignored `.venv`. Neither the
wrapper package nor its FFmpeg executable is committed to this repository.
