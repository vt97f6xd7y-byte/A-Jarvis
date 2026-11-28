#!/usr/bin/env python3
"""Tiny helper for the ClipsBank posting queue (queue.json).

  python3 grind.py next              # print the next unposted entry as JSON (or "empty")
  python3 grind.py mark ID YT_ID     # mark an entry posted with its YouTube video id
  python3 grind.py status            # how many are posted / left, and by streamer
"""
import datetime, json, os, sys
from collections import Counter

Q = os.path.join(os.path.dirname(os.path.abspath(__file__)), "queue.json")


def load():
    return json.load(open(Q))


def save(q):
    json.dump(q, open(Q, "w"), indent=1, ensure_ascii=False)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    q = load()
    left = [e for e in q if not e.get("posted")]
    if cmd == "next":
        print(json.dumps(left[0], ensure_ascii=False) if left else "empty")
    elif cmd == "mark":
        _, _, cid, yt = sys.argv
        for e in q:
            if e["id"] == cid:
                e["posted"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                e["youtube_id"] = yt
                save(q)
                print("marked", cid, yt)
                return
        sys.exit(f"no queue entry {cid}")
    else:
        print(f"{len(q) - len(left)} posted, {len(left)} left")
        print("left by streamer:", dict(Counter(e["streamer"] for e in left)))


if __name__ == "__main__":
    main()
