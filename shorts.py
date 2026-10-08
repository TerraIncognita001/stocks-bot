import array, asyncio, datetime as dt, json, math, os, pathlib, random, re, subprocess, time, wave
import requests

W = pathlib.Path("work")
W.mkdir(exist_ok=True)
USED = pathlib.Path("used.json")
used = json.loads(USED.read_text(encoding="utf-8")) if USED.exists() else []
env = os.getenv

# ---- Universe: large, well-known US stocks (ticker: name, sector) ----------------------------------------
UNIVERSE = {
    "AAPL": ("Apple", "Tech"), "MSFT": ("Microsoft", "Tech"), "NVDA": ("Nvidia", "Tech"),
    "GOOGL": ("Alphabet", "Tech"), "META": ("Meta", "Tech"), "AVGO": ("Broadcom", "Tech"),
    "ORCL": ("Oracle", "Tech"), "AMD": ("AMD", "Tech"), "INTC": ("Intel", "Tech"), "CRM": ("Salesforce", "Tech"),
    "ADBE": ("Adobe", "Tech"), "CSCO": ("Cisco", "Tech"), "QCOM": ("Qualcomm", "Tech"), "IBM": ("IBM", "Tech"),
    "TXN": ("Texas Instruments", "Tech"), "MU": ("Micron", "Tech"), "PLTR": ("Palantir", "Tech"),
    "NFLX": ("Netflix", "Tech"), "UBER": ("Uber", "Tech"), "SHOP": ("Shopify", "Tech"),
    "AMZN": ("Amazon", "Consumer"), "TSLA": ("Tesla", "Consumer"), "WMT": ("Walmart", "Consumer"),
    "COST": ("Costco", "Consumer"), "HD": ("Home Depot", "Consumer"), "MCD": ("McDonald's", "Consumer"),
    "NKE": ("Nike", "Consumer"), "SBUX": ("Starbucks", "Consumer"), "KO": ("Coca-Cola", "Consumer"),
    "PEP": ("PepsiCo", "Consumer"), "PG": ("Procter & Gamble", "Consumer"), "DIS": ("Disney", "Consumer"),
    "TGT": ("Target", "Consumer"), "F": ("Ford", "Consumer"), "GM": ("General Motors", "Consumer"),
    "JPM": ("JPMorgan", "Finance"), "BAC": ("Bank of America", "Finance"), "WFC": ("Wells Fargo", "Finance"),
    "C": ("Citigroup", "Finance"), "GS": ("Goldman Sachs", "Finance"), "MS": ("Morgan Stanley", "Finance"),
    "V": ("Visa", "Finance"), "MA": ("Mastercard", "Finance"), "AXP": ("American Express", "Finance"),
    "PYPL": ("PayPal", "Finance"), "BLK": ("BlackRock", "Finance"), "SCHW": ("Charles Schwab", "Finance"),
    "UNH": ("UnitedHealth", "Healthcare"), "JNJ": ("Johnson & Johnson", "Healthcare"),
    "LLY": ("Eli Lilly", "Healthcare"), "PFE": ("Pfizer", "Healthcare"), "MRK": ("Merck", "Healthcare"),
    "ABBV": ("AbbVie", "Healthcare"), "TMO": ("Thermo Fisher", "Healthcare"), "ABT": ("Abbott", "Healthcare"),
    "BMY": ("Bristol-Myers Squibb", "Healthcare"), "CVS": ("CVS Health", "Healthcare"),
    "AMGN": ("Amgen", "Healthcare"), "GILD": ("Gilead", "Healthcare"),
    "XOM": ("ExxonMobil", "Energy & Industry"), "CVX": ("Chevron", "Energy & Industry"),
    "COP": ("ConocoPhillips", "Energy & Industry"), "OXY": ("Occidental", "Energy & Industry"),
    "BA": ("Boeing", "Energy & Industry"), "CAT": ("Caterpillar", "Energy & Industry"),
    "GE": ("GE Aerospace", "Energy & Industry"), "LMT": ("Lockheed Martin", "Energy & Industry"),
    "RTX": ("RTX", "Energy & Industry"), "UPS": ("UPS", "Energy & Industry"), "DE": ("Deere", "Energy & Industry"),
    "HON": ("Honeywell", "Energy & Industry"), "NEE": ("NextEra Energy", "Energy & Industry"),
    "T": ("AT&T", "Energy & Industry"), "VZ": ("Verizon", "Energy & Industry"),
}
TOP_TECH = ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AVGO", "ORCL", "AMD", "NFLX", "PLTR"]   # slide 3 of movers
SECTORS = ["All", "Tech", "Finance", "Healthcare", "Consumer", "Energy & Industry"]

# ---- Categories: label, accent, playlist, how to tell it, tags ----------------------------------------
CATEGORIES = {
    "movers": ("BIGGEST MOVERS TODAY", "0x3B82F6", "Biggest Movers",
               "Today's 4 biggest gainers among big US stocks (or the 4 biggest losers if the market fell), "
               "with the reason from the news.",
               ["stock market today", "biggest movers"]),
    "news": ("MARKET NEWS", "0x3B82F6", "Market News",
             "The 3 market stories that mattered most today, and which stocks they moved.",
             ["stock market news", "market news today"]),
    "pe": ("LOWEST P/E STOCKS", "0x3B82F6", "Lowest P/E",
           "The cheapest big stocks by P/E ratio, and why cheap is not always a bargain.",
           ["value stocks", "low PE stocks"]),
    "month": ("TOP PICKS OF ANALYSTS THIS MONTH", "0x3B82F6", "Analysts' Top Picks",
              "The stocks Wall Street analysts rate highest this month, and the event to watch for each.",
              ["stocks to watch", "analyst ratings"]),
    "y2030": ("2030 POTENTIAL", "0x3B82F6", "2030 Potential",
              "The fastest-growing big companies of the last 5 years, and what that pace would mean by 2030 "
              "if it continued.", ["growth stocks", "stocks for 2030"]),
}
NOW = dt.datetime.now(dt.timezone.utc)
US_DATE = (NOW - dt.timedelta(hours=5)).date()           # trading day in New York
EVENING = NOW.weekday() < 5 and (NOW.hour >= 21 or NOW.hour < 2) or (NOW.weekday() == 5 and NOW.hour < 2)


def pick_category():
    """Weekday evenings: movers, then news (once per trading day). Otherwise: P/E, analysts, 2030 in turn."""
    if env("CATEGORY"):
        return env("CATEGORY")
    if EVENING:
        for c in ("movers", "news"):
            if f"{c} {US_DATE}" not in used:
                return c
    return ["pe", "month", "y2030"][sum(1 for u in used if not u.startswith(("movers", "news"))) % 3]


CATEGORY = pick_category()
LABEL, ACCENT, PLAYLIST, STORY, CAT_TAGS = CATEGORIES[CATEGORY]
KIND = "single"                                          # used by the shared sound design

# ---- Settings (override in the workflow env) ----------------------------------
MUSIC = pathlib.Path("music.mp3")                       # fallback track, repo root
MOODS = ("positive", "negative", "neutral")


MOOD_WORDS = {   # file name -> mood, so all tracks can simply be dropped into music/
    "negative": ("dark", "sad", "cinematic", "tense", "suspense", "slowed"),
    "neutral": ("lofi", "chill", "calm", "ambient", "vlog", "focus", "study"),
}


def track_mood(path):
    name = path.stem.lower()
    for mood, words in MOOD_WORDS.items():
        if any(w in name for w in words):
            return mood
    return "positive"                                    # upbeat, hip hop beat, motivational ...


def mood_track(mood):
    """Random track for the mood: music/<mood>/*.mp3 first, else any music/*.mp3 whose name fits the mood."""
    tracks = sorted((pathlib.Path("music") / mood).glob("*.mp3")) or \
        [t for t in sorted(pathlib.Path("music").glob("*.mp3")) if track_mood(t) == mood]
    return random.choice(tracks) if tracks else None


