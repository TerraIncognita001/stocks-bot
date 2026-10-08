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
SECTORS = ["All", "Tech", "Finance", "Healthcare", "Consumer", "Energy & Industry"]

# ---- Categories: label, accent, playlist, how to tell it, tags ----------------------------------------
CATEGORIES = {
    "movers": ("BIGGEST MOVERS TODAY", "0x3B82F6", "Biggest Movers",
               "Today's biggest winners and losers among big US stocks, with the reason from the news.",
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
WHITE, RED, YELLOW = "&H00FFFFFF&", "&H00F6823B&", "&H00FDC593&"   # ASS colours (BGR): blue, light blue
GREEN_ASS, RED_ASS = "&H005EC522&", "&H004444EF&"                  # growth up / down
SIGNED = re.compile(r"(?<![\w.])([+\-−])\$?\d[\d,]*\.?\d*%?(?:/yr)?")
ACC_ASS = f"&H00{ACCENT[6:8]}{ACCENT[4:6]}{ACCENT[2:4]}&"
ACC_RGB = tuple(int(ACCENT[k:k + 2], 16) for k in (2, 4, 6))
FONT = pathlib.Path("font.ttf")
FONTS_DIR = str(FONT.resolve().parent) if FONT.exists() else "/usr/share/fonts/truetype/dejavu"
UP, DOWN, INK, BG, MUTED = (34, 197, 94), (239, 68, 68), (255, 255, 255), (0, 0, 0), (115, 115, 115)
LINE = (38, 38, 38)                                     # hairlines


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


def to_ass(t):
    t = str(t).replace("\\", "").replace("{", "").replace("}", "").replace("\n", " ")
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
    fc = [f"[0:v]drawbox=x=0:y={TOP_BAR - 2}:w=1080:h=2:color={ACCENT}@1:t=fill,drawbox=x=0:y={BOT_Y}:w=1080:"
          f"h=2:color={ACCENT}@1:t=fill,ass={ass_path.resolve()}:fontsdir={FONTS_DIR}[v]"]
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


def tickers(sector):
    return [t for t, (_, s) in UNIVERSE.items() if sector == "All" or s == sector]


def pct(x):
    return f"{x:+.1f}%"


def money(x):
    return f"${x:,.2f}"


def quote(t):
    q = fh("quote", symbol=t) or {}
    return q if q.get("c") and q.get("dp") is not None else None


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
    pick = ranked[::-1][:2] + ranked[:2]                                  # 2 winners, 2 losers
    items = []
    for t in pick:
        news = fh("company-news", symbol=t, **{"from": str(US_DATE - dt.timedelta(days=2)), "to": str(US_DATE)}) or []
        heads = [n.get("headline", "") for n in news[:4] if n.get("headline")]
        q = qs[t]
        items.append({"ticker": t, "name": UNIVERSE[t][0], "main": money(q["c"]),
                      "badge": (pct(q["dp"]), UP if q["dp"] >= 0 else DOWN),
                      "rows": [("Day range", f"{money(q['l'])} - {money(q['h'])}"), ("Previous close", money(q["pc"]))],
                      "bar": q["dp"], "bar_txt": pct(q["dp"]),
                      "fact": f"{t} ({UNIVERSE[t][0]}): closed at {money(q['c'])}, {pct(q['dp'])} today. "
                              f"News headlines: {' | '.join(heads) or 'none'}"})
    avg = sum(q["dp"] for q in qs.values()) / len(qs)                    # the whole basket, not just the 4
    mood = "positive" if avg >= 0.4 else "negative" if avg <= -0.4 else "neutral"
    return {"items": items, "key": f"movers {US_DATE}", "sub": US_DATE.strftime("%b %d, %Y"),
            "board": "Today's change", "mood": mood}


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
                              + "; ".join(f"{k} {v}" for k, v in rows)})
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
                              f"({r.get('strongBuy', 0)} Strong Buy); next earnings: {when}"})
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
                                "(hypothetical, not a forecast)"})
    return {"items": items, "key": f"y2030 {sector} {US_DATE:%Y-%m}", "sub": f"Sector: {sector}",
            "board": "Revenue growth per year (5 yrs)"}


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
    facts = "\n".join(f"ITEM {i + 1}: {it['fact']}" for i, it in enumerate(d["items"]))
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
        f"- lines: exactly {n + 1} narration lines, max 12 words each. Line k (1..{n}) is about ITEM k, in order: "
        "name the company, its key number, and the reason or meaning from the facts. "
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
    for _ in range(3):
        data = gemini(prompt, ok)
        if numbers_ok([data["headline"]] + data["lines"], facts):
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


