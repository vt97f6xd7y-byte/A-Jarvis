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
    opts = dict(word_timestamps=True, condition_on_previous_text=False,
                no_speech_threshold=None, log_prob_threshold=None, beam_size=5)
    try:
        segs = list(model.transcribe(audio, **opts)[0])
    except IndexError:  # faster-whisper alignment bug on empty segments; skip silence and retry
        segs = list(model.transcribe(audio, vad_filter=True, **opts)[0])
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


def write_ass(words, path, y=SEAM_Y):
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
            lines.append(f"Dialogue: 0,{ts(ws)},{ts(we2)},Cap,,0,0,0,,{{\\pos(540,{y})}}{pop if j == 0 else ''}{txt}")
    with open(path, "w") as f:
        f.write(hdr + "\n".join(lines) + "\n")


def probe_duration(src):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", src]).strip())


FACE_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "mmod_human_face_detector.dat")


def _face_detector():
    """dlib's CNN face detector (much better on small, dim webcams); OpenCV Haar cascades as a fallback."""
    try:
        import dlib
        if os.path.exists(FACE_MODEL):
            cnn = dlib.cnn_face_detection_model_v1(FACE_MODEL)

            def side_strips(rgb):
                # webcams sit in the outer quarter on the left or right; scan just those, upsampled so small cams register,
                # which also keeps mid-screen game characters out of the running
                w = rgb.shape[1]
                sw = int(w * 0.27)
                out = []
                for x0 in (0, w - sw):
                    strip = np.ascontiguousarray(rgb[:, x0:x0 + sw])
                    out += [(r.rect.left() + x0, r.rect.top(), r.rect.width(), r.rect.height()) for r in cnn(strip, 1)]
                return out
            return side_strips
    except ImportError:
        pass
    import cv2
    cascades = [cv2.CascadeClassifier(cv2.data.haarcascades + n) for n in
                ("haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml")]
    def haar(rgb):
        g = cv2.equalizeHist(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
        return [tuple(b) for c in cascades for b in c.detectMultiScale(g, 1.1, 5, minSize=(16, 16), maxSize=(200, 200))]
    return haar


def detect_cam(src, samples=12):
    """Find the streamer's face cam: a face that stays in the same spot across many sampled frames.

    Returns the face box (x, y, w, h) in 1920x1080 source pixels, or None if there's no face cam
    (avatar streamers, no-cam clips). Game characters move around and sit mid-screen, so clusters near
    the screen edges, where webcam overlays live, get a bonus.
    """
    W, H, k = 960, 540, 2
    detect = _face_detector()
    dur = probe_duration(src)
    hits = []
    for i in range(samples):
        t = dur * (i + 0.5) / samples
        raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{t:.2f}", "-i", src, "-frames:v", "1",
                              "-vf", f"scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
        if len(raw) != W * H * 3:
            continue
        for (x, y, w, h) in detect(np.frombuffer(raw, np.uint8).reshape(H, W, 3)):
            hits.append((i, x, y, w, h))
    clusters = []
    for hit in hits:
        i, x, y, w, h = hit
        for c in clusters:
            _, cx, cy, cw, _ = c[0]
            if abs((x + w / 2) - (cx + cw / 2)) < 0.9 * cw and abs((y + h / 2) - (cy + cw / 2)) < 0.9 * cw:
                c.append(hit); break
        else:
            clusters.append([hit])

    def score(c):
        n = len({h[0] for h in c})
        mx = np.median([h[1] + h[3] / 2 for h in c]) / W
        my = np.median([h[2] + h[4] / 2 for h in c]) / H
        edge = mx < 0.3 or mx > 0.7 or my < 0.3 or my > 0.75
        return n + (samples // 4 if edge else 0)

    good = [c for c in clusters if len({h[0] for h in c}) >= max(3, samples // 4)]
    if not good:
        return None
    best = max(good, key=score)
    return tuple(int(np.median([h[j] for h in best]) * k) for j in (1, 2, 3, 4))


def overlap(a, b):
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    return max(0, min(ax + aw, bx + bw) - max(ax, bx)) * max(0, min(ay + ah, by + bh) - max(ay, by))


def auto_layout(src, face=None):
    face = face or detect_cam(src)
    if face is None:
        return {"mode": "blur"}
    fx, fy, fw, fh = face
    ch = min(1080, int(fh * 3.4)) // 2 * 2
    cw = min(1920, int(ch * OUT_W / CAM_H)) // 2 * 2
    cx = int(min(max(fx + fw / 2 - cw / 2, 0), 1920 - cw))
    cy = int(min(max(fy - fh * 1.0, 0), 1080 - ch))
    # the webcam overlay itself is roughly face plus shoulders; keep the game crop off that, centered if possible
    foot = (fx - fw, fy - fh // 2, fw * 3, fh * 3)
    gy, gs = 150, 760
    options = [580, 760, 400, 1120, 40]
    gx = min(options, key=lambda x: (overlap(foot, (x, gy, gs, gs)) > 0.05 * fw * fh * 9, options.index(x)))
    return {"mode": "stack", "cam": (cx, cy, cw, ch), "game": (gx, gy, gs), "face": face}


def fixed_layout(cam_w, cam_h, game=None):
    """Webcam box of a known size in the top-left corner (Lacy's overlay)."""
    ch = cam_h - 4
    cw = round(ch * OUT_W / CAM_H)
    cx = max(0, (cam_w - cw) // 2)
    gx = 600 if cam_w > 520 else 580
    gy, gs = 150, 760  # ends at y910, above the stream captions and two-line in-game subtitles (~y925)
    return {"mode": "stack", "cam": (cx, 2, cw, ch), "game": game or (gx, gy, gs)}


BLUR_FG_H = 512  # 1920x910 game area scaled to 1080 wide
BLUR_FG_Y = (1920 - BLUR_FG_H) // 2


def caption_y(layout):
    return SEAM_Y if layout["mode"] == "stack" else BLUR_FG_Y + BLUR_FG_H + 130


def render(src, ass, out, layout):
    if layout["mode"] == "stack":
        cx, cy, cw, ch = layout["cam"]
        gx, gy, gs = layout["game"]
        fc = (f"[0:v]crop={cw}:{ch}:{cx}:{cy},scale={OUT_W}:{CAM_H}:flags=lanczos,setsar=1[cam];"
              f"[0:v]crop={gs}:{gs}:{gx}:{gy},scale={OUT_W}:{GAME_H}:flags=lanczos,setsar=1[game];"
              f"[cam][game]vstack=inputs=2,ass={ass}[v]")
    else:  # no face cam: full game view over a blurred copy, cropped above the stream's captions
        fc = (f"[0:v]split[a][b];[a]scale=-2:1920,crop=1080:1920,boxblur=30:3,eq=brightness=-0.15[bg];"
              f"[b]crop=1920:910:0:0,scale={OUT_W}:{BLUR_FG_H}:flags=lanczos,setsar=1[fg];"
              f"[bg][fg]overlay=0:{BLUR_FG_Y},setsar=1,ass={ass}[v]")
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", src, "-filter_complex", fc, "-map", "[v]", "-map", "0:a",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("clips", nargs="+")
    ap.add_argument("--cam", default="494x276", help='webcam box WxH in the top-left corner, "auto" to find it, x,y,w,h for an exact box, or "none" for the full-game blur layout')
    ap.add_argument("--model", default="medium.en")
    ap.add_argument("--game", help="game crop override x,y,size (square, source pixels)")
    ap.add_argument("--reuse", action="store_true", help="reuse saved transcripts, only re-render")
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    game = tuple(map(int, a.game.split(","))) if a.game else None
    names = [os.path.splitext(os.path.basename(src))[0] for src in a.clips]
    lpaths = [os.path.join(a.out_dir, n + ".layout.json") for n in names]

    def pick_layout(src, lpath):
        if a.cam == "none":  # no webcam, or one not worth showing: full game over blur
            return {"mode": "blur"}
        if a.cam.count(",") == 3:  # exact webcam box x,y,w,h from a manual check
            x, y, w, h = map(int, a.cam.split(","))
            return auto_layout(src, face=(x + w // 3, y + h // 3, w // 3, h // 3))
        if a.cam != "auto":
            return fixed_layout(*map(int, a.cam.split("x")))
        if a.reuse and os.path.exists(lpath):
            return json.load(open(lpath))
        return None  # detect below, in parallel

    layouts = [pick_layout(s_, l_) for s_, l_ in zip(a.clips, lpaths)]
    todo = [i for i, L in enumerate(layouts) if L is None]
    if todo:  # face detection is the slow part, so spread it over the CPU cores
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(min(4, os.cpu_count() or 1)) as ex:
            for i, L in zip(todo, ex.map(auto_layout, [a.clips[i] for i in todo])):
                layouts[i] = L

    model = None
    if not a.reuse:
        from faster_whisper import WhisperModel
        model = WhisperModel(a.model, device="cpu", compute_type="int8")
    for src, name, lpath, layout in zip(a.clips, names, lpaths, layouts):
        if game and layout["mode"] == "stack":
            layout["game"] = game
        wpath = os.path.join(a.out_dir, name + ".words.json")
        if a.reuse:
            words = json.load(open(wpath))
        else:
            words = transcribe(model, src)
            json.dump(words, open(wpath, "w"))
        json.dump(layout, open(lpath, "w"))
        ass = os.path.join(a.out_dir, name + ".ass")
        write_ass(words, ass, caption_y(layout))
        render(src, ass, os.path.join(a.out_dir, name + ".mp4"), layout)
        print("done", name, len(words), "words", layout["mode"], flush=True)


if __name__ == "__main__":
    sys.exit(main())