MUSIC_START = float(env("MUSIC_START", "0"))
CHANNEL = env("CHANNEL", "MARKET PULSE")                 # shown in every frame
FILE_NO = len(used) + 1
HEADLINE, COVER_END = "", 0.0                           # set per video
NARRATION = env("NARRATION", "1") == "1"
VOICE = env("VOICE", "en-US-AndrewNeural")
MUSIC_VOL = float(env("MUSIC_VOL", "0.08" if NARRATION else "0.18"))
SFX = env("SFX", "1") == "1"
SFX_VOL = float(env("SFX_VOL", "1.0"))
FUNNY = 0.0
LANGS = [l.strip() for l in env("LANGS", "es,pt,de,fr,it,pl,uk,tr").split(",") if l.strip()]
MIN_SEC, MAX_SEC = 15.0, 40.0
FINNHUB = "https://finnhub.io/api/v1"
DISCLAIMER = ("Not financial advice. This is an automated summary of public market data for education and "
              "entertainment. Do your own research before investing. Data: Finnhub.")

# ---- Layout 1080x1920: black bar | slide | black bar ---------------------------
TOP_BAR, MID_H = 380, 810
BOT_Y = TOP_BAR + MID_H
# ---- Colour themes (THEME in the workflow env): dark (default), light, paper ----------------------------
def bgr(rgb, a="00"):
    return f"&H{a}{rgb[2]:02X}{rgb[1]:02X}{rgb[0]:02X}&"


THEMES = {   # bg, text, muted, hairline, accent, accent-light, up text, down text, up bar, down bar, blue bar
    "dark": dict(bg=(0, 0, 0), ink=(255, 255, 255), muted=(115, 115, 115), line=(38, 38, 38),
                 acc=(59, 130, 246), acc2=(147, 197, 253), up=(57, 232, 20), down=(239, 68, 68),
                 bar_up=(120, 205, 120), bar_down=(222, 112, 112), bar_blue=(112, 150, 222), sub=(200, 200, 200)),
    "light": dict(bg=(255, 255, 255), ink=(17, 24, 39), muted=(107, 114, 128), line=(229, 231, 235),
                  acc=(37, 99, 235), acc2=(96, 165, 250), up=(22, 163, 74), down=(220, 38, 38),
                  bar_up=(134, 214, 140), bar_down=(240, 140, 140), bar_blue=(147, 180, 240), sub=(75, 85, 99)),
    "paper": dict(bg=(246, 243, 236), ink=(15, 32, 64), muted=(120, 113, 105), line=(224, 218, 206),
                  acc=(30, 64, 175), acc2=(59, 130, 246), up=(21, 128, 61), down=(185, 28, 28),
                  bar_up=(163, 207, 160), bar_down=(230, 160, 150), bar_blue=(160, 180, 220), sub=(90, 84, 78)),
}
THEME = THEMES.get(env("THEME", "paper"), THEMES["paper"])   # paper = the channel's main look
WHITE, RED, YELLOW = bgr(THEME["ink"]), bgr(THEME["acc"]), bgr(THEME["acc2"])   # ASS: text, highlight, 2nd
GREEN_ASS, RED_ASS = bgr(THEME["up"]), bgr(THEME["down"])                      # growth up / down
SIGNED = re.compile(r"(?<![\w.])([+\-−])\$?\d[\d,]*\.?\d*%?(?:/yr)?", re.I)
ACCENT = "0x%02X%02X%02X" % THEME["acc"]                 # one accent per theme
ACC_ASS = f"&H00{ACCENT[6:8]}{ACCENT[4:6]}{ACCENT[2:4]}&"
ACC_RGB = tuple(int(ACCENT[k:k + 2], 16) for k in (2, 4, 6))
FONT = pathlib.Path("font.ttf")
FONTS_DIR = str(FONT.resolve().parent) if FONT.exists() else "/usr/share/fonts/truetype/dejavu"
UP, DOWN, INK, BG, MUTED = THEME["up"], THEME["down"], THEME["ink"], THEME["bg"], THEME["muted"]
LINE = THEME["line"]                                    # hairlines
COVER_UP, COVER_DOWN, COVER_BLUE = (57, 232, 20), (239, 68, 68), (59, 130, 246)   # cover looks the same on every theme


# ---- Shared helpers (same as the other bots) -------------------------------------
def x264(crf):
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p"]


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True, cwd=W)


def probe_duration(path):
    try:
        return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                     "-of", "default=nw=1:nk=1", str(path)],
                                    capture_output=True, text=True, check=True).stdout.strip())
    except Exception:
        return 0.0


def font_family():
    try:
        out = subprocess.run(["fc-scan", "--format", "%{family}", str(FONT)],
                             capture_output=True, text=True, check=True).stdout
        return out.split(",")[0].strip() or "DejaVu Sans"
    except Exception:
        return "DejaVu Sans"


def gemini(prompt, ok, rounds=6):
    models = [env("GEMINI_MODEL", "gemini-3.5-flash"), "gemini-flash-latest", "gemini-3.1-flash-lite"]
    for _ in range(rounds):
        for model in models:
            try:
                r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                                  params={"key": os.environ["GEMINI_API_KEY"]}, timeout=(15, 90),
                                  json={"contents": [{"parts": [{"text": prompt}]}],
                                        "generationConfig": {"responseMimeType": "application/json"}})
                if not r.ok:
                    print(model, r.status_code)
                    continue
                data = json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
                if ok(data):
                    return data
                print(model, "incomplete JSON")
            except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as e:
                print(model, "error:", type(e).__name__)
        time.sleep(60)
    raise SystemExit("Gemini unavailable, try later")


def plain(t):
    return re.sub(r"\[/?[ry]\]", "", str(t)).strip()


def caps(t):
    """Upper-case text but keep the [r]/[y] markers and /yr working."""
    t = str(t).upper()
    for m in ("R", "Y"):
        t = t.replace(f"[{m}]", f"[{m.lower()}]").replace(f"[/{m}]", f"[/{m.lower()}]")
    return t


def to_ass(t):
    t = caps(t).replace("\\", "").replace("{", "").replace("}", "").replace("\n", " ")
    t = re.sub(r"\[(r|y)\]([^\[]*?[+\-−]\d[^\[]*?)\[/\1\]", r"\2", t)    # signed numbers get their own colour
    t = SIGNED.sub(lambda m: f"{{\\c{GREEN_ASS if m.group(1) == '+' else RED_ASS}}}{m.group(0)}{{\\c{WHITE}}}", t)
    for tag, col in (("r", RED), ("y", YELLOW)):
        t = re.sub(rf"\[{tag}\](.*?)\[/{tag}\]", lambda m: f"{{\\c{col}}}{m.group(1)}{{\\c{WHITE}}}", t)
    return plain(t)


def ass_time(sec):
    cs = int(round(max(0, sec) * 100))
    return f"{cs // 360000}:{(cs // 6000) % 60:02d}:{(cs // 100) % 60:02d}.{cs % 100:02d}"


