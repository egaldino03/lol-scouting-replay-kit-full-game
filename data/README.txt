DROP YOUR GAME DATA HERE
========================

This folder holds series data exported from the Grid data platform.

Required folder structure
--------------------------

data/
  series_<SERIES_ID>/
    games/
      1/
        events.jsonl          (or events*riot*.jsonl)
        summary.json          (or *summary*.json / end_state_summary_riot_*.json)
      2/
        events.jsonl
        summary.json
      3/
        ...
  series_<ANOTHER_ID>/
    games/
      ...

The server auto-discovers every series_* directory and every numbered
game folder inside it — no configuration needed.  Just drop the folders
here and restart the server.

File naming notes
-----------------
The server handles multiple naming conventions automatically:

  Summary files:
    summary.json
    end_state_summary_riot_<anything>.json
    any file matching *summary*.json

  Events files:
    events.jsonl
    events*riot*.jsonl   (preferred when both exist)
    any file matching events*.jsonl

Supported event schemas (read from events.jsonl)
-------------------------------------------------
  stats_update     — position + level snapshots every 2 seconds
  champion_kill    — kill / death / assist events
  ward_placed      — ward placements (yellowTrinket, control)
  ward_killed      — ward destructions

Only the first 5 minutes of each game are loaded.
