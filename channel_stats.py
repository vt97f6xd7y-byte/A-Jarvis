#!/usr/bin/env python3
"""Read the public view counts of our YouTube Shorts and show what's working.

Usage:
  python3 channel_stats.py            # uses youtube_handle from channel.json
  python3 channel_stats.py @handle

Matches each Short to the clip it came from using posted.json, which maps
YouTube video titles to streamer/category (the weekly job appends to it when it
plans posts). Prints views per Short, then average views per streamer and per
category, and writes stats.json for the weekly job to weight next week's picks.
Needs www.youtube.com reachable from the environment.
"""
import json, os, subprocess, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    cfg = json.load(open(os.path.join(HERE, "channel.json")))
    handle = sys.argv[1] if len(sys.argv) > 1 else cfg.get("youtube_handle")
    if not handle:
        print("no youtube_handle set in channel.json yet"); return
    handle = "@" + handle.lstrip("@")
    out = subprocess.run(["yt-dlp", "--flat-playlist", "-J", f"https://www.youtube.com/{handle}/shorts"],
                         capture_output=True, text=True)
    if out.returncode:
        print(out.stderr[-500:]); sys.exit(1)
    shorts = [(e.get("title") or "", e.get("view_count") or 0) for e in json.loads(out.stdout).get("entries", [])]

    posted_path = os.path.join(HERE, "posted.json")
    posted = json.load(open(posted_path)) if os.path.exists(posted_path) else {}
    by_streamer, by_cat = defaultdict(list), defaultdict(list)
    rows = []
    for title, views in sorted(shorts, key=lambda s: -s[1]):
        info = posted.get(title.strip(), {})
        rows.append(dict(title=title, views=views, **info))
        if info:
            by_streamer[info.get("streamer", "?")].append(views)
            by_cat[info.get("category", "?")].append(views)

    avg = lambda d: {k: round(sum(v) / len(v)) for k, v in sorted(d.items(), key=lambda kv: -sum(kv[1]) / len(kv[1]))}
    stats = dict(handle=handle, shorts=rows, avg_views_by_streamer=avg(by_streamer), avg_views_by_category=avg(by_cat))
    json.dump(stats, open(os.path.join(HERE, "stats.json"), "w"), indent=1)
    for r in rows[:15]:
        print(f"{r['views']:>9,}  {r.get('streamer', '?'):<15} {r['title'][:70]}")
    print("\nAverage views by streamer:", stats["avg_views_by_streamer"])
    print("Average views by category:", stats["avg_views_by_category"])


if __name__ == "__main__":
    main()
