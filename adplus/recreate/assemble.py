"""Assembly: beat timeline in, 9:16 film out.

The whole point is that **timing is decided here, not by the model**.  Each
beat owns a fixed slot; the shot is trimmed or frozen into that slot, the
voice line is placed at the beat's start, and subtitle cards are overlaid on
the same windows.  If a shot is 4 seconds and the beat is 2.1, the cut wins —
the model's drift never reaches the timeline.

Audio: no native model audio survives (it is unusable Chinese); the voice is
TTS, with macOS ``say`` as the offline fallback so the pipeline still produces
a reviewable file when the TTS provider is down.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from adplus.recreate import media

FFMPEG = media.FFMPEG
_NO_WINDOW = media._NO_WINDOW  # same platform flag


def _run(args: list[str], *, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, creationflags=_NO_WINDOW)


def _tts(text: str, out: Path, *, voice: str | None = None) -> dict[str, Any]:
    """MiniMax speech-02 first, macOS ``say`` as the offline fallback."""
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        from adplus.recreate import speech

        profile = next((p for p in VOICE_PROFILES.values() if p["voice"] == voice), None)
        return speech.synthesize(
            text,
            out,
            voice=voice,
            speed=(profile or {}).get("speed", TTS_SPEED),
            pitch=(profile or {}).get("pitch", 0),
        )
    except Exception as exc:  # noqa: BLE001 - fall through to local voice
        first_error = f"{type(exc).__name__}: {exc}"[:160]
    try:
        from adplus import tts as local_tts

        local_tts.synthesize(text, out, voice="Tingting", language="zh-CN")
        return {"path": str(out), "provider": "local", "fallback_reason": first_error}
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"TTS unavailable: {first_error} / {type(exc).__name__}: {exc}") from exc


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _clip_to_slot(clip: Path, duration: float, out: Path, *, width: int = 720, height: int = 1280, fps: int = 24, keep_audio: bool = False) -> Path:
    """Trim (or freeze-extend) a shot into an exact slot.

    A still image needs ``-loop 1``; without it ffmpeg emits a single frame and
    the slot silently becomes zero-length.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    loop = ["-loop", "1"] if clip.suffix.lower() in IMAGE_SUFFIXES else []
    proc = _run(
        [FFMPEG, "-v", "error", "-y", *loop, "-i", str(clip), "-t", f"{duration:.3f}",
         "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={fps},setsar=1",
         *([] if keep_audio else ["-an"]),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         *(["-c:a", "aac", "-b:a", "160k", "-ar", "44100"] if keep_audio else []),
         str(out)]
    )
    if proc.returncode != 0 or not out.is_file():
        raise RuntimeError(f"failed to cut {clip.name}: {proc.stderr[:200]}")
    probe = media.probe(out)
    if probe["duration_s"] + 0.05 < duration:
        pad = duration - probe["duration_s"]
        padded = out.with_name(out.stem + "_padded.mp4")
        proc = _run(
            [FFMPEG, "-v", "error", "-y", "-i", str(out), "-vf", f"tpad=stop_mode=clone:stop_duration={pad:.3f}",
             "-t", f"{duration:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-pix_fmt", "yuv420p", str(padded)]
        )
        if proc.returncode == 0 and padded.is_file():
            return padded
    return out


