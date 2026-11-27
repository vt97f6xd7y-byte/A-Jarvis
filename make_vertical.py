#!/usr/bin/env python3
"""Turn a 1920x1080 Twitch clip into a 1080x1920 vertical video.

Webcam on top, gameplay on the bottom, word-by-word captions on the seam.

Usage:
  python3 make_vertical.py OUT_DIR CLIP.mp4 [CLIP2.mp4 ...] [--cam WxH]

--cam sets the webcam box size in the top-left corner of the source
(default 494x276, Lacy's usual overlay). Needs ffmpeg and faster-whisper.
"""
import argparse, json, os, re, subprocess, sys, tempfile, wave

import numpy as np

OUT_W, CAM_H, GAME_H = 1080, 840, 1080
SEAM_Y = CAM_H
HALLUCINATIONS = {"thank you.", "thanks for watching!", "you're welcome.", "you", "bye."}


def ts(t):
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def transcribe(model, path):
    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, "a.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-ac", "1", "-ar", "16000", wav], check=True)
        w = wave.open(wav)
        audio = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    segs, _ = model.transcribe(audio, word_timestamps=True, condition_on_previous_text=False,
                               no_speech_threshold=None, log_prob_threshold=None, beam_size=5)
    words = []
    for s in segs:
        if s.text.strip().lower() in HALLUCINATIONS or s.avg_logprob < -1.2:
            continue
        for x in s.words:
            t = x.word.strip()
            if not t:
                continue
            if words and re.fullmatch(r"[%!?.,']+\S*", t):  # glue "%!" etc to previous word
                words[-1] = (words[-1][0], x.end, words[-1][2] + t)
            else:
                words.append((x.start, x.end, t))
    return words


def clean(words):
    """Drop whisper's stuck-loop output: runs of 3+ words squeezed onto one timestamp."""
    out = []
    i = 0
    while i < len(words):
        j = i
        while j + 1 < len(words) and abs(words[j + 1][0] - words[i][0]) < 0.05 and words[j + 1][1] - words[j + 1][0] < 0.05:
            j += 1
        if j - i >= 2:
            i = j + 1
            continue
        out.append(tuple(words[i]))
        i += 1
    return out


def chunk(words, max_words=3, max_chars=16):
    chunks, cur = [], []
    for i, w in enumerate(words):
        if cur and (len(cur) == max_words
                    or len(" ".join(c[2] for c in cur + [w])) > max_chars
                    or w[0] - cur[-1][1] > 0.6):
            chunks.append(cur); cur = []
        cur.append(w)
        if w[2].endswith(("!", "?", ".")):
            chunks.append(cur); cur = []
    if cur:
        chunks.append(cur)
    return chunks


def write_ass(words, path):
    hdr = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,DejaVu Sans,88,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,4,5,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    pop = r"{\fscx80\fscy80\t(0,90,\fscx105\fscy105)\t(90,160,\fscx100\fscy100)}"
    yel, wht = r"{\c&H00E5FF&}", r"{\c&HFFFFFF&}"
    cs = chunk(clean(words))
    lines = []
    for i, c in enumerate(cs):
        end = c[-1][1] + 0.5
        if i + 1 < len(cs):
            end = min(end, cs[i + 1][0][0])
        for j, (ws, we, _) in enumerate(c):
            we2 = c[j + 1][0] if j + 1 < len(c) else max(end, we)
            txt = " ".join((yel + x[2].upper() + wht) if k == j else x[2].upper() for k, x in enumerate(c))
            lines.append(f"Dialogue: 0,{ts(ws)},{ts(we2)},Cap,,0,0,0,,{{\\pos(540,{SEAM_Y})}}{pop if j == 0 else ''}{txt}")
    with open(path, "w") as f:
        f.write(hdr + "\n".join(lines) + "\n")


def render(src, ass, out, cam_w, cam_h, game=None):
    # webcam: inset a few px to skip the overlay border, crop to the top panel's aspect, centered
    ch = cam_h - 4
    cw = round(ch * OUT_W / CAM_H)
    cx = max(0, (cam_w - cw) // 2)
    # game: square from the middle, below the chat box and above the bottom HUD / stream captions
    gx = 590 if cam_w > 520 else 570
    gy, gs = 160, 780  # stops above the stream's own captions and in-game subtitles (~y950)
    if game:  # manual override "x,y,size" for clips where the action sits elsewhere
        gx, gy, gs = game
    fc = (f"[0:v]crop={cw}:{ch}:{cx}:2,scale={OUT_W}:{CAM_H}:flags=lanczos,setsar=1[cam];"
          f"[0:v]crop={gs}:{gs}:{gx}:{gy},scale={OUT_W}:{GAME_H}:flags=lanczos,setsar=1[game];"
          f"[cam][game]vstack=inputs=2,ass={ass}[v]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-filter_complex", fc, "-map", "[v]", "-map", "0:a",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("clips", nargs="+")
    ap.add_argument("--cam", default="494x276")
    ap.add_argument("--model", default="medium.en")
    ap.add_argument("--game", help="game crop override x,y,size (square, source pixels)")
    ap.add_argument("--reuse", action="store_true", help="reuse saved transcripts, only re-render")
    a = ap.parse_args()
    cam_w, cam_h = map(int, a.cam.split("x"))
    os.makedirs(a.out_dir, exist_ok=True)
    game = tuple(map(int, a.game.split(","))) if a.game else None
    model = None
    if not a.reuse:
        from faster_whisper import WhisperModel
        model = WhisperModel(a.model, device="cpu", compute_type="int8")
    for src in a.clips:
        name = os.path.splitext(os.path.basename(src))[0]
        wpath = os.path.join(a.out_dir, name + ".words.json")
        if a.reuse:
            words = json.load(open(wpath))
        else:
            words = transcribe(model, src)
            json.dump(words, open(wpath, "w"))
        ass = os.path.join(a.out_dir, name + ".ass")
        write_ass(words, ass)
        render(src, ass, os.path.join(a.out_dir, name + ".mp4"), cam_w, cam_h, game)
        print("done", name, len(words), "words", flush=True)


if __name__ == "__main__":
    sys.exit(main())
