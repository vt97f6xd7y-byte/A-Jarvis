#!/usr/bin/env python3
"""Pull a streamer's newest top clips for one game and turn them into vertical Shorts.

Usage:
  python3 weekly_pull.py OUT_DIR [--channel lacy] [--game "Grand Theft Auto VI"]
                         [--range 7d] [--top 10]

Clips already listed in done_clips.txt (next to this script) are skipped, and new
ones are appended after they render, so each week only brings fresh clips.
Writes OUT_DIR/manifest.json with title, views, duration and transcript per clip.
"""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DONE = os.path.join(HERE, "done_clips.txt")
ENV = dict(os.environ, HF_HUB_DISABLE_XET="1")


def ytdlp_json(args):
    out = subprocess.run(["yt-dlp", *args], capture_output=True, text=True, check=True).stdout
    return [json.loads(l) for l in out.splitlines() if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--channel", default="lacy")
    ap.add_argument("--game", default="Grand Theft Auto VI")
    ap.add_argument("--range", default="7d", choices=["24hr", "7d", "30d", "all"])
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--scan", type=int, default=100, help="how many top clips to check for the game")
    a = ap.parse_args()

    done = set(open(DONE).read().split()) if os.path.exists(DONE) else set()
    src_dir = os.path.join(a.out_dir, "src")
    os.makedirs(src_dir, exist_ok=True)

    listing = ytdlp_json(["--flat-playlist", "--playlist-end", str(a.scan), "-j",
                          f"https://www.twitch.tv/{a.channel}/clips?filter=clips&range={a.range}"])
    urls = [e["url"] for e in listing if e["url"].rsplit("/", 1)[-1] not in done]
    if not urls:
        print("no new clips"); return
    meta = ytdlp_json(["-j", "--skip-download", *urls])
    picked = sorted((m for m in meta if a.game in (m.get("categories") or [])),
                    key=lambda m: -m["view_count"])[:a.top]
    if not picked:
        print("no new clips for", a.game); return

    for m in picked:
        subprocess.run(["yt-dlp", "-q", "-o", os.path.join(src_dir, "%(display_id)s.%(ext)s"), m["webpage_url"]], check=True)
    srcs = [os.path.join(src_dir, m["display_id"] + ".mp4") for m in picked]
    subprocess.run([sys.executable, os.path.join(HERE, "make_vertical.py"), a.out_dir, *srcs], check=True, env=ENV)

    manifest = []
    for m in picked:
        words = json.load(open(os.path.join(a.out_dir, m["display_id"] + ".words.json")))
        manifest.append(dict(id=m["display_id"], url=m["webpage_url"], twitch_title=m["title"],
                             views=m["view_count"], seconds=m["duration"], date=m.get("upload_date"),
                             video=os.path.join(a.out_dir, m["display_id"] + ".mp4"),
                             transcript=" ".join(w[2] for w in words)))
    json.dump(manifest, open(os.path.join(a.out_dir, "manifest.json"), "w"), indent=1)
    with open(DONE, "a") as f:
        f.write("".join(m["display_id"] + "\n" for m in picked))
    print(f"made {len(picked)} clips -> {a.out_dir}")


if __name__ == "__main__":
    main()