def _subtitle_card(text: str, out: Path, *, width: int = 720, height: int = 1280) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    font_path = "/System/Library/Fonts/STHeiti Medium.ttc"
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    size = 44
    font = ImageFont.truetype(font_path, size)
    while draw.textlength(text, font=font) > width - 80 and size > 22:
        size -= 2
        font = ImageFont.truetype(font_path, size)
    tw = draw.textlength(text, font=font)
    x, y = (width - tw) / 2, height - 190
    draw.text((x + 3, y + 3), text, font=font, fill=(0, 0, 0, 200), stroke_width=6, stroke_fill=(0, 0, 0, 200))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255), stroke_width=5, stroke_fill=(0, 0, 0, 235))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def assemble(
    skeleton: dict[str, Any],
    script: dict[str, Any],
    shots: dict[str, Any],
    out_dir: str | Path,
    *,
    width: int = 720,
    height: int = 1280,
    fps: int = 24,
    voice: bool = True,
    audio_mode: str = "tts",
) -> dict[str, Any]:
    """Render the beat timeline into ``out_dir/final.mp4``.

    ``shots`` maps beat id -> {"clip": path} or {"image": path}; images become
    a still slot (useful for a dry run before spending on video).
    """
    out = Path(out_dir)
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)

    timeline: list[dict[str, Any]] = []
    pieces: list[Path] = []
    for beat in skeleton.get("beats") or []:
        beat_id = beat["id"]
        start, end = float(beat["start_s"]), float(beat["end_s"])
        duration = round(end - start, 3)
        source = shots.get(beat_id) or {}
        clip = source.get("clip")
        still = source.get("image")
        try:
            if clip and Path(clip).is_file():
                slot = _clip_to_slot(
                    Path(clip), duration, work / f"{beat_id}.mp4",
                    width=width, height=height, fps=fps, keep_audio=(audio_mode == "native"),
                )
            elif still and Path(still).is_file():
                slot = _clip_to_slot(Path(still), duration, work / f"{beat_id}.mp4", width=width, height=height, fps=fps)
            else:
                raise RuntimeError("no clip or image")
            pieces.append(slot)
            timeline.append({"beat": beat_id, "start_s": start, "end_s": end, "duration_s": duration, "clip": str(slot), "status": "ok"})
        except Exception as exc:  # noqa: BLE001 - report per beat, keep going
            timeline.append({"beat": beat_id, "start_s": start, "end_s": end, "duration_s": duration, "status": f"error: {exc}"[:160]})

    if not pieces:
        raise RuntimeError("no usable shots")

    concat_file = work / "concat.txt"
    concat_file.write_text("\n".join(f"file '{p.resolve()}'" for p in pieces), encoding="utf-8")
    base = work / "base.mp4"
    proc = _run([FFMPEG, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(base)])
    if proc.returncode != 0:
        proc = _run([FFMPEG, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(base)])
    if proc.returncode != 0:
        raise RuntimeError(f"concat failed: {proc.stderr[:300]}")

    voice_files: list[dict[str, Any]] = []
    if voice and audio_mode != "native":
        voice_files = _voice_lines(script, skeleton, work)

    beats_by_id = {beat["id"]: beat for beat in skeleton.get("beats") or []}
    subtitles: list[dict[str, Any]] = []
    for beat in script.get("beats") or []:
        text = " ".join(line["text"] for line in beat.get("lines") or [])
        if not text:
            continue
        span = beats_by_id.get(beat["id"]) or {}
        card = _subtitle_card(text, work / f"sub_{beat['id']}.png", width=width, height=height)
        subtitles.append(
            {
                "beat": beat["id"],
                "image": str(card),
                "start_s": float(span.get("start_s") or 0),
                "end_s": float(span.get("end_s") or 0),
            }
        )

    bed = _ambience(base, work) if (voice and audio_mode != "native") else None
    final = out / "final.mp4"
    _compose(
        base, voice_files, subtitles, final,
        width=width, height=height, fps=fps, ambience=bed, audio_mode=audio_mode,
    )
    plan = {
        "timeline": timeline,
        "voice": voice_files,
        "subtitles": subtitles,
        "output": str(final),
        "duration_s": round(media.probe(final)["duration_s"], 2) if final.is_file() else None,
    }
    (out / "timeline.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return plan


# Two characters must sound like two people.  Different voice IDs alone were
# only 140Hz vs 131Hz — indistinguishable.  Voice + pitch offset gives ~106Hz
# vs ~198Hz, which reads as an older man and a younger one.
VOICE_PROFILES = {
    "A": {
        "voice": os.environ.get("ADPLUS_TTS_VOICE_A", "male-qn-jingying"),
        "pitch": int(os.environ.get("ADPLUS_TTS_PITCH_A", "-4")),
        "speed": float(os.environ.get("ADPLUS_TTS_SPEED_A", "1.05")),
    },
    "B": {
        "voice": os.environ.get("ADPLUS_TTS_VOICE_B", "male-qn-qingse"),
        "pitch": int(os.environ.get("ADPLUS_TTS_PITCH_B", "3")),
        "speed": float(os.environ.get("ADPLUS_TTS_SPEED_B", "1.2")),
    },
}
LINE_GAP_S = 0.12
MAX_TEMPO = 1.6
TTS_SPEED = float(os.environ.get("ADPLUS_TTS_SPEED", "1.12"))


def _duration(path: Path) -> float:
    """Read duration from the container, not media.probe (which needs a video)."""
    proc = _run([media.FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], timeout=30)
    try:
        return float((proc.stdout or "").strip())
    except ValueError:
        return 0.0


def _voice_lines(script: dict[str, Any], skeleton: dict[str, Any], work: Path) -> list[dict[str, Any]]:
    """Synthesize one clip per dialogue line, placed back-to-back inside its beat.

    The previous version joined a beat's lines into one clip with a single
    voice.  That is what made two-speaker beats sound like one person talking
    to himself, and long lines could run past the next beat.  Here each line
    gets its own speaker voice and a cursor, so nothing overlaps and every line
    lands inside its beat window.
    """
    beats_by_id = {beat["id"]: beat for beat in skeleton.get("beats") or []}
    clips: list[dict[str, Any]] = []
    for beat in script.get("beats") or []:
        span = beats_by_id.get(beat["id"]) or {}
        beat_start = float(span.get("start_s") or 0.0)
        beat_end = float(span.get("end_s") or beat_start + float(beat.get("len_s") or 1.0))
        cursor = beat_start
        for index, line in enumerate(beat.get("lines") or []):
            text = str(line.get("text") or "").strip()
            if not text:
                continue
            speaker = str(line.get("speaker") or "A")[:1].upper()
            target = work / f"vo_{beat['id']}_{index}.mp3"
            try:
                profile = VOICE_PROFILES.get(speaker, VOICE_PROFILES["A"])
                info = _tts(text, target, voice=profile["voice"])
            except Exception as exc:  # noqa: BLE001
                clips.append({"beat": beat["id"], "error": f"{type(exc).__name__}: {exc}"[:160]})
                continue
            length = _duration(target)
            start_at = cursor
            available = beat_end - start_at
            if length and available > 0.3 and length > available:
                # A line must not bleed into the next beat: speed it up a little
                # rather than letting two speakers overlap.
                tempo = min(MAX_TEMPO, length / available)
                if tempo > 1.02:
                    fitted = _stretch(target, tempo, work / f"vo_{beat['id']}_{index}_fit.mp3")
                    if fitted:
                        target = fitted
                        length = _duration(target)
            if length and start_at + length > beat_end:
                start_at = max(beat_start, beat_end - length)
            clips.append(
                {
                    "beat": beat["id"],
                    "line": index,
                    "speaker": speaker,
                    "text": text,
                    "path": str(target),
                    "at_s": round(start_at, 3),
                    "len_s": round(length, 3),
                    "provider": info.get("provider"),
                    "voice": info.get("voice"),
                }
            )
            cursor = start_at + length + LINE_GAP_S
    return clips


def _ambience(base: Path, work: Path) -> Path | None:
    """A quiet outdoor bed so dialogue sits in a place, not in a studio.

    Generated locally (pink noise, low-passed) rather than downloaded: it only
    needs to fill the silence between lines without being identifiable.
    """
    length = media.probe(base)["duration_s"]
    bed = work / "ambience.wav"
    proc = _run(
        [
            FFMPEG, "-v", "error", "-y", "-f", "lavfi",
            "-i", f"anoisesrc=color=pink:amplitude=0.05:duration={length:.3f}",
            "-af", "highpass=f=180,lowpass=f=1400,aecho=0.8:0.5:90:0.25",
            "-ar", "44100", "-ac", "1", str(bed),
        ]
    )
    return bed if proc.returncode == 0 and bed.is_file() else None


def _stretch(source: Path, tempo: float, target: Path) -> Path | None:
    """Speed a voice clip up so it fits its beat (atempo keeps pitch)."""
    proc = _run([FFMPEG, "-v", "error", "-y", "-i", str(source), "-filter:a", f"atempo={tempo:.3f}", str(target)])
    return target if proc.returncode == 0 and target.is_file() else None


def _compose(base: Path, voice: list[dict[str, Any]], subtitles: list[dict[str, Any]], final: Path,
             *, width: int, height: int, fps: int, ambience: Path | None = None,
             audio_mode: str = "tts") -> None:
    """Overlay subtitles, mix the voice track, normalise loudness.

    Input indices are tracked explicitly: looped images add four argv tokens
    ("-loop 1 -i file"), so deriving the index from the argument count silently
    points at the wrong stream.
    """
    inputs: list[str] = ["-i", str(base)]
    next_input = 1
    filters: list[str] = []
    label = "0:v"

    for index, item in enumerate(subtitles):
        inputs += ["-loop", "1", "-i", item["image"]]
        stream = f"{next_input}:v"
        next_input += 1
        out_label = f"v{index}"
        filters.append(
            f"[{label}][{stream}]overlay=0:0:enable='between(t,{item['start_s']:.2f},{item['end_s']:.2f})'[{out_label}]"
        )
        label = out_label

    audio_inputs = [item for item in voice if item.get("path") and Path(item["path"]).is_file()]
    for index, item in enumerate(audio_inputs):
        inputs += ["-i", item["path"]]
        stream = f"{next_input}:a"
        next_input += 1
        delay = int(float(item.get("at_s") or 0) * 1000)
        filters.append(f"[{stream}]adelay={delay}|{delay},volume=1.0[a{index}]")

    if ambience and ambience.is_file():
        inputs += ["-i", str(ambience)]
        filters.append(f"[{next_input}:a]volume=0.7[aamb]")
        next_input += 1
        audio_inputs = audio_inputs + [{"path": str(ambience), "_label": "aamb"}]

    if audio_mode == "native":
        filters.append("[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[aout]")
        audio_map = ["-map", "[aout]"]
    elif audio_inputs:
        labels = []
        for index, item in enumerate(audio_inputs):
            labels.append(f"[{item.get('_label', f'a{index}')}]" if item.get("_label") else f"[a{index}]")
        mix = "".join(labels)
        filters.append(f"{mix}amix=inputs={len(labels)}:duration=longest:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[aout]")
        audio_map = ["-map", "[aout]"]
    else:
        audio_map = ["-an"]

    args = [FFMPEG, "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filters),
            "-map", f"[{label}]", *audio_map, "-t", f"{media.probe(base)['duration_s']:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(fps),
            "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-movflags", "+faststart", str(final)]
    proc = _run(args, timeout=900)
    if proc.returncode != 0:
        raise RuntimeError(f"compose failed: {proc.stderr[:400]}")


def _subtitle_groups(segments: list[dict[str, Any]], max_chars: int = 12) -> list[dict[str, Any]]:
    """Split ASR segments into short subtitle lines using word timings.

    Whole-segment subtitles hold a long line on screen after the speech has
    moved on; grouping by words keeps the text close to the voice.
    """
    words = [w for seg in segments for w in (seg.get("words") or [])]
    if not words:
        return segments

    groups: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []

    def flush() -> None:
        if not current:
            return
        groups.append(
            {
                "start": round(float(current[0]["start"]), 3),
                "end": round(float(current[-1]["end"]), 3),
                "text": "".join(str(w.get("word") or "") for w in current).strip(),
            }
        )
        current.clear()

    for word in words:
        text = str(word.get("word") or "")
        if not text:
            continue
        length = sum(len(str(w.get("word") or "")) for w in current)
        if current and length + len(text) > max_chars:
            flush()
        if current and float(word.get("start") or 0) - float(current[-1].get("end") or 0) > 0.45:
            flush()
        current.append(word)
        if text.endswith(("。", "！", "？", "，", "、", "；")):
            flush()
    flush()
    return [group for group in groups if group["text"]]


def _subtitles_from_script(segments: list[dict[str, Any]], script: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Time each written line against the spoken words.

    The text always comes from the script (ASR mishears brand names), while the
    timing comes from word timestamps: consume words until they cover the
    line's length, then take that span.
    """
    words = sorted(
        [w for seg in segments for w in (seg.get("words") or [])],
        key=lambda w: float(w.get("start") or 0),
    )
    lines = [str(line.get("text") or "") for beat in (script or {}).get("beats") or [] for line in beat.get("lines") or []]
    lines = [line for line in lines if line]
    if not words or not lines:
        return []

    out: list[dict[str, Any]] = []
    cursor = 0
    for line in lines:
        if cursor >= len(words):
            break
        target = max(1, len(line))
        start_word = words[cursor]
        collected = 0
        end_index = cursor
        while end_index < len(words) and collected < target * 0.85:
            collected += len(str(words[end_index].get("word") or ""))
            end_index += 1
        if end_index == cursor:
            end_index = cursor + 1
        end_word = words[min(end_index, len(words)) - 1]
        out.append(
            {
                "start": round(float(start_word.get("start") or 0), 3),
                "end": round(float(end_word.get("end") or 0), 3),
                "text": line,
            }
        )
        cursor = end_index
    return out


def _align_to_script(groups: list[dict[str, Any]], script: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Replace ASR text with the script line when they clearly match.

    Whisper mishears brand words ("鹰嘴豆" -> "银嘴豆"), and that typo would be
    burned into the video.  Where a group corresponds to a script line, the
    written text wins; timing still comes from the audio.
    """
    from difflib import SequenceMatcher

    lines = [str(line.get("text") or "") for beat in (script or {}).get("beats") or [] for line in beat.get("lines") or []]
    lines = [line for line in lines if line]
    if not lines:
        return groups

    used: set[int] = set()
    for group in groups:
        text = group["text"]
        best, best_score = None, 0.0
        for index, line in enumerate(lines):
            if index in used:
                continue
            score = SequenceMatcher(None, text, line).ratio()
            if score > best_score:
                best, best_score = index, score
        if best is not None and best_score >= 0.55 and 0.5 <= len(text) / max(1, len(lines[best])) <= 1.8:
            group["text"] = lines[best]
            used.add(best)
    return groups


def assemble_oneshot(
    clip: str | Path,
    segments: list[dict[str, Any]],
    out_dir: str | Path,
    *,
    width: int = 720,
    height: int = 1280,
    fps: int = 24,
    script: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Take a single dialogue clip and burn subtitles timed from its own audio.

    The model paces itself, so the script's beat grid cannot be used for
    subtitle timing; the ASR segments are the timeline.
    """
    out = Path(out_dir)
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)
    source = Path(clip)
    duration = media.probe(source)["duration_s"]
    base = _clip_to_slot(source, duration, work / "oneshot_base.mp4",
                         width=width, height=height, fps=fps, keep_audio=True)

    # Prefer written lines timed by word stamps; fall back to ASR grouping.
    groups = _subtitles_from_script(segments, script) or _align_to_script(_subtitle_groups(segments), script)
    subtitles: list[dict[str, Any]] = []
    for index, seg in enumerate(groups):
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        card = _subtitle_card(text, work / f"os_sub_{index}.png", width=width, height=height)
        subtitles.append({"beat": f"s{index}", "image": str(card),
                          "start_s": float(seg["start"]), "end_s": float(seg["end"])})

    final = out / "final.mp4"
    _compose(base, [], subtitles, final, width=width, height=height, fps=fps, audio_mode="native")
    plan = {"timeline": [{"beat": "oneshot", "duration_s": round(duration, 2), "status": "ok"}],
            "voice": [], "subtitles": subtitles, "output": str(final),
            "duration_s": round(media.probe(final)["duration_s"], 2)}
    (out / "timeline.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return plan
