# Notes for Claude

## User preferences
- When the user wants something to repeat or run on its own (recurring jobs, scheduled posting, automations), build it in **Zapier** via the Zapier MCP connector rather than other schedulers, unless they say otherwise.
- YouTube uploads: always turn **comments off**.
- Writing style: plain, friendly, conversational. No em dashes, no buzzwords.

## Project
- `make_vertical.py`: turns 1920x1080 Twitch clips into 1080x1920 Shorts (webcam on top, game below, or blur / face-following portrait layouts) with word-by-word captions.
- `weekly_pull.py`: pulls each channel's top new clips (GTA 6 plus a few others) and renders them. `done_clips.txt` tracks what's been made.
- `channel_stats.py`: reads public Shorts view counts once `channel.json` has a `youtube_handle`.
- Uploads go through Zapier's YouTube "Upload Video" action (selected_api YouTubeV4CLIAPI), channel ClipsBank (@clipsbank1). Zapier fetches each video from the public repo vt97f6xd7y-byte/clipsbank-media (branch claude/media), via https://raw.githubusercontent.com/vt97f6xd7y-byte/clipsbank-media/claude/media/<path>. Keep only the current week's videos there.
- Money comes mainly from paid clip campaigns on Content Rewards (whop.com): Lacy GTA 6 marathon pool, Kai Cenat GTA 6 pool, StableRonaldo / CORE pools. Weight picks and posting slots toward those streamers. The user doesn't use Discord.
