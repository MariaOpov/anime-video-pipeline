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

## FastAPI and Uvicorn

- FastAPI license: MIT
- Uvicorn license: BSD-3-Clause
- Use: project-local Phase 6 HTTP application and ASGI development server

They are installed inside `.venv` by `setup_phase6.ps1` and are not
redistributed by this repository.

## Ollama

- Project: Ollama
- Use: optional local structured-output motion planning

Ollama and model weights are not installed or redistributed by Phase 6. Review
the license of the selected Ollama model before distributing derived content.

## mmd_tools and production models

- Project: MMD-Blender/blender_mmd_tools
- License: MIT
- Use: local PMX/PMD import and MMD model representation in Blender

Phase 7 does not download or redistribute `mmd_tools`, PMX/PMD files, textures,
or cached model data. Character licenses are independent of the importer and
must be reviewed before publishing renders or sharing any source asset.
