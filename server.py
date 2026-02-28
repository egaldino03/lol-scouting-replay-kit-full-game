"""
server.py  —  FastAPI backend for LoL Map Replay.

Reads all series_* directories from the data/ folder, pre-loads position
snapshots, champion badges, ward icons, kills and wards on startup, then
serves the React frontend and JSON API.

Run from the project root:
    python -m uvicorn server:app --port 8000

Then open http://localhost:8000
"""

import base64
import json
import re
from collections import Counter
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Paths  (all relative to this file = project root)
# ---------------------------------------------------------------------------
ROOT           = Path(__file__).parent
GRID_ROOT      = ROOT / "data"                          # drop series_* folders here
MAP_PATH       = ROOT / "assets" / "map" / "LOL_map.png"
CHAMP_CENTERED = ROOT / "assets" / "champions" / "centered"
CHAMP_FLAT     = ROOT / "assets" / "champions"
FRONTEND_HTML  = ROOT / "frontend" / "index.html"
WARD_DIR       = ROOT / "assets" / "wards"

ITEM_ID_TO_WARD_TYPE = {3340: "yellowTrinket", 2055: "control", 3364: "sweeper"}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAP_MAX     = 14_820
MAX_GAME_MS = 600_000   # 10 minutes
STEP_MS     = 2_000
BLUE_HEX    = "#0AC8B9"
RED_HEX     = "#FF4655"

# Matches _{seriesId}_{gameNum} embedded in filenames (e.g. events_2901035_1_riot.jsonl)
SERIES_GAME_RE = re.compile(r'[_\-](\d{5,12})[_\-](\d{1,3})(?:[_\-.]|$)')

# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------
_cache: Dict[str, object] = {}
_series_list: List[dict]  = []   # [{id, label, blueTag, redTag, games: [1,2,3]}, ...]


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def _find_portrait(champion: str) -> Optional[Path]:
    clean = champion.replace(" ", "").replace("'", "").replace(".", "")
    for root in [CHAMP_CENTERED, CHAMP_FLAT]:
        if not root.exists():
            continue
        for stem in [f"{clean}_0", f"{champion}_0", clean, champion]:
            for ext in (".jpg", ".png", ".jpeg"):
                p = root / f"{stem}{ext}"
                if p.exists():
                    return p
    low = clean.lower()
    for root in [CHAMP_CENTERED, CHAMP_FLAT]:
        if not root.exists():
            continue
        for f in root.iterdir():
            if f.suffix.lower() in (".jpg", ".png", ".jpeg") and f.stem.lower().startswith(low):
                return f
    return None


def _make_badge(champion: str, team: int, size: int = 80) -> str:
    """Return a data:image/png;base64 circular badge for a champion."""
    portrait  = _find_portrait(champion)
    border_px = 5
    hex_col   = BLUE_HEX if team == 100 else RED_HEX
    r, g, b   = int(hex_col[1:3], 16), int(hex_col[3:5], 16), int(hex_col[5:7], 16)

    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw   = ImageDraw.Draw(result)
    draw.ellipse((0, 0, size - 1, size - 1), fill=(r, g, b, 255))

    inner     = size - border_px * 2
    inner_box = (border_px, border_px, size - border_px, size - border_px)
    img       = None

    if portrait:
        try:
            img = Image.open(portrait).convert("RGBA")
            w, h = img.size
            s    = min(w, h)
            img  = img.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))
            img  = img.resize((inner, inner), Image.LANCZOS)
        except Exception:
            img = None

    if img is None:
        draw.ellipse(inner_box, fill=(20, 20, 30, 230))
        label     = champion[:6]
        font_size = max(8, inner // max(len(label), 1) - 2)
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()
        cx, cy = border_px + inner // 2, border_px + inner // 2
        draw.text((cx, cy), label, font=font, fill=(r, g, b, 255), anchor="mm")
    else:
        mask   = Image.new("L", (inner, inner), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, inner - 1, inner - 1), fill=255)
        masked = Image.new("RGBA", (inner, inner), (0, 0, 0, 0))
        masked.paste(img, (0, 0), mask)
        result.paste(masked, (border_px, border_px), mask)

    buf = BytesIO()
    result.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _discover_ward_icons() -> Dict[str, Path]:
    """Scan WARD_DIR and return {wardType: Path} for any file whose stem contains a known item ID."""
    result = {}
    if not WARD_DIR.exists():
        return result
    for f in WARD_DIR.iterdir():
        if f.suffix.lower() not in ('.png', '.jpg', '.jpeg'):
            continue
        m = re.search(r'(\d+)', f.stem)
        if m:
            ward_type = ITEM_ID_TO_WARD_TYPE.get(int(m.group(1)))
            if ward_type:
                result[ward_type] = f
    return result


