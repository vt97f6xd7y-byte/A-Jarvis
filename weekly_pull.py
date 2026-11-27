#!/usr/bin/env python3
"""Pull streamers' newest top clips (one main game plus a few others) and turn them into vertical Shorts.

Usage:
  python3 weekly_pull.py OUT_DIR [--channels lacy:14,xqc:4] [--game "Grand Theft Auto VI"]
                         [--range 7d] [--top 10]

Clips already listed in done_clips.txt (next to this script) are skipped, and new
ones are appended after they render, so each week only brings fresh clips.
The webcam is found automatically per clip (face detection); clips with no face cam
get the full-game-over-blur layout.
Writes OUT_DIR/manifest.json with channel, title, views, duration, layout and transcript per clip.
"""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DONE = os.path.join(HERE, "done_clips.txt")
ENV = dict(os.environ, HF_HUB_DISABLE_XET="1")
# channel[:clips] -- streamers with paid clip campaigns (Content Rewards pools for Lacy GTA 6,
# Kai Cenat GTA 6, and StableRonaldo / CORE) get most of the slots; the rest stay in for reach.
CHANNELS = "lacy:14,kaicenat:14,stableronaldo:12,caseoh_:4,xqc:4,theburntpeanut:3"


def ytdlp_json(args):
    out = subprocess.run(["yt-dlp", *args], capture_output=True, text=True).stdout
    return [json.loads(l) for l in out.splitlines() if l.strip()]


def pick_clips(channel, game, rng, top, other, scan, done):
    """Top `top` clips in `game`, plus the top `other` clips from anything else (Just Chatting, IRL, other games)."""
    listing = ytdlp_json(["--flat-playlist", "--playlist-end", str(scan), "-j",
                          f"https://www.twitch.tv/{channel}/clips?filter=clips&range={rng}"])
    urls = [e["url"] for e in listing if e["url"].rsplit("/", 1)[-1] not in done]
    if not urls:
        return []
    meta = sorted(ytdlp_json(["-j", "--skip-download", *urls]), key=lambda m: -m["view_count"])
    in_game = [m for m in meta if game in (m.get("categories") or [])][:top]
    rest = [m for m in meta if game not in (m.get("categories") or []) and m.get("duration", 0) >= 6][:other]
    return in_game + rest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--channels", default=CHANNELS,
                    help="comma-separated Twitch usernames, each optionally name:N to take N clips from that channel")
    ap.add_argument("--game", default="Grand Theft Auto VI")
    ap.add_argument("--range", default="7d", choices=["24hr", "7d", "30d", "all"])
    ap.add_argument("--top", type=int, default=10, help="clips per channel in --game when a channel has no :N")
    ap.add_argument("--other", type=int, default=3, help="extra clips per channel from other categories")
    ap.add_argument("--scan", type=int, default=60, help="how many top clips per channel to check for the game")
    a = ap.parse_args()

    done = set(open(DONE).read().split()) if os.path.exists(DONE) else set()
    src_dir = os.path.join(a.out_dir, "src")
    os.makedirs(src_dir, exist_ok=True)

    picked = []
    for entry in a.channels.split(","):
        ch, _, n = entry.partition(":")
        clips = pick_clips(ch, a.game, a.range, int(n) if n else a.top, a.other, a.scan, done)
        n_game = sum(a.game in (m.get("categories") or []) for m in clips)
        print(f"{ch}: {n_game} new {a.game} clips, {len(clips) - n_game} other clips", flush=True)
        picked += [dict(m, channel=ch) for m in clips]
    if not picked:
        print("no new clips"); return

    for m in picked:
        subprocess.run(["yt-dlp", "-q", "-o", os.path.join(src_dir, "%(display_id)s.%(ext)s"), m["webpage_url"]], check=True)
    src = lambda m: os.path.join(src_dir, m["display_id"] + ".mp4")
    game_srcs = [src(m) for m in picked if a.game in (m.get("categories") or [])]
    other_srcs = [src(m) for m in picked if a.game not in (m.get("categories") or [])]
    mv = [sys.executable, os.path.join(HERE, "make_vertical.py"), a.out_dir]
    if game_srcs:
        subprocess.run(mv + ["--cam", "auto", *game_srcs], check=True, env=ENV)
    if other_srcs:  # Just Chatting / IRL: may follow a full-screen face in a 9:16 crop
        subprocess.run(mv + ["--cam", "auto-irl", *other_srcs], check=True, env=ENV)

    manifest = []
    for m in picked:
        base = os.path.join(a.out_dir, m["display_id"])
        words = json.load(open(base + ".words.json"))
        manifest.append(dict(channel=m["channel"], category=(m.get("categories") or ["?"])[0], id=m["display_id"], url=m["webpage_url"], twitch_title=m["title"],
                             views=m["view_count"], seconds=m["duration"], date=m.get("upload_date"),
                             video=base + ".mp4", source=os.path.join(src_dir, m["display_id"] + ".mp4"),
                             layout=json.load(open(base + ".layout.json")),
                             transcript=" ".join(w[2] for w in words)))
    json.dump(manifest, open(os.path.join(a.out_dir, "manifest.json"), "w"), indent=1)
    with open(DONE, "a") as f:
        f.write("".join(m["display_id"] + "\n" for m in picked))
    print(f"made {len(picked)} clips -> {a.out_dir}")


if __name__ == "__main__":
    main()
