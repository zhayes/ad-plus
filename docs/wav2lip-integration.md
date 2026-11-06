# Local Wav2Lip integration

## Why

`avatar-spokesperson` needs a real lip-sync take even when cloud providers are
unavailable. Wav2Lip is a local fallback, not a quality answer.

## Install layout

```text
vendor/wav2lip/                    # clone, untracked
checkpoints/wav2lip_gan.pth        # gdown 15G3U08c8xsCkOqQxE38Z2XXDnPcOptNk
face_detection/detection/sfd/s3fd.pth
.venv-wav2lip/                     # Python 3.11, torch CPU
```

`adplus/local_tools.py` auto-detects this layout, sets `WAV2LIP_PATH`, and puts
the Python 3.11 venv first on `PATH` so the OpenMontage `lip_sync` tool's
`python inference.py` resolves correctly.

## Compatibility patches (vendor, untracked)

Wav2Lip's 2021 code needs three small patches for Python 3.11 / torch 2.x /
librosa 0.11:

1. `audio.py`: `librosa.filters.mel(sr=..., n_fft=..., ...)`
2. `inference.py`: `torch.load(..., map_location="cpu", weights_only=False)`
3. `inference.py`: if the checkpoint loads as a TorchScript archive, use
   `{"state_dict": checkpoint.state_dict()}`.

These are compatibility patches, not model changes.

## Verified take

```text
input: 480x720 still loop, 25fps
audio: macOS Tingting TTS, 6.57s
output: 480x720 h264/aac, 6.57s
stages: idea → script → scene_plan → assets → edit → compose → publish
```

Evidence:

- `docs/verification/p1-wav2lip-6s.mp4`
- `docs/verification/p1-wav2lip-6s.jpg`
- `docs/verification/p1-checkpoints.json`

## Limits

- mouth-only; identity/head motion/background do not improve
- 480x720, not 480x854 9:16
- CPU inference is slow (minutes per few seconds)
- no product truth; product plate remains separate