def _make_ward_badge(icon_path: Optional[Path], team: int, size: int = 44) -> str:
    """Return a data:image/png;base64 circular ward badge with team-coloured border."""
    ward_file = icon_path
    border_px = 4
    hex_col   = BLUE_HEX if team == 100 else RED_HEX
    r, g, b   = int(hex_col[1:3], 16), int(hex_col[3:5], 16), int(hex_col[5:7], 16)

    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw   = ImageDraw.Draw(result)
    draw.ellipse((0, 0, size - 1, size - 1), fill=(r, g, b, 255))

    inner = size - border_px * 2
    img   = None

    if ward_file.exists():
        try:
            img = Image.open(ward_file).convert("RGBA")
            img = img.resize((inner, inner), Image.LANCZOS)
        except Exception:
            img = None

    if img is not None:
        mask   = Image.new("L", (inner, inner), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, inner - 1, inner - 1), fill=255)
        masked = Image.new("RGBA", (inner, inner), (0, 0, 0, 0))
        masked.paste(img, (0, 0), mask)
        result.paste(masked, (border_px, border_px), mask)

    buf = BytesIO()
    result.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------------------
# File discovery helpers (handles different naming conventions per series)
# ---------------------------------------------------------------------------

def _find_summary_path(game_dir: Path) -> Optional[Path]:
    """Find the summary JSON in a game directory."""
    p = game_dir / "summary.json"
    if p.exists():
        return p
    candidates = sorted(game_dir.glob("*summary*.json"))
    return candidates[0] if candidates else None


def _find_events_path(game_dir: Path) -> Optional[Path]:
    """Find the events JSONL in a game directory (prefers riot-tagged files)."""
    p = game_dir / "events.jsonl"
    if p.exists():
        return p
    riot = sorted(game_dir.glob("events*riot*.jsonl"))
    if riot:
        return riot[0]
    candidates = sorted(game_dir.glob("events*.jsonl"))
    return candidates[0] if candidates else None


def _parse_series_game(filename: str) -> Tuple[Optional[str], Optional[int]]:
    """Extract (series_id, game_num) from a filename using SERIES_GAME_RE."""
    m = SERIES_GAME_RE.search(Path(filename).stem)
    if m:
        return m.group(1), int(m.group(2))
    return None, None