async def _tts(text, path):
    import edge_tts
    try:
        comm = edge_tts.Communicate(text, VOICE, rate="+5%", boundary="WordBoundary")
    except TypeError:
        comm = edge_tts.Communicate(text, VOICE, rate="+5%")
    words = []
    with open(path, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append((chunk["text"], chunk["offset"] / 1e7))
    return words


def tighten(path, words):
    """Cuts every pause longer than 0.25 s down to ~0.12 s and shifts the word timings to match."""
    log = subprocess.run(["ffmpeg", "-i", str(path), "-af", "silencedetect=noise=-40dB:d=0.25", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    cuts = [(a + 0.06, b - 0.06) for a, b in zip(starts, ends) if b - a > 0.25]
    if not cuts:
        return words
    keep, prev = [], 0.0
    for a, b in cuts:
        keep.append(f"between(t,{prev:.3f},{a:.3f})")
        prev = b
    keep.append(f"gte(t,{prev:.3f})")
    tmp = path.with_name("voice_tight.mp3")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-af",
                    f"aselect='{'+'.join(keep)}',asetpts=N/SR/TB", str(tmp)], check=True)
    tmp.replace(path)
    shift = lambda t: t - sum(b - a for a, b in cuts if b <= t + 0.001)
    return [(w[0], max(0.0, shift(w[1])), *w[2:]) for w in words]


def build_sfx(total, timed, cuts, shots, path):
    """Synthesized sounds. Discrete effects never closer than 1 s (the most important wins); under them a low
    tension bed that keeps rising and cuts off on the last frame, so the loop restarts the tension."""
    sr = 22050
    buf = [0.0] * int(sr * (total + 0.05))
    rnd = random.Random(len(timed) * 31 + int(total * 10))

    def add(start, samples, gain=1.0):
        i0 = int(start * sr)
        for k, v in enumerate(samples[:max(0, len(buf) - i0)]):
            buf[i0 + k] += v * gain

    def noise(n, alpha):                              # low-passed noise
        y, out = 0.0, []
        for _ in range(n):
            y += alpha * (rnd.uniform(-1, 1) - y)
            out.append(y)
        return out

    def tap():
        n = int(0.05 * sr)
        nz = noise(n, 0.18)
        return [nz[k] * math.exp(-k / (0.008 * sr)) * 0.9 +
                0.25 * math.sin(2 * math.pi * 180 * k / sr) * math.exp(-k / (0.012 * sr)) for k in range(n)]

    def whoosh(d=0.5):
        n, y, out = int(d * sr), 0.0, []
        for k in range(n):
            p = k / n
            y += (0.03 + 0.2 * math.sin(math.pi * p)) * (rnd.uniform(-1, 1) - y)
            out.append(y * math.sin(math.pi * p) ** 2)
        return out

    def boom(f0=55, d=1.4, nmix=0.3):
        n, ph, out = int(d * sr), 0.0, []
        nz = noise(n, 0.05)
        for k in range(n):
            t = k / sr
            ph += 2 * math.pi * f0 * (1 - 0.35 * t / d) / sr
            out.append((math.sin(ph) + nmix * nz[k] * 3) * math.exp(-t / (d * 0.3)))
        return out

    def funny():                                       # a silly sound that does not match the picture
        kind, n, ph, out = rnd.choice(["boing", "fart", "slide"]), int(0.6 * sr), 0.0, []
        for k in range(n):
            t = k / sr
            if kind == "boing":
                f = 180 + 120 * math.sin(2 * math.pi * 9 * t) * math.exp(-t * 4)
                v = math.sin(ph) * math.exp(-t * 4)
            elif kind == "fart":
                f = 70 + 25 * rnd.uniform(-1, 1) - 30 * t
                v = (2 * (ph / (2 * math.pi) % 1) - 1) * min(1, t * 30) * math.exp(-t * 3)
            else:
                f = 400 + 900 * t
                v = math.sin(ph) * min(1, t * 20, (0.6 - t) * 10)
            ph += 2 * math.pi * f / sr
            out.append(0.8 * v)
        return out

    events = []                                        # (time, priority, samples, gain)
    events.append((0.0, 9, boom(60, 1.0, 0.3), 0.8))
    for idx, (text, s, _) in enumerate(timed):
        events.append((s, 5 if "[r]" in text else 2, boom(80, 0.5, 0.15) if "[r]" in text else tap(),
                       0.3 if "[r]" in text else 0.55))
    for t in cuts:
        events.append((max(0, t - 0.2), 3, whoosh(0.45), 0.45))
    t = 0.0
    for sh in shots:
        if sh["kind"] == "split":
            events.append((t + 0.05, 7, boom(60, 0.9, 0.35), 0.6))
        t += sh["dur"]
    events.append((max(0, total - shots[-1]["dur"]), 8, boom(70, 0.8, 0.3), 0.7))   # payoff hit
    if CATEGORY == "classified":                     # soft Morse ... --- ...
        morse = []
        for d in [0.07] * 3 + [0.21] * 3 + [0.07] * 3:
            n = int(d * sr)
            morse += [0.35 * math.sin(2 * math.pi * 650 * k / sr) * min(1, k / 80, (n - k) / 80) for k in range(n)]
            morse += [0.0] * int(0.07 * sr)
        events.append((0.5, 6, morse, 0.5))
    if KIND != "quiz" and CATEGORY in ("myth", "versus") and len(timed) > 2 and rnd.random() < FUNNY:
        events.append((timed[1][1] + 0.3, 8, funny(), 0.6))
    taken = []
    for t, prio, smp, g in sorted(events, key=lambda e: -e[1]):
        if all(abs(t - u) >= 1.0 for u in taken):      # max 1 effect per second
            taken.append(t)
            add(t, smp, g)
    bed = noise(len(buf), 0.006)                       # rising tension bed + slow low drone, hard cut at end
    ph = 0.0
    for k in range(len(buf)):
        p = k / len(buf)
        ph += 2 * math.pi * (42 + 14 * p) / sr
        buf[k] += (bed[k] * 1.8 + 0.12 * math.sin(ph)) * (0.25 + 1.6 * p * p) * min(1, k / (0.3 * sr))
    peak = max(1e-6, max(abs(v) for v in buf))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(array.array("h", (int(v / peak * 26000) for v in buf)).tobytes())


def render(ass_path, total):
    args = ["-i", "bg.mp4"]
    on = f"enable='gte(t,{COVER_END:.2f})'"
    fc = [f"[0:v]drawbox=x=0:y={TOP_BAR - 2}:w=1080:h=2:color={ACCENT}@1:t=fill:{on},drawbox=x=0:y={BOT_Y}:w=1080:"
          f"h=2:color={ACCENT}@1:t=fill:{on},ass={ass_path.resolve()}:fontsdir={FONTS_DIR}[v]"]
    srcs = []                                        # (input args, filter) for each audio layer
    if NARRATION:
        srcs.append((["-i", "voice.mp3"], "highpass=f=90,lowpass=f=8500,deesser=i=0.6"))
    if MUSIC.exists():
        srcs.append((["-ss", str(MUSIC_START), "-stream_loop", "-1", "-i", str(MUSIC.resolve())],
                     f"volume={MUSIC_VOL},afade=t=in:d=0.3"))
    if SFX and (W / "sfx.wav").exists():
        srcs.append((["-i", "sfx.wav"], f"lowpass=f=6000,volume={0.12 * SFX_VOL:.3f}"))
    if not srcs:
        srcs.append((["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"], "anull"))
    for k, (a, f) in enumerate(srcs, 1):
        args += a
        fc.append(f"[{k}:a]aresample=44100,{f}[a{k}]")
    fc.append("".join(f"[a{k}]" for k in range(1, len(srcs) + 1))
              + f"amix=inputs={len(srcs)}:duration=longest:normalize=0[a]")
    ff(*args, "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}", *x264(21),
       "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", "-movflags", "+faststart", "final.mp4")


def youtube():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=Credentials(
        None, refresh_token=os.environ["YT_REFRESH_TOKEN"], token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"]))


def translate(title, question, story):
    """Localized title/description so YouTube shows them in the viewer's language."""
    if not LANGS:
        return {}
    try:
        tr = gemini(
            f"Translate this YouTube Short metadata about the US stock market into these languages: {', '.join(LANGS)} "
            "(ISO 639-1 codes). Natural, catchy wording for each language, keep company names, tickers, numbers and dates exact, "
            f"title max 80 characters, no hashtags.\nTITLE: {title}\nQUESTION: {question}\nSTORY:\n{story}\n"
            'Return JSON: {"<code>": {"title": "...", "question": "...", "story": "..."}, ...}',
            lambda d: isinstance(d, dict) and sum(isinstance(d.get(l), dict) and bool(d[l].get("title"))
                                                  for l in LANGS) >= len(LANGS) // 2, rounds=2)
    except SystemExit:
        print("translation skipped")
        return {}
    return {l: v for l, v in tr.items() if l in LANGS and isinstance(v, dict) and v.get("title")}


def add_to_playlist(yt, vid):
    try:
        items = yt.playlists().list(part="snippet", mine=True, maxResults=50).execute().get("items", [])
        pl = next((i["id"] for i in items if i["snippet"]["title"] == PLAYLIST), None) or \
            yt.playlists().insert(part="snippet,status", body={
                "snippet": {"title": PLAYLIST, "description": f"{PLAYLIST}: stock market Shorts."},
                "status": {"privacyStatus": "public"}}).execute()["id"]
        yt.playlistItems().insert(part="snippet", body={"snippet": {
            "playlistId": pl, "resourceId": {"kind": "youtube#video", "videoId": vid}}}).execute()
        print("playlist:", PLAYLIST)
    except Exception as e:
        print("playlist skipped (re-run auth.py with new scopes):", str(e)[:200])


def post_comment(yt, vid, data):
    q = plain(data.get("question", ""))
    try:
        if q:
            yt.commentThreads().insert(part="snippet", body={"snippet": {"videoId": vid, "topLevelComment": {
                "snippet": {"textOriginal": f"{q} 👇"}}}}).execute()
            print("comment posted")
    except Exception as e:
        print("comment skipped (re-run auth.py with new scopes):", str(e)[:200])


def set_category(c):
    global CATEGORY, LABEL, ACCENT, PLAYLIST, STORY, CAT_TAGS, ACC_ASS, ACC_RGB
    CATEGORY = c
    LABEL, ACCENT, PLAYLIST, STORY, CAT_TAGS = CATEGORIES[c]
    ACCENT = "0x%02X%02X%02X" % THEME["acc"]
    ACC_ASS = f"&H00{ACCENT[6:8]}{ACCENT[4:6]}{ACCENT[2:4]}&"
    ACC_RGB = tuple(int(ACCENT[k:k + 2], 16) for k in (2, 4, 6))


# ---- Market data (Finnhub, free key) -------------------------------------------
def fh(path, **params):
    """One Finnhub call; paced under the free limit (60/min). None if unavailable."""
    for _ in range(4):
        try:
            r = requests.get(f"{FINNHUB}/{path}", params={**params, "token": os.environ["FINNHUB_API_KEY"]},
                             timeout=30)
            time.sleep(1.05)
            if r.status_code == 429:
                time.sleep(20)
                continue
            if r.status_code in (401, 403):
                print(path, r.status_code, "(not available on this plan)")
                return None
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            print(path, "error:", type(e).__name__)
            time.sleep(5)
    return None


def company_news(t, days=3, k=3):
    """Latest headlines + short summaries for one ticker, as raw facts for the 'why' line."""
    news = fh("company-news", symbol=t, **{"from": str(US_DATE - dt.timedelta(days=days)), "to": str(US_DATE)}) or []
    out = [f"{n['headline']} ({str(n.get('summary', ''))[:220]})" for n in news[:k] if n.get("headline")]
    return " | ".join(out) or "none"


def tickers(sector):
    return [t for t, (_, s) in UNIVERSE.items() if sector == "All" or s == sector]


def pct(x):
    return f"{x:+.1f}%"


def money(x):
    return f"${x:,.2f}"


QUOTES = {}


def quote(t):
    """Latest quote, cached per run so every slide shows the same number."""
    if t not in QUOTES:
        q = fh("quote", symbol=t) or {}
        QUOTES[t] = q if q.get("c") and q.get("dp") is not None else None
    return QUOTES[t]


def metrics(sector):
    out = {}
    for t in tickers(sector):
        m = (fh("stock/metric", symbol=t, metric="all") or {}).get("metric") or {}
        if m:
            out[t] = m
    return out


def pick_sector(cat, period):
    """First sector (rotating) not yet covered by this category in this period."""
    start = sum(1 for u in used if u.startswith(cat))
    for k in range(len(SECTORS)):
        s = SECTORS[(start + k) % len(SECTORS)]
        if f"{cat} {s} {period}" not in used:
            return s
    return SECTORS[start % len(SECTORS)]


def data_movers():
    qs = {t: quote(t) for t in UNIVERSE}
    qs = {t: q for t, q in qs.items() if q}
    if len(qs) < 20 or max(abs(q["dp"]) for q in qs.values()) < 0.3:   # weekend / holiday / no data
        return None
    ranked = sorted(qs, key=lambda t: qs[t]["dp"])
    avg = sum(q["dp"] for q in qs.values()) / len(qs)                    # the whole basket decides the story
    global DAY_WORD
    DAY_WORD = "GAINERS" if avg >= 0 else "TANKERS"                       # shown above the 4 stock cards
    pick = ranked[::-1][:4] if avg >= 0 else ranked[:4]                   # top 4 gainers (or losers)
    items = []
    for t in pick:
        heads = company_news(t, days=2)
        q = qs[t]
        items.append({"ticker": t, "name": UNIVERSE[t][0], "main": money(q["c"]),
                      "badge": (pct(q["dp"]), UP if q["dp"] >= 0 else DOWN),
                      "rows": [("Day range", f"{money(q['l'])} - {money(q['h'])}"), ("Previous close", money(q["pc"]))],
                      "bar": q["dp"], "bar_txt": pct(q["dp"]),
                      "fact": f"{t} ({UNIVERSE[t][0]}): closed at {money(q['c'])}, {pct(q['dp'])} today. "
                              f"Recent news: {heads}"})
    mood = "positive" if avg >= 0.4 else "negative" if avg <= -0.4 else "neutral"
    tech = [{"ticker": t, "bar": qs[t]["dp"], "bar_txt": pct(qs[t]["dp"])} for t in TOP_TECH if t in qs]
    spy = quote("SPY")
    bench = f"S&P 500 (SPY) was {pct(spy['dp'])} today" if spy else US_DATE.strftime("%b %d, %Y")
    extra = "Top tech stocks today: " + ", ".join(f"{x['ticker']} {x['bar_txt']}" for x in tech) + \
        (f". S&P 500 (SPY) {pct(spy['dp'])} today" if spy else "")
    return {"items": items, "key": f"movers {US_DATE}", "sub": US_DATE.strftime("%b %d, %Y"),
            "board": "Top tech stocks today", "board_items": tech, "board_sub": bench, "extra": extra,
            "mood": mood}


def data_news():
    raw = fh("news", category="general") or []
    cut = NOW.timestamp() - 30 * 3600
    stories = [n for n in raw if n.get("datetime", 0) >= cut and n.get("headline")][:15]
    if len(stories) < 3:
        return None
    listing = "\n".join(f"{i}. {n['headline']} — {str(n.get('summary', ''))[:300]}" for i, n in enumerate(stories))
    pick = gemini(
        "From these stock market news items pick the 3 that matter most to everyday investors today. For each give "
        "a neutral title of max 6 words in your own words and 0-2 US stock tickers it is about.\n" + listing +
        "\nAlso judge the overall mood of these stories for investors: positive, negative or neutral."
        '\nReturn JSON: {"mood": "positive", "stories": [{"index": 0, "title": "...", "tickers": ["AAPL"]}]}',
        lambda d: isinstance(d, dict) and len(d.get("stories", [])) >= 3)
    mood = str(pick.get("mood", "neutral")).lower()
    items = []
    for s in pick["stories"][:3]:
        n = stories[int(s.get("index", 0)) % len(stories)]
        chips, facts = [], []
        for t in [str(x).upper() for x in s.get("tickers", [])][:2]:
            q = quote(t) if re.fullmatch(r"[A-Z.]{1,6}", t) else None
            if q:
                chips.append((t, pct(q["dp"]), UP if q["dp"] >= 0 else DOWN))
                facts.append(f"{t} {pct(q['dp'])} today")
        items.append({"ticker": f"STORY {len(items) + 1}", "name": str(s.get("title", ""))[:60], "chips": chips,
                      "bar": None,
                      "fact": f"{n['headline']} — {str(n.get('summary', ''))[:400]} ({n.get('source', '')}). "
                              f"{'; '.join(facts)}"})
    return {"items": items, "key": f"news {US_DATE}", "sub": US_DATE.strftime("%b %d, %Y"), "board": None,
            "mood": mood if mood in MOODS else "neutral"}


def data_pe():
    sector = pick_sector("pe", US_DATE.strftime("%Y-%m"))
    ms = metrics(sector)
    pes = {t: m.get("peTTM") or m.get("peBasicExclExtraTTM") for t, m in ms.items()}
    pes = {t: p for t, p in pes.items() if p and 0 < p < 300}
    if len(pes) < 4:
        return None
    items = []
    for t in sorted(pes, key=pes.get)[:4]:
        m = ms[t]
        ret, gr, dy = m.get("52WeekPriceReturnDaily"), m.get("revenueGrowthTTMYoy"), m.get("currentDividendYieldTTM")
        rows = [(k, v) for k, v in (("1-year return", pct(ret) if ret is not None else None),
                                    ("Revenue growth", pct(gr) if gr is not None else None),
                                    ("Dividend yield", f"{dy:.1f}%" if dy else None)) if v]
        items.append({"ticker": t, "name": UNIVERSE[t][0], "main": f"P/E {pes[t]:.1f}", "rows": rows,
                      "bar": pes[t], "bar_txt": f"{pes[t]:.1f}",
                      "fact": f"{t} ({UNIVERSE[t][0]}, {UNIVERSE[t][1]}): P/E {pes[t]:.1f}; "
                              + "; ".join(f"{k} {v}" for k, v in rows) + f". Recent news: {company_news(t, days=14, k=2)}"})
    return {"items": items, "key": f"pe {sector} {US_DATE:%Y-%m}", "sub": f"Sector: {sector}", "board": "P/E ratio"}


def data_month():
    sector = pick_sector("month", US_DATE.strftime("%Y-%m"))
    first = US_DATE.replace(day=1)
    last = (first + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
    cal = (fh("calendar/earnings", **{"from": str(US_DATE), "to": str(last)}) or {}).get("earningsCalendar", [])
    earn = {e["symbol"]: e["date"] for e in cal if e.get("symbol") in UNIVERSE}
    score = {}
    for t in tickers(sector):
        rec = fh("stock/recommendation", symbol=t) or []
        if rec:
            r = rec[0]
            total = sum(r.get(k, 0) for k in ("strongBuy", "buy", "hold", "sell", "strongSell"))
            if total >= 10:
                score[t] = (round(100 * (r.get("strongBuy", 0) + r.get("buy", 0)) / total), total, r)
    if len(score) < 4:
        return None
    items = []
    for t in sorted(score, key=lambda t: (score[t][0], score[t][1]), reverse=True)[:4]:
        share, total, r = score[t]
        when = dt.date.fromisoformat(earn[t]).strftime("%b %d") if t in earn else "not this month"
        items.append({"ticker": t, "name": UNIVERSE[t][0], "main": f"{share}% Buy",
                      "rows": [("Analysts", str(total)), ("Strong buy", str(r.get("strongBuy", 0))),
                               ("Earnings", when)],
                      "bar": share, "bar_txt": f"{share}%",
                      "fact": f"{t} ({UNIVERSE[t][0]}): {share}% of {total} analysts rate it Buy or Strong Buy "
                              f"({r.get('strongBuy', 0)} Strong Buy); next earnings: {when}" + f". Recent news: {company_news(t, days=14, k=2)}"})
    return {"items": items, "key": f"month {sector} {US_DATE:%Y-%m}", "sub": f"{US_DATE:%B %Y} · {sector}",
            "board": "Analysts rating Buy"}


def data_y2030():
    sector = pick_sector("y2030", US_DATE.strftime("%Y-%m"))
    ms = metrics(sector)
    g = {t: m.get("revenueGrowth5Y") for t, m in ms.items()}
    g = {t: v for t, v in g.items() if v is not None and -50 < v < 300}
    if len(g) < 4:
        return None
    years = max(1, 2030 - US_DATE.year)
    items = []
    for t in sorted(g, key=g.get, reverse=True)[:4]:
        mult = (1 + g[t] / 100) ** years
        eps = ms[t].get("epsGrowth5Y")
        rows = [("5-yr revenue growth", f"{g[t]:+.1f}%/yr")] + ([("5-yr EPS growth", f"{eps:+.1f}%/yr")] if eps else []) \
            + [(f"Same pace to 2030", f"x{mult:.1f} revenue")]
        items.append({"ticker": t, "name": UNIVERSE[t][0], "main": f"{g[t]:+.1f}%/yr", "rows": rows,
                      "bar": g[t], "bar_txt": f"{g[t]:+.1f}%",
                      "fact": f"{t} ({UNIVERSE[t][0]}): revenue grew {g[t]:.1f}% per year over 5 years"
                              + (f", EPS {eps:.1f}% per year" if eps else "")
                              + f"; if that pace continued for {years} more years revenue would be x{mult:.1f} by 2030 "
                                "(hypothetical, not a forecast)" + f". Recent news: {company_news(t, days=14, k=2)}"})
    return {"items": items, "key": f"y2030 {sector} {US_DATE:%Y-%m}", "sub": f"Sector: {sector}",
            "board": "5-year revenue growth per year"}


DATA = {"movers": data_movers, "news": data_news, "pe": data_pe, "month": data_month, "y2030": data_y2030}


def get_data():
    order = [CATEGORY] + [c for c in ("pe", "month", "y2030") if c != CATEGORY]
    for c in order:
        set_category(c)
        d = DATA[c]()
        if d and d["key"] not in used:
            return d
        print("no data for", c)
    raise SystemExit("No market data available")


# ---- Script --------------------------------------------------------------------
def numbers_ok(lines, facts):
    """Every number spoken must come from the data (years and small counts allowed)."""
    known = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.?\d*", facts)]
    for l in lines:
        for x in re.findall(r"\d[\d,]*\.?\d*", plain(l)):
            v = float(x.replace(",", "").rstrip("."))
            if v <= 10 or 2000 <= v <= 2040 or any(abs(v - k) <= 0.06 for k in known):
                continue
            print("number not in data:", x, "|", plain(l))
            return False
    return True


def gen_script(d):
    n = len(d["items"])
    facts = "\n".join(f"ITEM {i + 1}: {it['fact']}" for i, it in enumerate(d["items"])) + \
        (f"\nMARKET CONTEXT (for the last line only): {d['extra']}" if d.get("extra") else "")
    rules = {
        "pe": "- One line must say a low P/E can mean the market expects trouble (a value trap).\n",
        "y2030": "- Say clearly the 2030 numbers are 'if this pace continued', never a prediction.\n",
        "month": "- Present it as analysts' opinion, which can be wrong.\n",
    }.get(CATEGORY, "")
    prompt = (
        "You write a 20-30 second YouTube Short about the US stock market for beginners, voiced by a calm, "
        f"confident narrator. Topic: {STORY} ({d['sub']}).\nFACTS (the ONLY source; copy numbers exactly as written, "
        f"never invent or round differently):\n{facts}\nRules:\n"
        "- headline: the hook, max 7 words, spoken first and shown the whole time; a number or a contradiction; "
        "must not reveal the final takeaway. Never start with 'Did you know'.\n"
        f"- lines: exactly {n + 1} narration lines, max 12 words each. Line k (1..{n}) is about ITEM k, in order. "
        "Line k may use ONLY ITEM k's own facts and recent news, never another item's news; every stock has its "
        "own reason, so all item lines must be different. "
        "The screen already shows the ticker, company name, price and its % move, so a line must NOT repeat them "
        "and must NOT say 'moved' or 'on the news'. Instead state the concrete CAUSE or driver from that item's "
        "facts and recent news, short and specific, with a number if the facts have one (style example: "
        "'New Apple subscriptions deal; $5.5B free cash flow'). If the facts give no clear cause, say it honestly "
        "(e.g. 'No company news; the whole sector fell'). Never invent a cause. "
        f"Line {n + 1} is the single most important takeaway or risk.\n"
        "- NEVER tell viewers to buy, sell or hold anything, and never give your own price predictions. "
        "Do not copy news sentences; say it in your own words.\n" + rules +
        "- Write every change or growth number with its sign (+5.8%, -2.1%, +44.6%/yr); other numbers without a sign.\n"
        "- In headline and each line wrap the most important number or name in [r]...[/r] and at most one other "
        "detail in [y]...[/y].\n"
        "- question: one short question to viewers that invites comments (max 10 words, no markers).\n"
        "- title: up to 70 characters with a number, honest, no markers.\n"
        'Return JSON: {"title": "...", "headline": "...", "lines": ["..."], "question": "...", "tags": ["5-8 tags"]}')
    ok = lambda x: isinstance(x, dict) and x.get("headline") and len(x.get("lines", [])) == n + 1
    def distinct(lines):
        """No two stock lines may share most of their words (each stock needs its own cause)."""
        sets = [set(re.findall(r"[a-z]{4,}", plain(l).lower())) for l in lines[:n]]
        for a in range(len(sets)):
            for b in range(a + 1, len(sets)):
                if sets[a] and len(sets[a] & sets[b]) / len(sets[a] | sets[b]) > 0.5:
                    print("lines too similar:", lines[a], "|", lines[b])
                    return False
        return True

    for _ in range(3):
        data = gemini(prompt, ok)
        if numbers_ok([data["headline"]] + data["lines"], facts) and distinct(data["lines"]):
            return data
    raise SystemExit("Script kept using numbers that are not in the data")


# ---- Slides (drawn with Pillow) ------------------------------------------------
def font(size, bold=True):
    from PIL import ImageFont
    for p in ([str(FONT)] if FONT.exists() else []) + [
            f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf"]:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def canvas():
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (1080, MID_H), BG)
    d = ImageDraw.Draw(im)
    d.rectangle([70, 52, 130, 58], fill=ACC_RGB)       # short blue rule, top left
    return im, d


def tone(v):
    """Green for a positive change, red for a negative one, white for everything else."""
    v = str(v).strip()
    return UP if v.startswith("+") else DOWN if v.startswith(("-", "−")) and re.match(r"[-−]\$?\d", v) else INK


def wrap(d, text, f, width):
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    return lines + ([cur] if cur else [])


def slide_title(d0, path):
    im, d = canvas()
    y = 230
    for line in wrap(d, LABEL, font(84), 900):
        d.text((70, y), line, font=font(84), fill=INK)
        y += 100
    d.text((70, y + 20), d0["sub"], font=font(44, False), fill=ACC_RGB)
    d.text((70, MID_H - 90), "Data: Finnhub  ·  Not financial advice", font=font(28, False), fill=MUTED)
    im.save(path)


LOGOS = {}


def logo_for(t):
    """Company logo from the Finnhub company profile (as provided by the data feed); None if unavailable."""
    if t in LOGOS:
        return LOGOS[t]
    LOGOS[t] = None
    if re.fullmatch(r"[A-Z.]{1,6}", t):
        url = (fh("stock/profile2", symbol=t) or {}).get("logo")
        if url:
            try:
                r = requests.get(url, timeout=30)
                r.raise_for_status()
                p = W / f"logo_{t}.img"
                p.write_bytes(r.content)
                from PIL import Image
                Image.open(p).verify()
                LOGOS[t] = p
            except Exception as e:
                print("logo skipped:", t, type(e).__name__)
    return LOGOS[t]


def logo_badge(t, height):
    """Logo on a white rounded badge (readable on black), sized to the logo's shape; None if no logo."""
    from PIL import Image, ImageDraw
    p = logo_for(t)
    if not p:
        return None
    try:
        lg = Image.open(p).convert("RGBA")
    except Exception:
        return None
    pad = int(height * .14)
    lg.thumbnail((int(height * 3.2), height - 2 * pad), Image.LANCZOS)
    badge = Image.new("RGBA", (lg.width + 2 * pad, height), (0, 0, 0, 0))
    ImageDraw.Draw(badge).rounded_rectangle([0, 0, badge.width - 1, height - 1], radius=height // 5,
                                            fill=(255, 255, 255, 255), outline=LINE + (255,), width=2)
    badge.alpha_composite(lg, (pad, (height - lg.height) // 2))
    return badge


def slide_card(it, i, n, path):
    im, d = canvas()
    d.text((145, 36), f"{i}/{n}", font=font(30, False), fill=MUTED)       # next to the blue rule
    d.text((70, 120), it["ticker"], font=font(120), fill=INK)
    badge = logo_badge(it["ticker"], 120) if re.fullmatch(r"[A-Z.]{1,6}", it["ticker"]) else None
    if badge:                                                                # company logo, top right
        im.paste(badge, (1010 - badge.width, 130), badge)
    y = 270
    for line in wrap(d, str(it["name"]).upper(), font(48, False), 920 if not badge else 1010 - badge.width - 110)[:2]:
        d.text((74, y), line, font=font(48, False), fill=MUTED if it.get("main") else INK)
        y += 60
    if it.get("main"):
        d.text((70, y + 30), it["main"], font=font(96), fill=tone(it["main"]))
        if it.get("badge"):
            txt, col = it["badge"]
            x0 = 70 + d.textlength(it["main"], font=font(96)) + 30
            arrow = "▲ " if col == UP else "▼ "
            d.text((x0, y + 52), arrow + txt, font=font(56), fill=col)
        y += 160
    for t, v, col in it.get("chips", []):              # news: tickers it moved
        d.text((74, y + 30), t, font=font(52), fill=INK)
        d.text((74 + d.textlength(t + "  ", font=font(52)), y + 30), ("▲ " if col == UP else "▼ ") + v,
               font=font(52), fill=col)
        y += 110
    for k, v in it.get("rows", []):
        d.text((74, y + 10), k.upper(), font=font(34, False), fill=MUTED)
        d.text((1010 - d.textlength(v, font=font(40)), y + 6), v, font=font(40), fill=tone(v))
        d.line([(74, y + 62), (1010, y + 62)], fill=LINE, width=2)
        y += 72
    im.save(path)


BAR_UP, BAR_DOWN, BAR_BLUE = THEME["bar_up"], THEME["bar_down"], THEME["bar_blue"]   # softer chart colours


def slide_board(d0, path):
    """Ranking like a classic bar infographic: centered title, bars from the left, bold value inside the
    bar's end, company logo (or ticker) right after the bar. Black background."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (1080, MID_H), BG)
    d = ImageDraw.Draw(im)
    title, size = d0["board"].upper(), 54
    while d.textlength(title, font=font(size)) > 980 and size > 32:
        size -= 2
    d.text(((1080 - d.textlength(title, font=font(size))) / 2, 72), title, font=font(size), fill=INK)   # below the brand
    sub = str(d0.get("board_sub") or d0.get("sub", "")).upper()
    d.text(((1080 - d.textlength(sub, font=font(30, False))) / 2, 142), sub, font=font(30, False), fill=THEME["sub"])
    items = sorted(d0.get("board_items") or d0["items"], key=lambda it: it["bar"],
                   reverse=CATEGORY != "pe")                                   # P/E: cheapest on top
    vmax = max(abs(it["bar"]) for it in items) or 1
    x0, tag_w = 30, 290
    span = 1050 - x0 - tag_w
    top = 205
    gap = (MID_H - top - 20) // max(1, len(items))
    bh = min(120, int(gap * .8))
    vf = font(int(min(bh * .55, 52)))
    for k, it in enumerate(items):
        y = top + k * gap
        col = (BAR_UP if it["bar"] >= 0 else BAR_DOWN) if CATEGORY in ("movers", "y2030") else BAR_BLUE
        txt = it["bar_txt"]
        w = max(int(span * abs(it["bar"]) / vmax), int(d.textlength(txt, font=vf)) + 50)
        d.rounded_rectangle([x0, y, x0 + w, y + bh], radius=6, fill=col)
        d.text((x0 + w - 22 - d.textlength(txt, font=vf), y + (bh - vf.size) / 2 - 3), txt, font=vf, fill=(0, 0, 0))
        badge = logo_badge(it["ticker"], int(bh * .78)) if re.fullmatch(r"[A-Z.]{1,6}", it["ticker"]) else None
        if badge:
            im.paste(badge, (x0 + w + 16, y + (bh - badge.height) // 2), badge)
        else:
            tf = font(int(min(bh * .55, 52)))
            d.text((x0 + w + 18, y + (bh - tf.size) / 2 - 3), it["ticker"], font=tf, fill=INK)
    im.save(path)


# ---- Cover (first seconds): illustrated market background + tag + big headline ---------------------------
COND_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"
NAVY, NAVY2 = (6, 18, 40), (14, 40, 84)


def cond_font(size):
    from PIL import ImageFont
    for p in ([str(FONT)] if FONT.exists() else []) + [COND_FONT, "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def cover_background(mood, seed):
    """Original illustration: night skyline, candlesticks, rising bars and a glowing arrow (down if bad news)."""
    from PIL import Image, ImageDraw, ImageFilter
    rnd = random.Random(seed)
    W_, H_ = 1080, 1920
    up = mood != "negative"
    col = COVER_UP if mood == "positive" else COVER_DOWN if mood == "negative" else COVER_BLUE
    im = Image.new("RGB", (W_, H_), NAVY)
    d = ImageDraw.Draw(im)
    for y in range(H_):                                   # night-sky gradient
        k = y / H_
        d.line([(0, y), (W_, y)], fill=tuple(int(NAVY2[c] * (1 - k) + NAVY[c] * k) for c in range(3)))
    for x in range(0, W_, 60):                            # faint data grid
        d.line([(x, 0), (x, H_)], fill=(20, 48, 92), width=1)
    for y in range(0, H_, 60):
        d.line([(0, y), (W_, y)], fill=(20, 48, 92), width=1)
    # skyline silhouette with lit windows
    x = -20
    while x < W_:
        w, h = rnd.randint(70, 160), rnd.randint(380, 980)
        top = 1350 - h
        d.rectangle([x, top, x + w, 1400], fill=(10, 22, 44))
        for wy in range(top + 20, 1340, 34):
            for wx in range(x + 12, x + w - 14, 26):
                if rnd.random() < 0.35:
                    d.rectangle([wx, wy, wx + 10, wy + 16], fill=(70, 110, 170) if rnd.random() < .8 else (230, 200, 120))
        x += w + rnd.randint(4, 20)
    # candlesticks across the sky, trending with the mood
    glow = Image.new("RGB", (W_, H_), (0, 0, 0))
    g = ImageDraw.Draw(glow)
    price = 900 if up else 350
    for i in range(26):
        cx = 60 + i * 38
        step = rnd.uniform(-38, 12) if up else rnd.uniform(-12, 38)
        o, c = price, price + step
        green = c < o
        hi, lo = min(o, c) - rnd.uniform(8, 40), max(o, c) + rnd.uniform(8, 40)
        cc = COVER_UP if green else COVER_DOWN
        d.line([(cx, hi), (cx, lo)], fill=cc, width=3)
        d.rectangle([cx - 11, min(o, c), cx + 11, max(o, c) + 3], fill=cc)
        g.rectangle([cx - 11, min(o, c), cx + 11, max(o, c) + 3], fill=cc)
        price = c
    # rising (or falling) bars at the bottom of the art
    for i in range(10):
        bh = (90 + i * 45 if up else 520 - i * 45) + rnd.randint(-20, 20)
        bx = 560 + i * 50
        d.rectangle([bx, 1380 - bh, bx + 34, 1380], fill=tuple(int(v * .75) for v in col))
        g.rectangle([bx, 1380 - bh, bx + 34, 1380], fill=tuple(int(v * .5) for v in col))
    # big zigzag arrow
    pts = [(40, 1250), (230, 1080), (330, 1170), (520, 900), (620, 990), (860, 520)] if up else \
          [(40, 420), (230, 600), (330, 510), (520, 790), (620, 700), (860, 1160)]
    for layer, wdt in ((g, 70), (d, 34)):
        layer.line(pts, fill=col, width=wdt, joint="curve")
    (x1, y1), (x2, y2) = pts[-2], pts[-1]
    ang = math.atan2(y2 - y1, x2 - x1)
    tip = (x2 + 70 * math.cos(ang), y2 + 70 * math.sin(ang))
    head = [tip, (x2 + 60 * math.cos(ang + 2.1), y2 + 60 * math.sin(ang + 2.1)),
            (x2 + 60 * math.cos(ang - 2.1), y2 + 60 * math.sin(ang - 2.1))]
    for layer in (g, d):
        layer.polygon(head, fill=col)
    glow = glow.filter(ImageFilter.GaussianBlur(28))
    im = Image.blend(im, Image.composite(glow, im, glow.convert("L")), 1.0)
    from PIL import ImageChops
    im = ImageChops.add(im, glow, scale=1.4)
    return im


def make_cover(headline, label, mood, path):
    """Layout of a news card: art on top, dark fade, coloured tag, big two-colour headline, channel name."""
    from PIL import Image, ImageDraw
    col = COVER_UP if mood == "positive" else COVER_DOWN if mood == "negative" else COVER_BLUE
    im = cover_background(mood, seed=len(headline) * 7 + FILE_NO)
    shade = Image.new("L", (1080, 1920), 0)                # fade to black over the lower part
    sd = ImageDraw.Draw(shade)
    for y in range(1920):
        sd.line([(0, y), (1080, y)], fill=int(255 * min(1, max(0, (y - 900) / 520)) ** 1.2))
    im = Image.composite(Image.new("RGB", im.size, (0, 0, 0)), im, shade)
    d = ImageDraw.Draw(im)
    d.text((60, 70), CHANNEL, font=font(34), fill=(220, 225, 235))          # small top-left brand
    # headline: [r]...[/r] part in the mood colour, rest white; auto-size to fit 4 lines
    parts = re.split(r"(\[r\].*?\[/r\])", caps(headline))
    words = []
    for p in parts:
        hot = p.startswith("[r]")
        words += [(w, hot) for w in plain(p).split()]
    if not any(h for _, h in words):                       # nothing marked: colour the first half
        words = [(w, k < max(1, len(words) // 2)) for k, (w, _) in enumerate(words)]
    for size in (104, 96, 88, 80, 72):
        hf = cond_font(size)
        lines, cur = [], []
        for w in words:
            if cur and d.textlength(" ".join(x for x, _ in cur + [w]), font=hf) > 960:
                lines.append(cur)
                cur = []
            cur.append(w)
        lines.append(cur)
        if len(lines) <= 4:
            break
    line_h = int(size * 1.12)
    y0 = 1790 - len(lines) * line_h - 110                  # block ends just above the disclaimer
    # tag: icon box + coloured label
    tf = cond_font(52)
    tw = d.textlength(label, font=tf)
    d.rectangle([60, y0, 132, y0 + 72], outline=col, width=4)
    for k, hgt in enumerate((18, 32, 46)):
        d.rectangle([74 + k * 18, y0 + 58 - hgt, 86 + k * 18, y0 + 58], fill=col)
    d.rectangle([150, y0, 150 + tw + 44, y0 + 72], fill=col)
    d.text((172, y0 + 6), label, font=tf, fill=(255, 255, 255))
    y = y0 + 100
    for line in lines:
        x = 60
        for w, hot in line:
            d.text((x, y), w, font=hf, fill=col if hot else (255, 255, 255))
            x += d.textlength(w + " ", font=hf)
        y += line_h
    d.text((60, 1840), "NOT FINANCIAL ADVICE", font=font(26, False), fill=(120, 125, 135))
    im.save(path)


TAGS = {"movers": "MARKET MOVERS", "news": "STOCK MARKET", "pe": "VALUE STOCKS",
        "month": "ANALYSTS' PICKS", "y2030": "GROWTH STOCKS"}


# ---- Timing, shots, captions ---------------------------------------------------
def line_times(data, words, total):
    body = [l for l in data["lines"] if plain(l)]
    counts = [len(plain(l).split()) for l in body]
    c = head = len(plain(data["headline"]).split())
    starts = []
    for k in counts:
        if words and len(words) > head + 3:
            starts.append(words[min(c, len(words) - 1)][1])
        else:
            starts.append(0.4 + (total - 0.6) * c / (head + sum(counts)))
        c += k
    return list(zip(body, starts, starts[1:] + [total]))


def build_slides(d0, timed, total):
    """Title while the hook is spoken, one card per item line, the comparison board on the last line."""
    paths = [(W / "s_cover.png").resolve()]
    make_cover(HEADLINE, TAGS.get(CATEGORY, "STOCK MARKET"), d0.get("mood", "neutral"), paths[0])
    n = len(d0["items"])
    for i, it in enumerate(d0["items"], 1):
        paths.append((W / f"s_{i}.png").resolve())
        slide_card(it, i, n, paths[-1])
    last = paths[-1]
    if d0.get("board") and all(it.get("bar") is not None for it in d0["items"]):
        last = (W / "s_board.png").resolve()
        slide_board(d0, last)
    starts = [0.0] + [s for _, s, _ in timed]
    shots = []
    for k in range(len(starts)):
        end = starts[k + 1] if k + 1 < len(starts) else total
        img = paths[k] if k < len(paths) else last
        if k == len(starts) - 1:
            img = last
        shots.append({"kind": "cover" if k == 0 else "single", "imgs": [img], "dur": max(0.4, end - starts[k])})
    return shots


def render_shot(i, sh):
    fr = int(sh["dur"] * 30) + 2
    if sh["kind"] == "cover":                            # full frame, slow push-in
        ff("-loop", "1", "-framerate", "30", "-i", str(sh["imgs"][0]), "-filter_complex",
           f"[0:v]scale=2160:3840,zoompan=z='1+0.04*on/{fr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={fr}:"
           "s=1080x1920:fps=30,setsar=1,format=yuv420p[v]", "-map", "[v]", "-t", f"{sh['dur']:.3f}", *x264(20),
           f"shot{i}.mp4")
        return f"shot{i}.mp4"
    z = f"1+0.05*on/{fr}" if i % 2 == 0 else f"1.05-0.05*on/{fr}"
    ff("-loop", "1", "-framerate", "30", "-i", str(sh["imgs"][0]), "-filter_complex",
       f"[0:v]scale=2160:{MID_H * 2},zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={fr}:"
       f"s=1080x{MID_H}:fps=30,setsar=1,format=yuv420p,pad=1080:1920:0:{TOP_BAR}:0x{BG[0]:02X}{BG[1]:02X}{BG[2]:02X}[v]",
       "-map", "[v]", "-t", f"{sh['dur']:.3f}", *x264(20), f"shot{i}.mp4")
    return f"shot{i}.mp4"


def build_background(shots):
    parts = [render_shot(i, s) for i, s in enumerate(shots)]
    (W / "bg.txt").write_text("\n".join(f"file '{p}'" for p in parts), encoding="utf-8")
    ff("-f", "concat", "-safe", "0", "-i", "bg.txt", "-c", "copy", "bg.mp4")


def build_ass(data, timed, total):
    fam = font_family()
    style = lambda name, size, col, sp, out, sh, al, ml, mr, mv: (
        f"Style: {name},{fam},{size},{col},{col},&H00000000&,&H00000000&,-1,0,0,0,100,100,{sp},0,1,{out},{sh},"
        f"{al},{ml},{mr},{mv},1")
    ev = lambda layer, s, e, st, txt: f"Dialogue: {layer},{ass_time(s)},{ass_time(e)},{st},,0,0,0,,{txt}"
    lines = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "WrapStyle: 0",
             "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
             "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
             "Alignment, MarginL, MarginR, MarginV, Encoding",
             style("Label", 40, ACC_ASS, 6, 0, 0, 8, 60, 60, 125),
             style("Head", 76, WHITE, 1, 0, 0, 8, 60, 60, 185),
             style("Body", 58, WHITE, 0, 0, 0, 8, 170, 170, BOT_Y + 35),
             style("Brand", 30, bgr(THEME["ink"], "50"), 4, 3 if sum(BG) < 200 else 0, 0, 9, 0, 28, TOP_BAR + 18),
             "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
             ev(0, COVER_END, total, "Label", f"{LABEL}  ·  #{FILE_NO}"),
             *top_events(data, timed, total, ev),
             ev(3, COVER_END, total, "Brand", CHANNEL)]
    lines += [ev(1, s, e, "Body", "{\\fad(120,60)}" + to_ass(text)) for text, s, e in timed]
    path = W / "subs.ass"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


DAY_WORD = "GAINERS"
TOPBAR = env("TOPBAR", "chapter")                       # chapter | market: what sits above slides 2-3
D0 = {}


def chapters(d0):
    """Two-line title per narration line (blue line + white line, same look as before): what THIS slide is."""
    items, out, g, l = d0["items"], [], 0, 0
    for i, it in enumerate(items, 1):
        if CATEGORY == "movers":
            out.append((DAY_WORD, "OF THE DAY"))
        else:
            out.append({"news": (f"STORY {i}", f"OF {len(items)}"), "pe": (f"CHEAPEST #{i}", "BY P/E RATIO"),
                        "month": (f"ANALYSTS' PICK #{i}", "THIS MONTH"),
                        "y2030": (f"FASTEST GROWER #{i}", "OVER 5 YEARS")}.get(CATEGORY, (f"#{i}", "")))
    out.append({"movers": ("TECH", "SCOREBOARD"), "news": ("WHAT IT", "MEANS")}.get(CATEGORY, ("THE FULL", "RANKING")))
    return out


def market_strip():
    """Index ETFs as a market bar: SPY (S&P 500) and QQQ (Nasdaq 100)."""
    parts = [f"{t} {pct(q['dp'])}" for t in ("SPY", "QQQ") if (q := quote(t))]
    return "   ".join(parts)


def top_events(data, timed, total, ev):
    """Text above slides 2-3 (instead of repeating the cover headline), in the same two-line style."""
    two = lambda a, b: "{\\fad(150,0)}" + to_ass(f"[r]{a}[/r]") + ("\\N" + to_ass(b) if b else "")
    if TOPBAR == "market":
        strip = market_strip()
        if strip:
            return [ev(0, COVER_END, total, "Head", two("MARKET TODAY", strip))]
    titles = chapters(D0) if D0 else []
    return [ev(0, s, e, "Head", two(*titles[k]) if k < len(titles) else "")
            for k, (_, s, e) in enumerate(timed)]


def make_video(data, d0):
    global MUSIC, D0
    D0 = d0
    mood = d0.get("mood", "neutral")                     # P/E, analysts, 2030 = neutral facts
    global MUSIC_START
    MUSIC = mood_track(mood) or MUSIC
    if MUSIC.exists() and not env("MUSIC_START"):
        MUSIC_START = round(random.uniform(0, max(0.0, probe_duration(MUSIC) - MAX_SEC - 5) * 0.6), 1)
    print("mood:", mood, "| music:", MUSIC if MUSIC.exists() else "none")
    words = []
    spoken = plain(data["headline"]) + ". " + " ".join(plain(l) for l in data["lines"])
    total = min(MAX_SEC, max(MIN_SEC, 1 + len(spoken.split()) * 0.38))
    if NARRATION:
        words = tighten(W / "voice.mp3", asyncio.run(_tts(spoken, W / "voice.mp3")))
        total = min(MAX_SEC, max(MIN_SEC, probe_duration(W / "voice.mp3") + 0.3))
    timed = line_times(data, words, total)
    global HEADLINE, COVER_END
    HEADLINE, COVER_END = data["headline"], timed[0][1] if timed else 2.5
    shots = build_slides(d0, timed, total)
    build_background(shots)
    if SFX:
        cuts = [sum(s["dur"] for s in shots[:k + 1]) for k in range(len(shots) - 1)]
        build_sfx(total, timed, cuts, shots, W / "sfx.wav")
    render(build_ass(data, timed, total), total)


def upload(yt, data, d0):
    from googleapiclient.http import MediaFileUpload
    title, q = plain(data["title"]), plain(data.get("question", ""))
    syms = [it["ticker"] for it in d0["items"] if re.fullmatch(r"[A-Z.]{1,6}", it["ticker"])]
    tags = list(dict.fromkeys(["stocks", "stock market", "investing"] + CAT_TAGS + syms + data.get("tags", [])))
    story = plain(data["headline"]) + "\n" + "\n".join(plain(l) for l in data["lines"])
    tail = ("\n\n#Shorts #stocks #investing " + " ".join("#" + s for s in syms[:4]) + "\n\n" + DISCLAIMER)
    body = {"snippet": {"title": f"{title[:85]} #Shorts", "tags": tags[:15], "categoryId": "27",
                        "description": ((f"{q} Tell me in the comments!\n\n" if q else "") + story + tail)[:4900],
                        "defaultLanguage": "en", "defaultAudioLanguage": "en"},
            "status": {"privacyStatus": env("PRIVACY", "public"), "selfDeclaredMadeForKids": False}}
    loc = {l: {"title": f"{plain(t['title'])[:85]} #Shorts",
               "description": ((t["question"] + "\n\n" if t.get("question") else "") + t.get("story", "") + tail)[:4900]}
           for l, t in translate(title, q, story).items()}
    if loc:
        body["localizations"] = loc
    send = lambda part: yt.videos().insert(part=part, body=body, media_body=MediaFileUpload(
        str(W / "final.mp4"), chunksize=-1, resumable=True)).execute()["id"]
    try:
        vid = send("snippet,status" + (",localizations" if loc else ""))
    except Exception as e:
        if not loc or "uploadLimitExceeded" in str(e) or "quota" in str(e).lower():
            raise
        body.pop("localizations")
        vid = send("snippet,status")
    print("uploaded:", vid)
    return vid


if __name__ == "__main__":
    d0 = get_data()
    print("category:", CATEGORY, "| key:", d0["key"])
    data = gen_script(d0)
    print(json.dumps(data, ensure_ascii=False))
    make_video(data, d0)
    yt = youtube()
    vid = upload(yt, data, d0)
    used.append(d0["key"])
    USED.write_text(json.dumps(used, ensure_ascii=False, indent=1), encoding="utf-8")
    add_to_playlist(yt, vid)
    post_comment(yt, vid, data)
