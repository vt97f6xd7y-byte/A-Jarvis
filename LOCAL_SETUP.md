# ClipsBank: what we built and how to run it locally

## What this project does

Turns Twitch clips into vertical YouTube Shorts and posts them to the **ClipsBank** channel (@clipsbank1).

1. **Find clips**: each week, pull the top new clips from Lacy, Kai Cenat, StableRonaldo, caseoh_, xQc and TheBurntPeanut (mostly GTA 6, plus a few others).
2. **Make Shorts**: 1080x1920 with the streamer's webcam on top, the game below, and big word-by-word captions. The webcam is found automatically with face detection. Clips with no face cam get the full game over a blurred background, and Just Chatting / IRL clips can follow the streamer's face in a 9:16 crop.
3. **Check and pick**: look at a frame from every video, fix wrong crops, hold back anything with sexual content, slurs or politics, and pick 14 posts for the week (2 a day).
4. **Post**: Zapier's YouTube "Upload Video" action posts each Short, pulling the file from the public `clipsbank-media` GitHub repo.

**Money plan:** YouTube Shorts ads pay very little. The real money is paid clip campaigns on **Content Rewards (whop.com)**: the Lacy GTA 6 marathon pool, the Kai Cenat GTA 6 pool and the StableRonaldo / CORE pools. That's why most posts are from those three streamers. Goal: $20K.

## Files

| File | What it does |
|---|---|
| `make_vertical.py` | Clip to vertical Short with captions. `--cam auto` (find webcam), `--cam auto-irl` (also face-following portrait), `--cam none` (blur layout), `--cam x,y,w,h` (exact webcam box), `--game x,y,size` (game crop). Reuses saved transcripts and layouts. |
| `weekly_pull.py` | Pulls each channel's top new clips and runs `make_vertical.py`. `--channels lacy:14,kaicenat:14,...` sets clips per channel. Skips anything in `done_clips.txt`. Writes `manifest.json`. |
| `channel_stats.py` | Reads ClipsBank's public Shorts views so picks can follow what performs. |
| `channel.json` | Channel handle and posts per day. |
| `posted.json` | Every post: title, streamer, YouTube ID. |
| `weekly_titles/` | Each week's plan (titles, descriptions, schedule). |
| `models/mmod_human_face_detector.dat` | dlib face detection model used to find webcams. |
| `CLAUDE.md` | Your preferences: Zapier for anything recurring, comments off, plain writing. |

## Accounts and connections

- **YouTube:** ClipsBank (@clipsbank1), connected to Zapier.
- **Zapier:** YouTube connected; Google Drive connected (instaarham6@gmail.com). Drive isn't needed anymore since videos come from GitHub.
- **GitHub:** `vt97f6xd7y-byte/A-Jarvis` (code, branch `claude/streamer-game-layout-subtitles-l8g02r`) and `vt97f6xd7y-byte/clipsbank-media` (public, videos, branch `claude/media`).

## Run it on your computer

### 1. Install
You need Python 3.11+, ffmpeg and git.

```bash
git clone -b claude/streamer-game-layout-subtitles-l8g02r https://github.com/vt97f6xd7y-byte/A-Jarvis.git
git clone -b claude/media https://github.com/vt97f6xd7y-byte/clipsbank-media.git
cd A-Jarvis
python3 -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

ffmpeg: Mac `brew install ffmpeg`, Windows `winget install ffmpeg`, Linux `sudo apt install ffmpeg`.

The first run downloads the speech-to-text model (about 1.5 GB) from Hugging Face. If downloads stall, set `HF_HUB_DISABLE_XET=1`.

### 2. Make a week of Shorts
```bash
python3 weekly_pull.py ../weekly-out --range 7d --other 3
```
Takes a while (about 1 to 2 minutes per clip on a laptop). Rerun the same command to resume if it stops.

Fix one clip that came out wrong:
```bash
rm ../weekly-out/<clip_id>.layout.json
python3 make_vertical.py ../weekly-out --cam x,y,w,h ../weekly-out/src/<clip_id>.mp4   # or --cam none
```

### 3. Post
1. Copy the 14 picks into `clipsbank-media/week-<date>/`, commit and push.
2. Each video's link is `https://raw.githubusercontent.com/vt97f6xd7y-byte/clipsbank-media/claude/media/week-<date>/<file>.mp4`.
3. In Claude Code (with the Zapier connector), ask it to post with **YouTube Upload Video**: that link as the video, title, description, public, category Gaming, not made for kids.

### 4. Automate it (your preference: Zapier)
Build a Zap on zapier.com:
- **Trigger:** Schedule by Zapier, every day at 12:30pm and 7:30pm ET (or a Google Sheets "new row" trigger).
- **Action:** YouTube, Upload Video, using the video link, title and description from a Google Sheet that lists the week's plan.

Each week, run step 2, push the videos, and fill the sheet. The Zap posts on its own.

## Still to do
- Turn **comments off**: YouTube Studio, Settings, Upload defaults, Advanced settings, Comments: Off.
- Sign up at **whop.com** and join the Lacy GTA 6, Kai Cenat GTA 6 and CORE / StableRonaldo campaigns on Content Rewards, then follow their rules (hashtags, tags) in every title and description.

## Heads up
- The cloud version is still running: posts are scheduled through Thursday Dec 3, and a weekly batch runs Mondays at 9:38am ET. If you switch to local, cancel those in the claude.ai scheduled tasks list so posts don't double up.
- Posting other streamers' clips can get copyright claims. Being in their clip campaigns is what makes it OK.