def _discover_games() -> Dict[str, Dict[int, Dict[str, Path]]]:
    """Return {series_id: {game_num: {events: Path, summary: Path}}} from data/.

    Pass 1: filename-based scan — works for flat folders and nested folders
             when filenames contain _{seriesId}_{gameNum}.
    Pass 2: legacy series_*/games/N/ folder layout fallback.
    """
    found: Dict[str, Dict[int, Dict[str, Path]]] = {}

    # Pass 1: filename-based (flat OR nested)
    for path in sorted(GRID_ROOT.rglob("*")):
        if not path.is_file():
            continue
        sid, gnum = _parse_series_game(path.name)
        if sid is None:
            continue
        slot = found.setdefault(sid, {}).setdefault(gnum, {})
        if path.suffix == ".jsonl" and "events" not in slot:
            slot["events"] = path
        elif path.suffix == ".json" and "summary" not in slot:
            slot["summary"] = path

    # Pass 2: legacy series_*/games/N/ folder structure fallback
    for series_dir in sorted(GRID_ROOT.glob("[Ss]eries_*")):
        sid = re.sub(r"(?i)^series_", "", series_dir.name)
        games_dir = series_dir / "games"
        if not games_dir.exists():
            continue
        for game_dir in sorted(games_dir.iterdir()):
            if not game_dir.is_dir() or not game_dir.name.isdigit():
                continue
            gnum = int(game_dir.name)
            slot = found.setdefault(sid, {}).setdefault(gnum, {})
            if "events" not in slot:
                p = _find_events_path(game_dir)
                if p:
                    slot["events"] = p
            if "summary" not in slot:
                p = _find_summary_path(game_dir)
                if p:
                    slot["summary"] = p

    return found


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def _team_prefix(names: List[str]) -> str:
    """Guess team tag from player display names (e.g. 'S2G DnDn' → 'S2G')."""
    prefixes = [n.split()[0] for n in names if n.split()]
    if not prefixes:
        return "???"
    return Counter(prefixes).most_common(1)[0][0]


def _extract_series_label(summary_path: Optional[Path]) -> Tuple[str, str, str]:
    """Return (label, blue_tag, red_tag) derived from a summary file."""
    if not summary_path or not summary_path.exists():
        return ("Unknown Series", "?", "?")
    try:
        with open(summary_path, encoding="utf-8") as f:
            s = json.load(f)
        info  = s.get("info", s)
        teams: Dict[int, List[str]] = {}
        for p in info.get("participants", []):
            tid  = p.get("teamId", 100)
            name = p.get("riotIdGameName", p.get("summonerName", ""))
            teams.setdefault(tid, []).append(name)
        blue_tag = _team_prefix(teams.get(100, []))
        red_tag  = _team_prefix(teams.get(200, []))
        return (f"{blue_tag} vs {red_tag}", blue_tag, red_tag)
    except Exception:
        return ("Unknown Series", "?", "?")


def _load_participants(summary_path: Optional[Path]) -> Dict[str, dict]:
    if not summary_path or not summary_path.exists():
        return {}
    with open(summary_path, encoding="utf-8") as f:
        s = json.load(f)
    info   = s.get("info", s)
    result = {}
    for p in info.get("participants", []):
        pid = str(p["participantId"])
        result[pid] = {
            "champion": p.get("championName", ""),
            "player":   p.get("riotIdGameName", p.get("summonerName", f"P{pid}")),
            "team":     p.get("teamId", 100 if int(pid) <= 5 else 200),
        }
    return result


