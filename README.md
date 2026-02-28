# LoL Scouting Replays Kit

A local web app that replays League of Legends scrim data on an interactive minimap — built for scouting opponent tendencies in the early game.

**What you can scout:**
- **Level 1 positioning** — see exactly where each player starts and how they move in the first minute
- **Early warding** — track first and second trinket placements by position and timing
- **Jungle pathing** — follow the jungler's route from the opening clear through the first gank window
- **Kill & death patterns** — identify lane pressure, dives, and skirmishes in the first 5 minutes

Driven by raw Grid data files. No cloud service, no API keys, no Node.js. Just Python + a browser.

![Preview](assets/map/LOL_map.png)

---

## Features

- **60 fps canvas animation** — smooth position playback with linear interpolation
- **Champion badges** — circular team-coloured icons for every player
- **Champion levels** — live level indicator updated from game data
- **KDA tracking** — kills / deaths / assists computed from kill events
- **Kill feed** — overlay showing the last 8 kills with timestamps
- **Wards** — yellow trinkets (90 s lifespan) and control wards (infinite) with team-coloured icons
- **Death timers** — champions disappear from the map on death and reappear at base on respawn; sidebar shows a red countdown
- **CS tracking** — creep score per player updated in real time
- **Multi-series / multi-game tabs** — auto-discovers every series in `data/`
- **Play / Pause / Scrub / Speed** — ×1 / ×2 / ×4 playback

---

## Requirements

| Requirement | Version |
|---|---|
| Python | 3.9 or newer |
| pip | bundled with Python |

No Node.js, no Docker, no external services.

---

## Quick Start

### 1 — Clone / download the project

```bash
git clone https://github.com/your-username/lol-map-replay.git
cd lol-map-replay
```

Or download the ZIP from GitHub and extract it.

### 2 — Champion icons

Champion icons are **already included** in `assets/champions/` — no action needed.

If a champion is missing (e.g. a newly released champion), place the image manually in `assets/champions/` (accepted formats: `Ezreal.png`, `Ezreal_0.jpg`, `ezreal.png`). Champions without a matching image render as a coloured circle.

### 3 — Download your game data from Grid