def slide_card(it, i, n, path):
    im, d = canvas()
    d.text((145, 36), f"{i}/{n}", font=font(30, False), fill=MUTED)       # next to the blue rule
    d.text((70, 120), it["ticker"], font=font(120), fill=INK)
    y = 270
    for line in wrap(d, it["name"], font(48, False), 920)[:2]:
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
        d.text((74, y + 10), k, font=font(36, False), fill=MUTED)
        d.text((1010 - d.textlength(v, font=font(40)), y + 6), v, font=font(40), fill=tone(v))
        d.line([(74, y + 62), (1010, y + 62)], fill=LINE, width=2)
        y += 72
    im.save(path)


def slide_board(d0, path):
    im, d = canvas()
    d.text((70, 90), d0["board"], font=font(44), fill=INK)
    items = d0["items"]
    vmax = max(abs(it["bar"]) for it in items) or 1
    neg = any(it["bar"] < 0 for it in items)
    x_zero = 540 if neg else 270
    span = 1010 - x_zero - 160                          # room for the value label
    for k, it in enumerate(items):
        y = 190 + k * 140
        col = (UP if it["bar"] >= 0 else DOWN) if CATEGORY in ("movers", "y2030") else ACC_RGB
        w = int(span * abs(it["bar"]) / vmax)
        x1, x2 = (x_zero, x_zero + w) if it["bar"] >= 0 else (x_zero - w, x_zero)
        d.rectangle([x1, y + 25, max(x2, x1 + 4), y + 65], fill=col)
        d.text((70 if not neg or it["bar"] >= 0 else x_zero + 20, y + 18), it["ticker"], font=font(48), fill=INK)
        tx = x2 + 20 if it["bar"] >= 0 else x1 - 20 - d.textlength(it["bar_txt"], font=font(44))
        d.text((tx, y + 22), it["bar_txt"], font=font(44), fill=tone(it["bar_txt"]))
    im.save(path)


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
    paths = [(W / "s_title.png").resolve()]
    slide_title(d0, paths[0])
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
        shots.append({"kind": "single", "imgs": [img], "dur": max(0.4, end - starts[k])})
    return shots


def render_shot(i, sh):
    fr = int(sh["dur"] * 30) + 2
    z = f"1+0.05*on/{fr}" if i % 2 == 0 else f"1.05-0.05*on/{fr}"
    ff("-loop", "1", "-framerate", "30", "-i", str(sh["imgs"][0]), "-filter_complex",
       f"[0:v]scale=2160:{MID_H * 2},zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={fr}:"
       f"s=1080x{MID_H}:fps=30,setsar=1,format=yuv420p,pad=1080:1920:0:{TOP_BAR}:black[v]",
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
             style("Brand", 30, "&H50FFFFFF&", 4, 3, 0, 9, 0, 28, TOP_BAR + 18),
             "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
             ev(0, 0, total, "Label", f"{LABEL}  ·  #{FILE_NO}"),
             ev(0, 0, total, "Head", "{\\fad(200,0)}" + to_ass(data["headline"])),
             ev(3, 0, total, "Brand", CHANNEL)]
    lines += [ev(1, s, e, "Body", "{\\fad(120,60)}" + to_ass(text)) for text, s, e in timed]
    path = W / "subs.ass"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def make_video(data, d0):
    global MUSIC
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