def _load_snapshots(events_path: Optional[Path]) -> Dict[str, Dict[str, list]]:
    """Return {str(time_ms): {str(pid): [x, z, level, cs]}} sampled every 2 s up to 5 min."""
    if not events_path or not events_path.exists():
        return {}

    snapshots   = {}
    last_bucket = -1

    with open(events_path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue

            if obj.get("rfc461Schema") != "stats_update":
                continue

            t = obj.get("gameTime", 0)
            if t > MAX_GAME_MS:
                break

            bucket = (t // STEP_MS) * STEP_MS
            if bucket == last_bucket:
                continue
            last_bucket = bucket

            snap = {}
            for p in obj.get("participants", []):
                pos       = p.get("position", {})
                stats_map = {s["name"]: s["value"] for s in p.get("stats", [])}
                cs        = int(stats_map.get("MINIONS_KILLED", 0)) + int(stats_map.get("NEUTRAL_MINIONS_KILLED", 0))
                snap[str(p["participantID"])] = [
                    float(pos.get("x", 0)),
                    float(pos.get("z", 0)),
                    int(p.get("level", 1)),
                    cs,
                    int(p.get("totalGold", 0)),
                    int(p.get("currentGold", 0)),
                ]
            snapshots[str(bucket)] = snap

    return snapshots


def _load_wards(events_path: Optional[Path]) -> Tuple[List[dict], List[dict]]:
    """Return (wards, sweeper_raw) from events within 5 min.

    wards: [{t, tKilled, placer, type, x, z}]
    sweeper_raw: [{t, placer}] — positions assigned later from snapshots
    """
    if not events_path or not events_path.exists():
        return [], []

    placed: List[dict]       = []
    sweeper_raw: List[dict]  = []

    with open(events_path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue

            t      = obj.get("gameTime", 0)
            schema = obj.get("rfc461Schema", "")

            if t > MAX_GAME_MS:
                break

            if schema == "ward_placed":
                pos = obj.get("position", {})
                placed.append({
                    "t":       t,
                    "tKilled": None,
                    "placer":  str(obj.get("placer", 0)),
                    "type":    obj.get("wardType", ""),
                    "x":       float(pos.get("x", 0)),
                    "z":       float(pos.get("z", 0)),
                })

            elif schema == "ward_killed":
                pos   = obj.get("position", {})
                kx    = float(pos.get("x", 0))
                kz    = float(pos.get("z", 0))
                wtype = obj.get("wardType", "")
                for w in reversed(placed):
                    if w["x"] == kx and w["z"] == kz and w["type"] == wtype and w["tKilled"] is None:
                        w["tKilled"] = t
                        break

            elif schema == "item_active_ability_used" and obj.get("itemID") == 3364:
                sweeper_raw.append({"t": t, "placer": str(obj.get("participantID", 0))})

    return placed, sweeper_raw


def _assign_sweeper_positions(sweeper_raw: List[dict], snapshots: Dict[str, dict]) -> List[dict]:
    """Resolve each sweeper activation to the player's position at that time."""
    times = sorted(int(k) for k in snapshots)
    uses  = []
    for ev in sweeper_raw:
        pid, t = ev["placer"], ev["t"]
        pos = None
        for ts in times:
            snap = snapshots.get(str(ts), {}).get(pid)
            if snap and ts >= t:
                pos = snap
                break
        if pos is None and times:
            pos = snapshots.get(str(times[-1]), {}).get(pid)
        if pos:
            uses.append({"t": t, "placer": pid, "x": pos[0], "z": pos[1]})
    return uses


def _compute_respawn_times(kills: List[dict], snapshots: Dict[str, Dict[str, list]]) -> None:
    """Add 'respawnAt' (int ms | None) to each kill, detected from position data.

    After a death we scan forward through snapshots for the first frame where
    the victim's position is >1000 game-units from the kill location — that
    jump indicates a teleport back to base (respawn).
    respawnAt = None means the champion did not respawn within the data window.
    """
    times = sorted(int(t) for t in snapshots.keys())
    for kill in kills:
        death_t = kill["t"]
        pid     = kill["victim"]
        death_x = kill["x"]
        death_z = kill["z"]
        respawn_t: Optional[int] = None
        for t in times:
            if t <= death_t:
                continue
            pos = snapshots.get(str(t), {}).get(pid)
            if pos is None:
                continue
            dx = pos[0] - death_x
            dz = pos[1] - death_z
            if dx * dx + dz * dz > 1_000 * 1_000:   # >1000 units → teleported to base
                respawn_t = t
                break
        kill["respawnAt"] = respawn_t


def _load_kills(events_path: Optional[Path]) -> List[dict]:
    """Return list of champion_kill events up to 5 min.

    Each entry: {t, killer, victim, assists, x, z, respawnAt}
    killer/victim/assists are str participant IDs.
    """
    if not events_path or not events_path.exists():
        return []

    kills = []
    with open(events_path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue

            if obj.get("rfc461Schema") != "champion_kill":
                continue

            t = obj.get("gameTime", 0)
            if t > MAX_GAME_MS:
                break

            pos = obj.get("position", {})
            kills.append({
                "t":       t,
                "killer":  str(obj.get("killer", 0)),
                "victim":  str(obj.get("victim", 0)),
                "assists": [str(a) for a in obj.get("assistants", [])],
                "x":       float(pos.get("x", 0)),
                "z":       float(pos.get("z", 0)),
            })

    return kills


# ---------------------------------------------------------------------------
# Startup — auto-discover and pre-load all series
# ---------------------------------------------------------------------------

def _preload_all():
    global _series_list

    # Map image
    if MAP_PATH.exists():
        img = Image.open(MAP_PATH).convert("RGBA")
        buf = BytesIO()
        img.save(buf, format="PNG")
        _cache["map"] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        print("  Map image loaded.")
    else:
        print(f"  WARNING: map image not found at {MAP_PATH}")
        print("  Place LOL_map.png in assets/map/ to show the minimap.")

    # Ward badge icons — auto-discovered from assets/wards/ by item ID in filename
    discovered_icons = _discover_ward_icons()
    ward_icons: Dict[str, str] = {}
    for wtype, icon_path in discovered_icons.items():
        for team in [100, 200]:
            ward_icons[f"{wtype}_{team}"] = _make_ward_badge(icon_path, team)
    _cache["ward_icons"] = ward_icons
    print(f"  Ward icons generated ({len(ward_icons)}) from {list(discovered_icons.keys())}.")

    # Discover all games from data/ (filename-based + legacy folder layout)
    discovered = _discover_games()
    if not discovered:
        print(f"  WARNING: No game data found in {GRID_ROOT}/")
        print("  Drop Grid files (events_*.jsonl + *summary*.json) into data/")
        print("  Or use the series_*/games/N/ folder layout. See README.md.")
        return

    for sid in sorted(discovered):
        game_map  = discovered[sid]
        game_nums = sorted(game_map)

        label, blue_tag, red_tag = _extract_series_label(game_map[game_nums[0]].get("summary"))
        if label == "Unknown Series":
            label = f"Series {sid}"

        _series_list.append({
            "id":      sid,
            "label":   label,
            "blueTag": blue_tag,
            "redTag":  red_tag,
            "games":   game_nums,
        })
        print(f"  Series {sid} ({label}) — {len(game_nums)} game(s)")

        for gnum in game_nums:
            slot = game_map[gnum]
            print(f"    Game {gnum} …", end=" ", flush=True)
            participants = _load_participants(slot.get("summary"))
            if not participants:
                print("no participants found, skipping.")
                continue

            snapshots                = _load_snapshots(slot.get("events"))
            kills                    = _load_kills(slot.get("events"))
            wards, sweeper_raw       = _load_wards(slot.get("events"))
            sweeper_uses             = _assign_sweeper_positions(sweeper_raw, snapshots)
            _compute_respawn_times(kills, snapshots)

            for pid, info in participants.items():
                info["badge"] = _make_badge(info["champion"], info["team"])

            _cache[f"series_{sid}_game_{gnum}"] = {
                "participants": participants,
                "snapshots":    snapshots,
                "kills":        kills,
                "wards":        wards,
                "sweeper_uses": sweeper_uses,
            }
            print(f"{len(participants)} players, {len(snapshots)} snapshots, "
                  f"{len(kills)} kills, {len(wards)} wards.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Pre-loading game data …")
    _preload_all()
    print(f"Ready — {len(_series_list)} series loaded. Open http://localhost:8000")
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="LoL Map Replay", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/map")
def get_map():
    return {"data": _cache.get("map", "")}


@app.get("/api/ward-icons")
def get_ward_icons():
    return _cache.get("ward_icons", {})


@app.get("/api/series")
def get_series():
    return _series_list


@app.get("/api/series/{series_id}/game/{game_num}")
def get_game(series_id: str, game_num: int):
    key = f"series_{series_id}_game_{game_num}"
    if key not in _cache:
        return {"error": f"Series {series_id} Game {game_num} not loaded"}
    return _cache[key]


@app.get("/", response_class=HTMLResponse)
def serve_index():
    if FRONTEND_HTML.exists():
        return HTMLResponse(FRONTEND_HTML.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>frontend/index.html not found</h1>", status_code=404)