For each game you want to replay, export two files from the [Grid](https://grid.gg) platform:

| File | Where to find it in Grid |
|---|---|
| `events_<id>_<game>_riot.jsonl` | Series page → Game → Download → **Events (Riot)** |
| `end_state_summary_riot_<id>_<game>.json` | Series page → Game → Download → **End State Summary (Riot)** |

Download both files for every game in the series, then drop them all into the `data/` folder.

### 4 — Drop files into `data/`

Just dump everything into `data/` with no subfolders — the server groups files by series and game automatically:

```
data/
  events_2901035_1_riot.jsonl
  end_state_summary_riot_2901035_1.json
  events_2901035_2_riot.jsonl
  end_state_summary_riot_2901035_2.json
  events_2901038_1_riot.jsonl
  end_state_summary_riot_2901038_1.json
```

The server reads the series ID and game number directly from the filenames and groups them automatically.

See the [Data Format](#data-format) section below for full details on supported file naming and layouts.

### 5 — Start the server

**Windows:**
```bat
start.bat
```

**Mac / Linux:**
```bash
chmod +x start.sh
./start.sh
```

**Or directly:**
```bash
pip install -r requirements.txt
python -m uvicorn server:app --port 8000
```

### 6 — Open in browser

```
http://localhost:8000
```

That's it. The app auto-discovers all series in `data/` and loads the first game.

---

## Project Structure

```
lol-map-replay/
├── server.py               # FastAPI backend — reads data, serves API + frontend
├── frontend/
│   └── index.html          # React 18 (CDN) single-page app
├── assets/
│   ├── map/
│   │   └── LOL_map.png     # Minimap image
│   ├── champions/          # Champion icons (already included)
│   │   └── centered/       # Optional higher-quality centered crops
│   └── wards/
│       ├── pinkward_2055.png
│       └── yellow_trinket_3340.png
├── data/                   # Drop Grid export files here (flat or nested)
│   └── README.txt          # Data format documentation
├── requirements.txt
├── start.bat               # Windows launcher
├── start.sh                # Mac/Linux launcher
└── .gitignore
```

---

## Data Format

### What to export from Grid

For each game you need **exactly 2 files** from the Grid data platform:

| File | What it is |
|---|---|
| `events_<seriesId>_<gameNum>_riot.jsonl` | Raw event stream — positions, kills, wards |
| `end_state_summary_riot_<seriesId>_<gameNum>.json` | End-of-game summary — players, champions, teams |

### Folder layouts

**Flat (recommended)** — drop everything directly into `data/`:

```
data/
  events_2901035_1_riot.jsonl
  end_state_summary_riot_2901035_1.json
  events_2901035_2_riot.jsonl
  end_state_summary_riot_2901035_2.json
  events_2901038_1_riot.jsonl
  end_state_summary_riot_2901038_1.json
```

The server parses the series ID and game number from the filenames automatically. Multiple series can coexist in the same folder.

**Legacy nested layout** — still supported if you prefer it:

```
data/
└── series_<ID>/
    └── games/
        ├── 1/
        │   ├── events.jsonl
        │   └── summary.json
        └── 2/
            ├── events.jsonl
            └── summary.json
```

Both layouts can be mixed in the same `data/` folder.

### What the server reads from `events.jsonl`

| Event schema | Used for |
|---|---|
| `stats_update` | Player positions (x, z) and champion level, sampled every 2 s |
| `champion_kill` | Kill / death / assist events and positions |
| `ward_placed` | Ward placement — wardType, placer, position, time |
| `ward_killed` | Ward destruction — matched to placement by position |

Only the **first 5 minutes** of each game are loaded (configurable via `MAX_GAME_MS` in `server.py`).

### What the server reads from `summary.json`

The file must contain a `participants` array where each entry has:

| Field | Value |
|---|---|
| `participantId` | Integer 1–10 |
| `championName` | e.g. `"Ezreal"` |
| `riotIdGameName` or `summonerName` | Player display name |
| `teamId` | `100` (blue side) or `200` (red side) |

---

## Customising Champion Images

The server looks for portrait images in this order:

1. `assets/champions/centered/<ChampionName>.png` *(highest priority)*
2. `assets/champions/centered/<ChampionName>_0.jpg`
3. `assets/champions/<ChampionName>.png`
4. `assets/champions/<ChampionName>_0.jpg`
5. Case-insensitive prefix match anywhere in the above folders

This means you can mix Data Dragon icons with your own custom portraits freely. Champions without a matching image render as a coloured circle with the first 6 letters of their name.

---

## Configuration

All tuneable constants are at the top of `server.py`:

| Constant | Default | Description |
|---|---|---|
| `MAX_GAME_MS` | `300_000` | How many ms of each game to load (5 min) |
| `STEP_MS` | `2_000` | Position snapshot interval |
| `BLUE_HEX` | `#0AC8B9` | Blue side badge border colour |
| `RED_HEX` | `#FF4655` | Red side badge border colour |

---

## Troubleshooting

**"No game data found"**
Make sure your files are in `data/` and that their names contain `_<seriesId>_<gameNum>` (e.g. `events_2901035_1_riot.jsonl`). The series ID must be 5–12 digits and the game number 1–3 digits.

**Champion shows as coloured circle (no portrait)**
Place the image manually in `assets/champions/` (e.g. `Ezreal.png`).

**Port 8000 already in use**
Change the port: `python -m uvicorn server:app --port 8001` and open `http://localhost:8001`.

**Startup is slow**
Each game's `events.jsonl` can be 90–120 MB. Startup reads all files; subsequent page loads are instant from the in-memory cache.

**Ward icons missing**
Ensure `assets/wards/pinkward_2055.png` and `assets/wards/yellow_trinket_3340.png` exist.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3, FastAPI, Uvicorn, Pillow |
| Frontend | React 18 (CDN), Babel Standalone (in-browser JSX), HTML Canvas |
| Build system | None — no Node.js, no bundler |

---

## License

MIT — free to use, modify and distribute.

Champion icons and map assets are property of Riot Games and used under their [Legal Jibber Jabber](https://www.riotgames.com/en/legal).
