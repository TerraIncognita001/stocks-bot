#!/usr/bin/env python3
"""Bull & Bear Daily v2 - data-story YouTube Shorts about famous stocks.

Series
  time_machine  "$1,000 in <company>, N years ago"  - growth chart + live counter, reveal at the end
  peak          "$1,000 at <company>'s very top"    - the same engine, a loss story
  battle        "$1,000 in A vs $1,000 in B"        - two lines race, winner at the end
  shock         "<company> just lost $X billion"    - today's biggest market-cap move, in dollars

Every number on screen and in the voice-over is computed from price data; the LLM only words it
and its text is checked. Frames are drawn with Pillow and piped straight into ffmpeg.
"""
import asyncio
import datetime as dt
import functools
import json
import math
import os
import pathlib
import random
import re
import socket
import subprocess
import time
import wave
from collections import Counter

import numpy as np
import requests
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

env = os.getenv
socket.setdefaulttimeout(60)                  # no network call may hang the run
START = time.time()
GHA = env("GITHUB_ACTIONS") == "true"
WORK = pathlib.Path(env("WORK_DIR", "work"))
WORK.mkdir(parents=True, exist_ok=True)
DATA = pathlib.Path("data")
PRICE_DIR, LOGO_DIR = DATA / "prices", WORK / "logos"
PROFILE_FILE = DATA / "profiles.json"
STATE_FILE = pathlib.Path(env("STATE_FILE", "used.json"))
FONT_DIR = pathlib.Path("fonts")
MUSIC_DIR = pathlib.Path("music")

DRY = env("DRY_RUN", "0") == "1"
LEARN = env("LEARN", "1") == "1"
FPS = int(env("FPS", "30"))
CHANNEL = env("CHANNEL", "BULL & BEAR DAILY")
VOICE = env("VOICE", "en-US-AndrewNeural")
RATE = env("RATE", "+10%")
MUSIC_VOL = float(env("MUSIC_VOL", "0.10"))
SFX_ON = env("SFX", "1") == "1"
SFX_VOL = float(env("SFX_VOL", "1.0"))
LANGS = [x.strip() for x in env("LANGS", "es,pt,de,fr,it,pl,uk,tr").split(",") if x.strip()]
NOW = dt.datetime.now(dt.timezone.utc)
TODAY = NOW.strftime("%Y-%m-%d")
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"}
US_POP = 340e6
SR = 44100
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
LONG_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
               "October", "November", "December"]

# ---- Companies: ticker -> (name, tier 1-3 = how famous, IPO year or None, sector, extra comment aliases) ----
COMPANIES = {
    "AAPL": ("Apple", 1, None, "tech", []), "MSFT": ("Microsoft", 1, None, "tech", []),
    "NVDA": ("Nvidia", 1, 1999, "chips", []), "AMZN": ("Amazon", 1, 1997, "retail", []),
    "GOOGL": ("Google", 1, 2004, "tech", ["alphabet"]), "META": ("Meta", 1, 2012, "tech", ["facebook"]),
    "TSLA": ("Tesla", 1, 2010, "auto", []), "NFLX": ("Netflix", 1, 2002, "media", []),
    "COST": ("Costco", 1, None, "retail", []), "MCD": ("McDonald's", 1, None, "food", ["mcdonalds"]),
    "KO": ("Coca-Cola", 1, None, "food", ["coke", "coca cola"]), "PEP": ("PepsiCo", 2, None, "food", ["pepsi"]),
    "NKE": ("Nike", 1, None, "retail", []), "DIS": ("Disney", 1, None, "media", []),
    "SBUX": ("Starbucks", 1, 1992, "food", []), "WMT": ("Walmart", 1, None, "retail", []),
    "HD": ("Home Depot", 2, None, "retail", []), "LOW": ("Lowe's", 3, None, "retail", ["lowes"]),
    "V": ("Visa", 2, 2008, "finance", []), "MA": ("Mastercard", 2, 2006, "finance", []),
    "JPM": ("JPMorgan", 2, None, "finance", ["jp morgan"]), "BAC": ("Bank of America", 3, None, "finance", []),
    "BRK-B": ("Berkshire Hathaway", 2, None, "finance", ["berkshire"]),
    "AMD": ("AMD", 1, None, "chips", []), "INTC": ("Intel", 1, None, "chips", []),
    "ORCL": ("Oracle", 2, None, "tech", []), "ADBE": ("Adobe", 2, None, "tech", []),
    "CRM": ("Salesforce", 2, 2004, "tech", []), "PYPL": ("PayPal", 2, None, "finance", []),
    "UBER": ("Uber", 1, 2019, "tech", []), "LYFT": ("Lyft", 3, 2019, "tech", []),
    "ABNB": ("Airbnb", 2, 2020, "tech", []), "SHOP": ("Shopify", 2, 2015, "tech", []),
    "SPOT": ("Spotify", 2, 2018, "media", []), "PLTR": ("Palantir", 1, 2020, "tech", []),
    "COIN": ("Coinbase", 2, 2021, "finance", []), "HOOD": ("Robinhood", 2, 2021, "finance", []),
    "RBLX": ("Roblox", 2, 2021, "media", []), "SNAP": ("Snap", 2, 2017, "tech", ["snapchat"]),
    "PTON": ("Peloton", 2, 2019, "retail", []), "ZM": ("Zoom", 2, 2019, "tech", []),
    "GME": ("GameStop", 1, None, "retail", ["gamestop"]), "AMC": ("AMC", 2, None, "media", []),
    "BA": ("Boeing", 2, None, "industrial", []), "F": ("Ford", 2, None, "auto", []),
    "GM": ("General Motors", 3, 2010, "auto", []), "LULU": ("Lululemon", 2, 2007, "retail", []),
    "CMG": ("Chipotle", 2, 2006, "food", []), "TGT": ("Target", 3, None, "retail", []),
    "PG": ("Procter & Gamble", 3, None, "food", []), "JNJ": ("Johnson & Johnson", 3, None, "health", []),
    "PFE": ("Pfizer", 2, None, "health", []), "MRNA": ("Moderna", 2, 2018, "health", []),
    "LLY": ("Eli Lilly", 2, None, "health", ["lilly"]), "XOM": ("ExxonMobil", 3, None, "energy", ["exxon"]),
    "CVX": ("Chevron", 3, None, "energy", []), "CAT": ("Caterpillar", 3, None, "industrial", []),
    "IBM": ("IBM", 2, None, "tech", []), "CSCO": ("Cisco", 3, None, "tech", []),
    "QCOM": ("Qualcomm", 3, None, "chips", []), "AVGO": ("Broadcom", 2, 2009, "chips", []),
    "MU": ("Micron", 3, None, "chips", []), "TSM": ("TSMC", 2, None, "chips", []),
    "SONY": ("Sony", 2, None, "media", []), "BABA": ("Alibaba", 2, 2014, "retail", []),
    "RIVN": ("Rivian", 2, 2021, "auto", []), "LCID": ("Lucid", 3, None, "auto", []),
    "SMCI": ("Super Micro", 3, None, "chips", ["supermicro"]), "DUOL": ("Duolingo", 2, 2021, "tech", []),
    "SPY": ("the S&P 500", 2, None, "index", ["s&p 500", "s&p", "sp500"]),
    "QQQ": ("the Nasdaq 100", 3, None, "index", ["nasdaq"]),
}
ETFS = {"SPY", "QQQ"}
PEAK_POOL = ["PTON", "ZM", "SNAP", "PYPL", "INTC", "NKE", "BA", "MRNA", "BABA", "RIVN", "LCID", "AMC", "DIS",
             "LULU", "SBUX", "PFE", "TGT", "COIN", "RBLX", "ABNB", "DUOL", "SMCI", "GME", "F", "MU", "ADBE"]
BATTLES = [("AAPL", "MSFT"), ("KO", "PEP"), ("NVDA", "AMD"), ("AMD", "INTC"), ("TSLA", "F"), ("NFLX", "DIS"),
           ("V", "MA"), ("HD", "LOW"), ("COST", "WMT"), ("UBER", "LYFT"), ("META", "SNAP"), ("GOOGL", "MSFT"),
           ("AMZN", "WMT"), ("SBUX", "MCD"), ("XOM", "CVX"), ("JPM", "BAC"), ("NKE", "LULU"), ("MCD", "CMG"),
           ("AAPL", "GOOGL"), ("ORCL", "CRM"), ("TSM", "INTC"), ("LLY", "PFE"), ("SPY", "TSLA"), ("SPY", "AAPL"),
           ("NVDA", "TSLA"), ("AMZN", "GOOGL"), ("META", "NFLX"), ("COST", "TGT"), ("PLTR", "NVDA"),
           ("SPY", "QQQ"), ("AVGO", "QCOM"), ("MU", "INTC"), ("COIN", "HOOD"), ("DIS", "SONY")]
SERIES_INFO = {   # label on screen, playlist, base weight
    "time_machine": ("TIME MACHINE", "Time Machine: $1,000 Then vs Now", 0.55),
    "peak": ("BOUGHT THE TOP", "Bought the Top", 0.15),
    "battle": ("STOCK BATTLE", "Stock Battles: $1,000 Each", 0.30),
    "shock": ("MARKET SHOCK", "Market Shock", 0.0),
}
HOOKS = ["you", "question", "imagine", "number"]

# ---- Look ---------------------------------------------------------------------------------------------
WD, HT = 1080, 1920
BG1, BG2, GRID = (11, 22, 46), (3, 6, 15), (24, 42, 76)
WHITE, MUTED, DIM = (255, 255, 255), (150, 163, 186), (92, 106, 132)
GREEN, RED, GOLD = (57, 232, 20), (255, 59, 59), (255, 201, 40)
BLUE, CYAN, ORANGE, SPY_C = (59, 130, 246), (34, 211, 238), (251, 146, 60), (128, 140, 165)
CARD = (15, 28, 56)
BRAND_Y, HEAD_Y, ROW_Y, COUNTER_Y, CHIP_Y = 172, 220, 478, 507, 742
CX0, CY0, CX1, CY1 = 70, 850, 900, 1262        # chart box (right edge stays left of the Shorts buttons)
CAP_Y = 1380                                   # captions centre (above the title / channel-name overlay)
CAP_X, CAP_W = 520, 800                        # captions centre x and max width (clear of the buttons)


# =========================================================================================================
# small helpers
# =========================================================================================================
def gh_note(level, title, msg):
    """notice / warning / error: shown on the GitHub Actions run page (Annotations)."""
    msg = re.sub(r"\s+", " ", str(msg))[:900]
    print(f"::{level} title={title}::{msg}" if GHA else f"[{level}] {title}: {msg}", flush=True)


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def load_json(path, default):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, obj):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def days_since(date_str):
    try:
        return (NOW.date() - dt.date.fromisoformat(date_str[:10])).days
    except Exception:
        return 9999


def safe(sym):
    return re.sub(r"[^A-Za-z0-9_-]", "_", sym)


def month_label(ym, long=False):
    y, m = ym.split("-")[:2]
    return f"{(LONG_MONTHS if long else MONTHS)[int(m) - 1]} {y}"


def add_months(ym, k):
    y, m = int(ym[:4]), int(ym[5:7]) - 1 + k
    return f"{y + m // 12:04d}-{m % 12 + 1:02d}"


def money(v):
    return ("-" if v < 0 else "") + f"${abs(v):,.0f}"


def money2(v):
    return f"${v:,.2f}"


def short_money(v):
    a, s = abs(v), "-" if v < 0 else ""
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            x = a / div
            txt = f"{x:.0f}" if x >= 100 else f"{x:.1f}" if x >= 10 else f"{x:.2f}"
            if "." in txt:
                txt = txt.rstrip("0").rstrip(".")
            return f"{s}${txt}{suf}"
    return f"{s}${a:,.0f}"


def say_money(v):
    """Rounded money for the voice: about $287,000 / $1.24 million / $210 billion."""
    a = abs(v)
    if a >= 1e12:
        return f"${f'{a / 1e12:.1f}'.rstrip('0').rstrip('.')} trillion"
    if a >= 1e9:
        x = f"{a / 1e9:.0f}" if a >= 1e10 else f"{a / 1e9:.1f}".rstrip("0").rstrip(".")
        return f"${x} billion"
    if a >= 1e6:
        return f"${f'{a / 1e6:.2f}'.rstrip('0').rstrip('.')} million"
    if a >= 1e5:
        return f"${round(a, -3):,.0f}"
    if a >= 1e3:
        return f"${round(a, -2):,.0f}"
    return f"${round(a):,.0f}"


def times_words(m):
    return f"{m:.0f} times" if m >= 10 else f"{m:.1f} times".replace(".0 ", " ")


def mult_chip(m):
    if m < 1:
        return f"–{(1 - m) * 100:.0f}%"
    return f"{m:,.0f}X" if m >= 10 else f"{m:.1f}X"


NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers_in(text):
    out = []
    for x in NUM.findall(str(text)):
        try:
            out.append(float(x.replace(",", "")))
        except ValueError:
            pass
    return out


def collect_numbers(obj, out=None):
    out = [] if out is None else out
    if isinstance(obj, dict):
        for v in obj.values():
            collect_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            collect_numbers(v, out)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        out.append(float(obj))
    elif isinstance(obj, str):
        out += numbers_in(obj)
    return out


INDEX_NAMES = re.compile(r"S&P\s*500|Nasdaq[- ]?100", re.I)


def numbers_ok(text, allowed):
    """Every number must be (close to) one of the facts; years and small counts are always fine."""
    for x in numbers_in(INDEX_NAMES.sub("", str(text))):
        if x <= 12 or (1980 <= x <= 2040 and x == int(x)):
            continue
        if any(abs(x - a) <= 0.016 * max(abs(a), 1.0) for a in allowed):
            continue
        return False, x
    return True, None


# =========================================================================================================
# state
# =========================================================================================================
def load_state():
    s = load_json(STATE_FILE, {})
    if isinstance(s, list):                     # v1 kept a plain list of keys
        s = {"legacy": s}
    s.setdefault("version", 2)
    s.setdefault("videos", [])
    s.setdefault("requests_done", {})
    return s


STATE = load_state()


def save_state():
    save_json(STATE_FILE, STATE)


def recent(field, n):
    return [v.get(field) for v in STATE["videos"][-n:]]


# =========================================================================================================
# network: Finnhub, prices, logos
# =========================================================================================================
def http_get(url, params=None, headers=None, timeout=20, tries=2):
    r = None
    for k in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA if headers is None else headers, timeout=timeout)
            if r.status_code == 429 and k + 1 < tries:
                time.sleep(3 * (k + 1))
                continue
            return r
        except requests.RequestException as e:
            print("net:", url.split("?")[0], type(e).__name__)
            r = None
            time.sleep(1 + 2 * k)
    return r


def fh_symbol(sym):
    return sym.replace("-", ".")


FH_FAILS = Counter()


def fh(path, **params):
    key = env("FINNHUB_API_KEY")
    if not key or FH_FAILS["net"] >= 4:               # Finnhub down: stop asking for this run
        return None
    for _ in range(2):
        r = http_get(f"https://finnhub.io/api/v1/{path}", {**params, "token": key}, headers={}, tries=1, timeout=15)
        time.sleep(1.05)                              # free tier: 60 calls / minute
        if r is None or r.status_code >= 500:
            FH_FAILS["net"] += 1
            continue
        FH_FAILS["net"] = 0
        if r.status_code == 429:
            time.sleep(10)
            continue
        if r.status_code in (401, 403):
            print("finnhub", path, r.status_code, "(not on this plan / bad key)")
            return None
        try:
            return r.json()
        except ValueError:
            return None
    return None


QUOTES = {}


def quote(sym):
    if sym not in QUOTES:
        q = fh("quote", symbol=fh_symbol(sym)) or {}
        QUOTES[sym] = q if q.get("c") and q.get("pc") else None
    return QUOTES[sym]


def profile(sym):
    cache = load_json(PROFILE_FILE, {})
    p = cache.get(sym)
    if p and days_since(p.get("fetched", "")) < 7:
        return p
    if sym in ETFS:
        return p or {}
    d = fh("stock/profile2", symbol=fh_symbol(sym)) or {}
    if d.get("name"):
        p = {"name": d["name"], "shares": d.get("shareOutstanding"), "logo": d.get("logo"),
             "mcap": d.get("marketCapitalization"), "fetched": TODAY}
        cache[sym] = p
        save_json(PROFILE_FILE, cache)
    return p or {}


def logo_image(sym):
    """Company logo as provided by the data feed (Finnhub profile), cached in data/logos."""
    path = LOGO_DIR / f"{safe(sym)}.png"
    if path.exists():
        try:
            return Image.open(path).convert("RGBA")
        except Exception:
            pass
    url = profile(sym).get("logo")
    if not url:
        return None
    r = http_get(url, tries=2)
    if r is None or r.status_code != 200:
        return None
    try:
        from io import BytesIO
        im = Image.open(BytesIO(r.content)).convert("RGBA")
        im.thumbnail((256, 256), Image.LANCZOS)
        LOGO_DIR.mkdir(parents=True, exist_ok=True)
        im.save(path)
        return im
    except Exception as e:
        print("logo skipped:", sym, type(e).__name__)
        return None


def company_news(sym, days=2, k=4):
    d0 = (NOW - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    news = fh("company-news", symbol=fh_symbol(sym), **{"from": d0, "to": TODAY}) or []
    return [{"headline": n.get("headline", ""), "summary": str(n.get("summary", ""))[:280]}
            for n in news[:k] if n.get("headline")]


# ---- monthly price history (adjusted when the source supports it), cached in data/prices ----------------
class DataError(Exception):
    pass


def need_ok(r, what):
    if r is None:
        raise DataError(f"{what}: no answer (network/timeout)")
    if r.status_code != 200:
        raise DataError(f"{what}: HTTP {r.status_code} {r.text[:90]!r}")
    return r


def from_tiingo(sym):
    key = env("TIINGO_API_KEY")
    if not key:
        raise DataError("Tiingo: TIINGO_API_KEY secret is not set")
    r = need_ok(http_get(f"https://api.tiingo.com/tiingo/daily/{sym.lower()}/prices",
                         {"startDate": "1985-01-01", "resampleFreq": "monthly", "token": key},
                         headers={"Content-Type": "application/json"}), "Tiingo")
    rows = r.json()
    if not isinstance(rows, list):
        raise DataError(f"Tiingo: {str(rows)[:120]}")
    return [(row["date"][:7], float(row["adjClose"])) for row in rows if row.get("adjClose")], True


def from_yfinance(sym):
    try:
        import yfinance as yf
    except ImportError:
        raise DataError("yfinance: not installed")
    h = yf.Ticker(sym).history(period="max", interval="1mo", auto_adjust=True, actions=False, timeout=20)
    if h is None or h.empty:
        raise DataError("yfinance: empty answer (Yahoo blocked?)")
    return [(i.strftime("%Y-%m"), float(c)) for i, c in zip(h.index, h["Close"]) if c == c and c > 0], True


def from_alphavantage(sym):
    key = env("ALPHAVANTAGE_API_KEY")
    if not key:
        raise DataError("Alpha Vantage: ALPHAVANTAGE_API_KEY secret is not set")
    r = need_ok(http_get("https://www.alphavantage.co/query",
                         {"function": "TIME_SERIES_MONTHLY_ADJUSTED", "symbol": sym, "apikey": key}), "Alpha Vantage")
    data = r.json()
    js = data.get("Monthly Adjusted Time Series")
    if not js:
        raise DataError(f"Alpha Vantage: {str(data)[:120]}")
    return [(d[:7], float(v["5. adjusted close"])) for d, v in js.items()], True


def from_yahoo(sym):
    err = None
    for host in ("query2", "query1"):
        try:
            r = need_ok(http_get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}",
                                 {"range": "max", "interval": "1mo", "includeAdjustedClose": "true",
                                  "events": "div,split"}, tries=1), "Yahoo")
        except DataError as e:
            err = e
            continue
        res = r.json()["chart"]["result"][0]
        adj = res["indicators"]["adjclose"][0]["adjclose"]
        return [(dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m"), float(a))
                for t, a in zip(res["timestamp"], adj) if a], True
    raise err or DataError("Yahoo: no answer")


def from_stooq(sym):
    r = need_ok(http_get("https://stooq.com/q/d/l/", {"s": f"{sym.lower()}.us", "i": "m"}, tries=1), "Stooq")
    if not r.text.startswith("Date"):
        raise DataError(f"Stooq: not a CSV {r.text[:60]!r}")
    pts = []
    for line in r.text.strip().splitlines()[1:]:
        p = line.split(",")
        if len(p) >= 5 and p[4] not in ("", "null"):
            pts.append((p[0][:7], float(p[4])))
    return pts, False                                 # split-adjusted only


PROVIDERS = [("Tiingo", from_tiingo), ("yfinance", from_yfinance), ("Yahoo", from_yahoo),
             ("Alpha Vantage", from_alphavantage), ("Stooq", from_stooq)]
PRICE_FAIL, DEAD, PROVIDER_ERR, PROVIDER_OK = set(), Counter(), {}, Counter()


def price_history(sym, force=False):
    path = PRICE_DIR / f"{safe(sym)}.json"
    cached = load_json(path, None)
    if cached and days_since(cached.get("updated", "")) < 7 and not force:
        return cached
    if sym in PRICE_FAIL:
        return cached
    for name, fn in PROVIDERS:
        if DEAD[name] >= 3:                           # this source is down / not set up: skip for this run
            continue
        try:
            pts, div = fn(sym)
        except Exception as e:
            reason = str(e) if isinstance(e, DataError) else f"{name}: {type(e).__name__} {str(e)[:100]}"
            print("prices:", sym, "|", reason[:200])
            PROVIDER_ERR.setdefault(name, reason[:200])
            DEAD[name] += 3 if "is not set" in reason or "not installed" in reason else 1
            continue
        if not pts or len(pts) < 24:                  # too young a listing: no source will do better
            print(f"prices: {sym} has only {len(pts or [])} months")
            break
        DEAD[name] = 0
        PROVIDER_OK[name] += 1
        data = {"src": name.replace("yfinance", "Yahoo Finance"), "div": bool(div), "updated": TODAY,
                "points": sorted(dict(pts).items())}
        save_json(path, data)
        print(f"prices: {sym} from {name} ({len(data['points'])} months)")
        return data
    PRICE_FAIL.add(sym)
    if cached:
        print("prices: using older cache for", sym)
    return cached


def load_series(sym):
    """[(YYYY-MM, price)] oldest first; the last point is today's price when Finnhub answers."""
    data = price_history(sym)
    if not data or len(data.get("points", [])) < 24:
        return None
    pts = sorted({p[0][:7]: float(p[1]) for p in data["points"] if p[1]}.items())
    q = quote(sym)
    if q and not 0.6 <= q["c"] / pts[-1][1] <= 1.6:      # stale cache across a split? refetch once
        print(f"prices: {sym} live {q['c']} vs history {pts[-1][1]:.2f}, refreshing")
        fresh = price_history(sym, force=True)
        if fresh and len(fresh.get("points", [])) >= 24:
            data = fresh
            pts = sorted({p[0][:7]: float(p[1]) for p in data["points"] if p[1]}.items())
        if not 0.6 <= q["c"] / pts[-1][1] <= 1.6:
            print("prices: live price ignored for", sym)
            q = None
    ym = NOW.strftime("%Y-%m")
    live = False
    if q:
        if pts[-1][0] == ym:
            pts[-1] = (ym, float(q["c"]))
        elif pts[-1][0] < ym:
            pts.append((ym, float(q["c"])))
        live = True
    return {"pts": pts, "div": data.get("div", False), "src": data.get("src", "?"), "live": live}


# =========================================================================================================
# stories
# =========================================================================================================
def name_of(sym):
    return COMPANIES.get(sym, (sym,))[0]


def screen_name(sym):
    n = name_of(sym)
    return n.replace("the ", "").upper() if sym in ETFS else n.upper()


def aligned(sym_series, months):
    """Values of another series on the given months (forward-filled); None if it starts too late."""
    if not sym_series:
        return None
    m = dict(sym_series["pts"])
    out, last = [], None
    for ym in months:
        last = m.get(ym, last)
        if last is None:
            return None
        out.append(last)
    return out


def pick_events(cands, n, max_k=3, gap=0.13, lo=0.08, hi=0.86):
    chosen = []
    for e in sorted(cands, key=lambda e: -e["score"]):
        f = e["i"] / max(1, n - 1)
        if not lo <= f <= hi:
            continue
        if all(abs(f - c["i"] / max(1, n - 1)) >= gap for c in chosen):
            chosen.append(e)
        if len(chosen) >= max_k:
            break
    return sorted(chosen, key=lambda e: e["i"])


def growth_events(vals, months):
    n = len(vals)
    cands = []
    scores = {2: 1.0, 5: 1.5, 10: 2.4, 20: 1.8, 50: 2.0, 100: 2.7, 200: 2.0, 500: 2.3, 1000: 2.9}
    for k, sc in scores.items():
        i = next((j for j, v in enumerate(vals) if v >= 1000 * k), None)
        if i is not None:
            cands.append({"i": i, "kind": "milestone", "k": k, "score": sc, "label": f"{k}X", "color": GOLD})
    peak, best = 0, (0.0, 0, 0)
    for j, v in enumerate(vals):
        if v > vals[peak]:
            peak = j
        dd = 1 - v / vals[peak]
        if dd > best[0]:
            best = (dd, peak, j)
    if best[0] >= 0.25:
        dd = round(best[0] * 100)
        cands.append({"i": best[2], "kind": "drawdown", "drop": dd, "peak_i": best[1], "score": 2.2 + best[0],
                      "label": f"–{dd}%", "color": RED})
    if vals[-1] < 1000:
        ih = next((j for j, v in enumerate(vals) if v <= 500), None)
        if ih is not None:
            cands.append({"i": ih, "kind": "half", "score": 2.0, "label": "–50%", "color": RED})
        im = int(np.argmin(vals))
        if vals[im] < vals[-1] * 0.85:
            cands.append({"i": im, "kind": "bottom", "score": 1.9, "color": RED,
                          "label": f"–{round((1 - vals[im] / 1000) * 100)}%"})
    ev = pick_events(cands, n)
    for e in ev:
        e["value"] = vals[e["i"]]
        e["date"] = months[e["i"]]
    return ev


def base_facts(sym, s, months, vals, spy):
    final = vals[-1]
    m = final / 1000
    years = (len(months) - 1) / 12
    facts = {
        "company": name_of(sym), "ticker": sym, "invested": "$1,000",
        "start": month_label(months[0], True), "start_year": int(months[0][:4]),
        "years": round(years, 1),
        "final_value": money(final), "final_value_say": say_money(final),
        "multiple": round(m, 1) if m < 10 else round(m), "multiple_say": times_words(m) if m >= 1 else None,
        "total_return_pct": f"{(m - 1) * 100:,.0f}%",
        "as_of": "today" if s["live"] else month_label(months[-1], True),
        "dividends": "reinvested" if s["div"] else "not included (price only)",
    }
    if years >= 1.5 and m > 0:
        facts["per_year_pct"] = f"{(m ** (1 / years) - 1) * 100:.1f}%"
    if spy:
        sv = 1000 * spy[-1] / spy[0]
        facts["sp500_same_period"] = money(sv)
        facts["sp500_say"] = say_money(sv)
    return facts


def event_fact(e, months):
    f = {"id": e["id"], "date": month_label(months[e["i"]], True), "year": int(months[e["i"]][:4]),
         "type": e["kind"], "value": money(e["value"]), "value_say": say_money(e["value"])}
    if e["kind"] == "milestone":
        f["multiple"] = f"{e['k']} times the money"
    elif e["kind"] == "drawdown":
        f["drop_from_peak_pct"] = f"{e['drop']}%"
        f["peak_date"] = month_label(months[e["peak_i"]], True)
    elif e["kind"] == "half":
        f["note"] = "half of the money was gone"
    elif e["kind"] == "bottom":
        f["note"] = "the lowest point"
    elif e["kind"] == "lead":
        f["leader"] = e["leader_name"]
        f["leader_value"] = money(e["leader_value"])
        f["other_value"] = money(e["other_value"])
        if e.get("pull"):
            f["note"] = f"{e['leader_name']} pulls clearly ahead (it led the whole way)"
    return f


def story_single(sym, series, mode=None, years=None, asked=False):
    s = load_series(sym)
    if not s or len(s["pts"]) < 30:
        return None
    months = [p[0] for p in s["pts"]]
    prices = [p[1] for p in s["pts"]]
    now_ym = months[-1]
    if series == "peak":
        i_from = next((i for i, m in enumerate(months) if m >= add_months(now_ym, -180)), 0)
        i0 = max(range(i_from, len(prices)), key=lambda i: prices[i])
        if prices[-1] / prices[i0] > 0.6 or len(prices) - i0 < 12:
            return None
        mode = "peak"
    else:
        ipo = COMPANIES.get(sym, (None, 3, None))[2]
        options = {"ago": 0.7}
        if "2020-03" in months and months.index("2020-03") < len(months) - 24:
            options["crash"] = 0.15
        if ipo and months[0][:4] == str(ipo) and len(months) <= 12 * 30:
            options["ipo"] = 0.15
        mode = mode if mode in options else random.choices(list(options), list(options.values()))[0]
        if mode == "ago":
            avail = [y for y in (10, 5, 15, 20) if months[0] <= add_months(now_ym, -12 * y)]
            if not avail:
                return None
            if years not in avail:
                years = random.choices(avail, [{10: 0.5, 5: 0.2, 15: 0.15, 20: 0.15}[y] for y in avail])[0]
            start = add_months(now_ym, -12 * years)
            i0 = next(i for i, m in enumerate(months) if m >= start)
        elif mode == "crash":
            i0 = months.index("2020-03")
        else:
            i0 = 0
    months, prices = months[i0:], prices[i0:]
    vals = [1000 * p / prices[0] for p in prices]
    spy = None if sym in ETFS else aligned(load_series("SPY"), months)
    events = growth_events(vals, months)
    for k, e in enumerate(events, 1):
        e["id"] = f"e{k}"
    yrs = round((len(months) - 1) / 12)
    facts = base_facts(sym, s, months, vals, spy)
    facts["mode"] = {"ago": f"bought {yrs} years ago", "crash": "bought in March 2020, during the COVID crash",
                     "ipo": "bought the month it went public", "peak": "bought at the all-time high (the very top)"}[mode]
    facts["events"] = [event_fact(e, months) for e in events]
    gain = vals[-1] >= 1000
    line2 = {"ago": f"{yrs} YEARS AGO", "crash": "IN THE 2020 CRASH", "ipo": "AT ITS IPO",
             "peak": "AT THE VERY TOP"}[mode]
    return {
        "series": series, "mode": mode, "tickers": [sym], "names": [name_of(sym)], "asked": asked,
        "key": f"{series} {sym} {mode} {yrs}", "months": months, "lines": [vals], "ghost": spy,
        "colors": [GREEN if gain else RED], "events": events, "facts": facts, "years": yrs,
        "mood": "positive" if gain else "negative", "gain": gain, "src": s["src"], "div": s["div"],
        "headline": [[("$1,000", GOLD), (" IN " + screen_name(sym), WHITE)],
                     [(line2, RED if mode == "peak" else WHITE)]],
    }


def story_battle(a, b):
    sa, sb = load_series(a), load_series(b)
    if not sa or not sb:
        return None
    ma, mb = dict(sa["pts"]), dict(sb["pts"])
    common = sorted(set(ma) & set(mb))
    if len(common) < 40:
        return None
    start = max(common[0], add_months(common[-1], -120))
    months = [m for m in common if m >= start]
    va = [1000 * ma[m] / ma[months[0]] for m in months]
    vb = [1000 * mb[m] / mb[months[0]] for m in months]
    n = len(months)
    changes, lead = [], None
    for i in range(1, n):
        r = va[i] / vb[i]
        now = "a" if r > 1.03 else "b" if r < 1 / 1.03 else lead
        if lead and now and now != lead:
            changes.append({"i": i, "kind": "lead", "who": now})
        lead = now or lead
    events = []
    ok_pos = lambda c: 0.08 <= c["i"] / (n - 1) <= 0.95
    if changes:          # the lead change that decided it + the one just before (no other flip between them,
        last = changes[-1]                           # so the voice never contradicts the chart)
        prev = changes[-2] if len(changes) >= 2 else None
        if ok_pos(last):
            events.append(last)
            if prev and ok_pos(prev) and (last["i"] - prev["i"]) / (n - 1) >= 0.06:
                events.insert(0, prev)
        elif prev and ok_pos(prev):
            events.append(prev)
    else:                                             # one side led all along: show where it pulled away
        ratio = [max(x, y) / min(x, y) for x, y in zip(va, vb)]
        i = next((j for j, r in enumerate(ratio) if r >= 1.5 and j / (n - 1) >= 0.08), None)
        if i is not None and i / (n - 1) <= 0.92:
            events.append({"i": i, "kind": "lead", "who": "a" if va[i] > vb[i] else "b", "pull": True})
    for k, e in enumerate(events, 1):
        who = e["who"]
        e.update(id=f"e{k}", leader=a if who == "a" else b, leader_name=name_of(a if who == "a" else b),
                 leader_value=(va if who == "a" else vb)[e["i"]], other_value=(vb if who == "a" else va)[e["i"]],
                 value=(va if who == "a" else vb)[e["i"]], color=CYAN if who == "a" else ORANGE,
                 label=("PULLS AHEAD" if e.get("pull") else "LEADS"))
    yrs = round((n - 1) / 12)
    win = a if va[-1] >= vb[-1] else b
    wv, lv = max(va[-1], vb[-1]), min(va[-1], vb[-1])
    facts = {
        "company_a": name_of(a), "company_b": name_of(b), "invested_each": "$1,000",
        "start": month_label(months[0], True), "start_year": int(months[0][:4]), "years": yrs,
        "final_a": money(va[-1]), "final_a_say": say_money(va[-1]),
        "final_b": money(vb[-1]), "final_b_say": say_money(vb[-1]),
        "winner": name_of(win), "winner_multiple": f"{wv / 1000:.1f}" if wv < 10000 else f"{wv / 1000:.0f}",
        "difference": money(wv - lv), "difference_say": say_money(wv - lv),
        "as_of": "today" if (sa["live"] and sb["live"]) else month_label(months[-1], True),
        "dividends": "reinvested" if (sa["div"] and sb["div"]) else "not included (price only)",
        "events": [event_fact(e, months) for e in events],
    }
    return {
        "series": "battle", "mode": "battle", "tickers": [a, b], "names": [name_of(a), name_of(b)], "asked": False,
        "key": f"battle {a} {b}", "months": months, "lines": [va, vb], "ghost": None, "colors": [CYAN, ORANGE],
        "events": events, "facts": facts, "years": yrs, "winner": win, "mood": "positive", "gain": True,
        "src": sa["src"], "div": sa["div"] and sb["div"],
        "headline": [[(screen_name(a), CYAN), (" VS ", WHITE), (screen_name(b), ORANGE)],
                     [(f"$1,000 EACH · {yrs} YEARS", WHITE)]],
    }


def quote_day(ts):
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.fromtimestamp(ts, ZoneInfo("America/New_York")).date()
    except Exception:
        return (dt.datetime.fromtimestamp(ts, dt.timezone.utc) - dt.timedelta(hours=5)).date()


def after_us_close():
    """The first evening run after the New York close (16:15-21:00 New York time, Mon-Fri) gets MARKET SHOCK."""
    try:
        from zoneinfo import ZoneInfo
        ny = NOW.astimezone(ZoneInfo("America/New_York"))
    except Exception:
        ny = NOW - dt.timedelta(hours=5)
    return ny.weekday() < 5 and (16, 15) <= (ny.hour, ny.minute) < (21, 0)


def us_trading_day():
    try:
        from zoneinfo import ZoneInfo
        ny = NOW.astimezone(ZoneInfo("America/New_York"))
    except Exception:
        ny = NOW - dt.timedelta(hours=5)
    return ny.date(), ny.weekday() < 5


def story_shock():
    if not env("FINNHUB_API_KEY"):
        return None
    day, weekday = us_trading_day()
    if not weekday and not env("SERIES"):
        return None
    rows = []
    for sym in COMPANIES:
        if sym in ETFS:
            continue
        q, p = quote(sym), profile(sym)
        if not q or not p.get("shares"):
            continue
        if q.get("t") and quote_day(q["t"]) != day:
            continue
        shares = float(p["shares"]) * 1e6
        rows.append({"sym": sym, "c": q["c"], "pc": q["pc"], "dp": q.get("dp") or (q["c"] / q["pc"] - 1) * 100,
                     "delta": shares * (q["c"] - q["pc"]), "mcap": shares * q["c"]})
    if len(rows) < 20 or max(abs(r["dp"]) for r in rows) < 0.3:
        print("shock: market closed or no data")
        return None
    top = max(rows, key=lambda r: abs(r["delta"]))
    sym, delta = top["sym"], top["delta"]
    lost = delta < 0
    smaller = [r for r in rows if r["mcap"] < abs(delta) and r["sym"] != sym and COMPANIES[r["sym"]][1] <= 2]
    comp = max(smaller, key=lambda r: r["mcap"]) if smaller else None
    sector = COMPANIES[sym][3]
    peers = [r["dp"] for r in rows if COMPANIES[r["sym"]][3] == sector and r["sym"] != sym]
    sector_avg = sum(peers) / len(peers) if len(peers) >= 2 else None
    news = company_news(sym)
    facts = {
        "company": name_of(sym), "ticker": sym, "date": day.strftime("%B %d, %Y"),
        "market_cap_change": money(delta), "market_cap_change_say": say_money(delta),
        "direction": "lost" if lost else "added", "price_change_pct": f"{abs(top['dp']):.1f}%",
        "price_now": money2(top["c"]), "per_american": money(abs(delta) / US_POP),
        "per_american_say": say_money(abs(delta) / US_POP), "us_population": "about 340 million people",
    }
    if comp:
        facts["comparison"] = {"company": name_of(comp["sym"]), "its_whole_value": money(comp["mcap"]),
                               "its_whole_value_say": say_money(comp["mcap"])}
    if sector_avg is not None and abs(sector_avg) >= 1 and (sector_avg < 0) == lost:
        word = {"chips": "chip", "food": "food and drink", "finance": "financial", "health": "healthcare",
                "auto": "car"}.get(sector, sector)
        facts["sector_move"] = (f"other {word} stocks {'fell' if lost else 'rose'} {abs(sector_avg):.1f}% "
                                f"on average")
    facts["news"] = news
    word = "LOST" if lost else "ADDED"
    return {
        "series": "shock", "mode": "shock", "tickers": [sym], "names": [name_of(sym)], "asked": False,
        "key": f"shock {day}", "facts": facts, "delta": delta, "pct": top["dp"], "price": top["c"], "comp": comp,
        "mood": "negative" if lost else "positive", "gain": not lost, "src": "Finnhub", "div": False,
        "headline": [[(screen_name(sym), WHITE)], [(f"JUST {word}", RED if lost else GREEN)]],
        "events": [], "lines": [], "months": [], "ghost": None, "colors": [RED if lost else GREEN],
    }


# =========================================================================================================
# learning + choosing
# =========================================================================================================
def update_views(yt):
    due = [v for v in STATE["videos"] if v.get("id") and days_since(v.get("date", "")) >= 2
           and days_since(v.get("date", "")) <= 45 and days_since(v.get("views_at", "2000-01-01")) >= 1]
    for k in range(0, len(due), 50):
        chunk = due[k:k + 50]
        try:
            res = yt.videos().list(part="statistics", id=",".join(v["id"] for v in chunk)).execute()
        except Exception as e:
            print("views unavailable:", str(e)[:160])
            return
        stats = {it["id"]: int(it["statistics"].get("viewCount", 0)) for it in res.get("items", [])}
        for v in chunk:
            if v["id"] in stats:
                v["views"], v["views_at"] = stats[v["id"]], TODAY


def weights_for(field, arms, base, where=None):
    vids = [v for v in STATE["videos"] if v.get("views") is not None and (where is None or where(v))]
    logs = [math.log1p(v["views"]) for v in vids]
    mean_all = sum(logs) / len(logs) if logs else None
    out = {}
    for a in arms:
        own = [math.log1p(v["views"]) for v in vids if v.get(field) == a]
        if len(own) < 3 or mean_all is None:
            out[a] = base[a] * 1.5                        # explore every arm at least 3 times
        else:
            out[a] = base[a] * clamp(math.exp(sum(own) / len(own) - mean_all), 0.5, 2.0)
    return out


def pick(weights):
    arms = [a for a, w in weights.items() if w > 0]
    if not arms:
        return None
    if random.random() < 0.1:
        return random.choice(arms)
    return random.choices(arms, [weights[a] for a in arms])[0]


NAME_SKIP = {"target", "snap", "zoom", "lucid", "block"}
COMMON_UPPER = {"A", "I", "IT", "ON", "ALL", "NOW", "ARM", "GE", "CAT", "LOW", "HD", "COST", "KO", "MA", "V", "F",
                "T", "BA", "GM", "MU", "AMC", "SPY", "QQQ", "SNAP", "ZM"}


def find_tickers(text):
    found = set()
    for m in re.findall(r"\$([A-Za-z]{1,5}(?:[.-][A-Za-z])?)\b", text):
        sym = m.upper().replace(".", "-")
        if sym in COMPANIES:
            found.add(sym)
    for tok in re.findall(r"\b[A-Z]{2,5}\b", text):
        if tok in COMPANIES and tok not in COMMON_UPPER:
            found.add(tok)
    for a, b in re.findall(r"\b([A-Z]{1,5})[.-]([A-Z])\b", text):      # BRK.B / BRK-B
        if f"{a}-{b}" in COMPANIES:
            found.add(f"{a}-{b}")
    low = text.lower()
    for sym, info in COMPANIES.items():
        names = [n for n in [info[0].lower().replace("the ", "")] + info[4] if n not in NAME_SKIP]
        if any(re.search(rf"(?<![a-z]){re.escape(n)}(?![a-z])", low) for n in names if len(n) >= 3):
            found.add(sym)
    return found


def comment_requests(yt):
    counts = Counter()
    try:
        cid = STATE.get("channel_id")
        if not cid:
            items = yt.channels().list(part="id", mine=True).execute().get("items", [])
            cid = items[0]["id"] if items else None
            STATE["channel_id"] = cid
        if not cid:
            return counts
        res = yt.commentThreads().list(part="snippet", allThreadsRelatedToChannelId=cid, maxResults=100,
                                       order="time", textFormat="plainText").execute()
    except Exception as e:
        print("comments unavailable:", str(e)[:160])
        return counts
    for it in res.get("items", []):
        sn = it["snippet"]["topLevelComment"]["snippet"]
        if sn.get("authorChannelId", {}).get("value") == cid:
            continue
        for sym in find_tickers(sn.get("textOriginal") or sn.get("textDisplay", "")):
            counts[sym] += 1
    for sym in list(counts):
        if days_since(STATE["requests_done"].get(sym, "2000-01-01")) < 30:
            del counts[sym]
    if counts:
        print("comment requests:", dict(counts.most_common(5)))
    return counts


def pick_company(exclude=()):
    recent_syms = {t for v in STATE["videos"][-14:] for t in v.get("tickers", [])}
    pool = [s for s in COMPANIES if s not in recent_syms and s not in exclude]
    return random.choices(pool, [{1: 3.0, 2: 1.6, 3: 0.8}[COMPANIES[s][1]] * (0.4 if s in ETFS else 1)
                                 for s in pool])[0]


def build_story(series, requests_, tick, used_keys):
    if series == "shock":
        return story_shock()
    if series == "asked":
        for sym, _ in requests_.most_common(3):
            story = story_single(sym, "time_machine", asked=True)
            if story:
                return story
    elif series == "battle":
        pairs = [tuple(tick[:2])] if len(tick) >= 2 else \
            [p for p in BATTLES if f"battle {p[0]} {p[1]}" not in used_keys]
        random.shuffle(pairs)
        for a, b in pairs[:4]:
            story = story_battle(a, b)
            if story:
                return story
    elif series == "peak":
        pool = tick[:1] or [s for s in PEAK_POOL if s not in {t for v in STATE["videos"][-20:]
                                                               for t in v.get("tickers", [])}]
        random.shuffle(pool)
        for sym in pool[:6]:
            story = story_single(sym, "peak")
            if story:
                return story
    elif series == "time_machine":
        tries = tick[:1] or []
        while len(tries) < 5:
            tries.append(pick_company(exclude=tries))
        for sym in tries:
            story = story_single(sym, "time_machine", mode=env("MODE") or None,
                                 years=int(env("YEARS")) if env("YEARS", "").isdigit() else None)
            if story and story["key"] not in used_keys:
                return story
    return None


def choose_story(requests_):
    forced = env("SERIES", "").strip()
    tick = [t.strip().upper() for t in env("TICKER", "").replace(" ", ",").split(",") if t.strip()]
    shock_slot = after_us_close() and f"shock {us_trading_day()[0]}" not in recent("key", 12)
    order = []
    if forced:
        order.append(forced)
    elif shock_slot and env("FINNHUB_API_KEY"):
        order.append("shock")
    if not forced and requests_:
        order.append("asked")
    base = {k: v[2] for k, v in SERIES_INFO.items() if v[2] > 0}
    while len(order) < 7:
        order.append(pick(weights_for("series", list(base), base)))
    used_keys = set(recent("key", 60))
    for series in order:
        if time.time() - START > 9 * 60:
            print("story search: out of time")
            break
        try:
            story = build_story(series, requests_, tick, used_keys)
        except Exception as e:                      # one bad data source must not kill the run
            print("story failed:", series, type(e).__name__, str(e)[:160])
            story = None
        if story:
            print("series:", story["series"], "| key:", story["key"])
            return story
    why = " | ".join(PROVIDER_ERR.values()) or "no details"
    gh_note("error", "No price data", f"Could not load price history for any stock. {why}. Fix: add the "
            "TIINGO_API_KEY secret (free at tiingo.com) or check the errors above.")
    raise SystemExit(1)


# =========================================================================================================
# script (Gemini words it, code checks it; templates if Gemini is unavailable)
# =========================================================================================================
GEMINI_ERR = []


def gemini(prompt, ok, rounds=2):
    key = env("GEMINI_API_KEY")
    if not key:
        GEMINI_ERR.append("GEMINI_API_KEY secret is not set")
        return None
    models = [env("GEMINI_MODEL", "gemini-3.5-flash"), "gemini-flash-latest", "gemini-3.1-flash-lite"]
    for r in range(rounds):
        for model in models:
            try:
                resp = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    params={"key": key}, timeout=(10, 60),
                    json={"contents": [{"parts": [{"text": prompt}]}],
                          "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9}})
                if not resp.ok:
                    print(model, resp.status_code)
                    GEMINI_ERR.append(f"{model} HTTP {resp.status_code}")
                    continue
                data = json.loads(resp.json()["candidates"][0]["content"]["parts"][0]["text"])
                if ok(data):
                    return data
                print(model, "rejected output")
                GEMINI_ERR.append(f"{model} output failed the checks")
            except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as e:
                print(model, "error:", type(e).__name__)
                GEMINI_ERR.append(f"{model} {type(e).__name__}")
        if r + 1 < rounds:
            time.sleep(10)
    return None


HOOK_STYLE = {
    "you": "second person, as if it really happened to the viewer (e.g. 'You put $1,000 into Netflix in 2015.')",
    "question": "one direct question (e.g. 'What happened to $1,000 in Netflix?')",
    "imagine": "an 'imagine' scenario (e.g. 'Imagine you bought $1,000 of Netflix in 2015 and forgot.')",
    "number": "a short punchy fragment that starts with the money (e.g. '$1,000. Netflix. 2015.')",
    "asked": "say that viewers asked for this company in the comments (e.g. 'You asked for AMD. $1,000, ten "
             "years ago.')",
}


def beats_for(story):
    """Ordered beats: hook, one per chart event, reveal, kicker (shock has its own set)."""
    if story["series"] == "shock":
        b = ["hook"]
        if story["facts"].get("comparison"):
            b.append("compare")
        b += ["person"]
        if story["facts"]["news"] or story["facts"].get("sector_move"):
            b.append("reason")
        return b + ["close"]
    return ["hook"] + [e["id"] for e in story["events"]] + ["reveal", "kicker"]


def beat_rules(story, beats):
    f = story["facts"]
    s = story["series"]
    out = []
    for b in beats:
        if b == "hook":
            out.append("hook: max 9 words, spoken in the first 2 seconds. Must NOT reveal how it ended."
                       if s != "shock" else
                       f"hook: max 9 words: {f['company']} just {f['direction']} {f['market_cap_change_say']} "
                       "of market value in one day.")
        elif b.startswith("e"):
            e = next(x for x in f["events"] if x["id"] == b)
            out.append(f"{b}: max 12 words about {e['date']}: {json.dumps(e)}")
        elif b == "reveal":
            out.append("reveal: max 12 words: what it is worth " + (
                f"today: {f['final_value_say']}" if s != "battle" else
                f"today: {f['company_a']} {f['final_a_say']} vs {f['company_b']} {f['final_b_say']}"))
        elif b == "kicker":
            if s == "battle":
                out.append(f"kicker: max 8 words: {f['winner']} wins (by about {f['difference_say']}).")
            elif f.get("sp500_say"):
                out.append(f"kicker: max 9 words: the S&P 500 over the same time turned $1,000 into "
                           f"{f['sp500_say']} (compare, no advice).")
            else:
                out.append("kicker: max 8 words: " + (f"that is {f['multiple_say']} the money."
                                                    if story["gain"] else f"that is {f['total_return_pct']}."))
        elif b == "compare":
            c = f["comparison"]
            out.append(f"compare: max 12 words: that is more than all of {c['company']} is worth "
                       f"({c['its_whole_value_say']}).")
        elif b == "person":
            out.append(f"person: max 10 words: about {f['per_american_say']} for every American.")
        elif b == "reason":
            out.append("reason: max 14 words: the likely reason, ONLY from the news or sector_move facts, in your "
                       "own words (never copy a headline). If unclear, say what the facts show.")
        elif b == "close":
            out.append(f"close: max 12 words: shares {'fell' if not story['gain'] else 'rose'} "
                       f"{f['price_change_pct']} to {f['price_now']}.")
    return out


def template_script(story, hook, beats):
    f, s = story["facts"], story["series"]
    name = f.get("company", "")
    lines = []
    for b in beats:
        if b == "hook":
            if s == "battle":
                a, c = f["company_a"], f["company_b"]
                lines.append({"you": f"You put $1,000 in {a} and $1,000 in {c}.",
                              "question": f"{a} or {c}? $1,000 each, {f['start_year']}.",
                              "imagine": f"Imagine $1,000 in {a} and $1,000 in {c}.",
                              "number": f"$1,000 each. {a} versus {c}. {f['start_year']}."}.get(hook) or
                             f"{a} or {c}? $1,000 each, {f['start_year']}.")
            elif s == "shock":
                lines.append(f"{name} just {f['direction']} {f['market_cap_change_say']} in one day.")
            else:
                when = {"ago": f"in {f['start_year']}", "crash": "in the 2020 crash",
                        "ipo": "at its IPO", "peak": "at the very top"}[story["mode"]]
                bare = when[3:] if when.startswith("in ") else when
                lines.append({"you": f"You put $1,000 into {name} {when}.",
                              "question": f"What happened to $1,000 in {name} {when}?",
                              "imagine": f"Imagine $1,000 in {name} {when}.",
                              "number": f"$1,000. {name}. {bare[:1].upper() + bare[1:]}.",
                              "asked": f"You asked for {name}. $1,000 {when}."}.get(hook) or
                             f"You put $1,000 into {name} {when}.")
        elif b.startswith("e"):
            e = next(x for x in f["events"] if x["id"] == b)
            yr, k_ev = e["year"], int(b[1:])
            if e["type"] == "lead":
                lines.append(f"By {yr}, {e['leader']} pulls ahead." if e.get("pull") else
                             f"By {yr}, {e['leader']} takes the lead." if k_ev == 1 else
                             f"Then in {yr}, {e['leader']} strikes back.")
            elif e["type"] == "milestone":
                lines.append(f"By {yr}, your money had doubled." if e["multiple"].startswith("2 ") else
                             [f"By {yr}, it was worth {e['value_say']}.", f"In {yr}, it hit {e['value_say']}.",
                              f"{yr}: {e['multiple'].replace(' the money', '')} the money."][(k_ev - 1) % 3])
            elif e["type"] == "drawdown":
                lines.append([f"Then {yr} hit. It fell {e['drop_from_peak_pct']} from the top.",
                              f"Then it crashed {e['drop_from_peak_pct']} in {yr}."][(k_ev - 1) % 2])
            else:
                lines.append({
                    "half": f"By {yr}, half of it was gone.",
                    "bottom": f"At the bottom, in {yr}, just {e['value_say']} was left.",
                }[e["type"]])
        elif b == "reveal":
            v = f.get("final_value_say")
            lines.append(f"Today: {f['company_a']} {f['final_a_say']}, {f['company_b']} {f['final_b_say']}."
                         if s == "battle" else random.choice([f"Today, it's worth about {v}.", f"Today? About {v}.",
                                                              f"Now it's worth about {v}."]))
        elif b == "kicker":
            if s == "battle":
                lines.append(f"{f['winner']} wins by about {f['difference_say']}.")
            elif f.get("sp500_say"):
                beat = story["lines"][0][-1] > 1000 * story["ghost"][-1] / story["ghost"][0]
                lines.append(random.choice([f"The S&P 500 made it {f['sp500_say']}.",
                                            f"The S&P 500 turned it into {f['sp500_say']}."] +
                                           ([f"The S&P 500? Just {f['sp500_say']}."] if beat else [])))
            else:
                lines.append(f"That's {f['multiple_say']} your money." if story["gain"] else
                             f"That's {f['total_return_pct'].lstrip('-')} gone.")
        elif b == "compare":
            lines.append(f"That's more than all of {f['comparison']['company']} is worth.")
        elif b == "person":
            lines.append(f"About {f['per_american_say']} for every American.")
        elif b == "reason":
            lines.append(f"It wasn't alone: {f['sector_move']}." if f.get("sector_move") else
                         "Traders are reacting to fresh company news.")
        elif b == "close":
            lines.append(f"Shares {'fell' if not story['gain'] else 'rose'} {f['price_change_pct']} "
                         f"to {f['price_now']}.")
    return lines


def default_title(story):
    f, s = story["facts"], story["series"]
    if s == "battle":
        return random.choice([f"{f['company_a']} vs {f['company_b']}: $1,000 Each, {f['years']} Years",
                              f"$1,000 in {f['company_a']} or {f['company_b']}?"])
    if s == "shock":
        return f"{f['company']} Just {f['direction'].title()} {short_money(abs(story['delta']))} in One Day"
    name = f["company"]
    return {"ago": random.choice([f"$1,000 in {name} {story['years']} Years Ago…",
                                  f"I Put $1,000 Into {name} in {f['start_year']}",
                                  f"What $1,000 in {name} in {f['start_year']} Is Worth Now"]),
            "crash": f"$1,000 in {name} During the 2020 Crash…",
            "ipo": f"$1,000 in {name} at Its IPO…",
            "peak": random.choice([f"Buying {name} at the Very Top…", f"$1,000 in {name} at Its Peak"])}[story["mode"]]


def title_ok(title, story):
    if not title or len(title) > 80:
        return False
    if story["series"] == "shock":
        return True
    f = story["facts"]
    ok_nums = {1000.0, float(f.get("start_year", 0)), float(story.get("years", 0)), 2020.0}
    return all(x in ok_nums or x <= 12 for x in numbers_in(INDEX_NAMES.sub("", title)))   # never reveal the result


BANNED = re.compile(r"did you know|you should (buy|sell)|buy now|sell now|guarantee|financial advice|"
                    r"not financial|subscribe|like and", re.I)


def write_script(story, hook):
    beats = beats_for(story)
    allowed = collect_numbers(story["facts"]) + [1000.0]
    limits = {"hook": 10, "kicker": 10, "person": 11, "reason": 15, "close": 13}
    f = story["facts"]

    def ok(d):
        if not isinstance(d, dict) or not isinstance(d.get("lines"), list) or len(d["lines"]) != len(beats):
            return False
        for b, line in zip(beats, d["lines"]):
            line = str(line).strip()
            if not line or len(line.split()) > limits.get(b, 14) or BANNED.search(line):
                return False
            good, bad = numbers_ok(line, allowed)
            if not good:
                print("number not in data:", bad, "|", line)
                return False
        rev = beats.index("reveal") if "reveal" in beats else None
        if rev is not None and story["series"] != "battle":
            if not numbers_in(d["lines"][rev]):
                return False
        return bool(d.get("question"))

    hook_style = HOOK_STYLE.get(hook, HOOK_STYLE["you"])
    if f.get("company"):
        hook_style = hook_style.replace("Netflix", f["company"]).replace("AMD", f["company"])
    if f.get("company_a"):
        hook_style = hook_style.replace("$1,000 in Netflix", f"$1,000 in {f['company_a']} vs {f['company_b']}") \
            .replace("Netflix", f["company_a"])
    if f.get("start_year"):
        hook_style = hook_style.replace("2015", str(f["start_year"]))
    series_txt = {"time_machine": "TIME MACHINE: what $1,000 in a famous stock became",
                  "peak": "BOUGHT THE TOP: $1,000 invested at a stock's all-time high",
                  "battle": "STOCK BATTLE: $1,000 in each of two rivals, a race to today",
                  "shock": "MARKET SHOCK: today's biggest move in market value, in dollars"}[story["series"]]
    prompt = (
        f"You write the voice-over for a 15-22 second YouTube Short on the channel 'Bull & Bear Daily'. "
        f"Series: {series_txt}. A live counter and chart on screen show the numbers as you speak.\n"
        f"FACTS (the only source; use these numbers exactly or their '_say' rounding; never invent numbers, "
        f"dates, reasons or quotes):\n{json.dumps(f, ensure_ascii=False)}\n"
        f"Write exactly {len(beats)} lines, one per beat, in this order:\n- " + "\n- ".join(beat_rules(story, beats))
        + f"\nHook style: {hook_style}\n"
        "Rules: spoken American English, short and punchy, every line moves the story; no greetings; never "
        "'Did you know'; never tell anyone to buy, sell or hold; money as '$' with digits (e.g. $287,000); "
        "multiples as words like '28 times'; years as digits; the hook never reveals the ending.\n"
        "Also return: question (max 12 words, makes people comment, e.g. which stock to run next; no advice), "
        "title (max 60 characters, curiosity, must NOT reveal the final value, multiple or winner"
        + ("" if story["series"] != "shock" else "; for this series the dollar move may be in the title")
        + "), tags (6-10 short tags).\n"
        'Return JSON: {"lines": ["..."], "question": "...", "title": "...", "tags": ["..."]}')
    data = gemini(prompt, ok)
    if not data:
        print("script: template")
        gh_note("warning", "Script", "Gemini unavailable, template script used: " + "; ".join(GEMINI_ERR[-6:]))
        data = {"lines": template_script(story, hook, beats),
                "question": random.choice(["Which stock should we run next?", "Would you have held on?",
                                           "Which company should we test next?"]) if story["series"] != "battle" else
                "Which battle should we run next?", "title": default_title(story),
                "tags": []}
    data["lines"] = [re.sub(r"\s+", " ", str(x)).strip() for x in data["lines"]]
    if not title_ok(data.get("title"), story):
        data["title"] = default_title(story)
    data["beats"] = beats
    return data


# =========================================================================================================
# audio: voice per line (exact timing), music by mood, synthesized SFX, mix
# =========================================================================================================
async def _tts_line(text, path):
    import edge_tts
    try:
        comm = edge_tts.Communicate(text, VOICE, rate=RATE, boundary="WordBoundary")
    except TypeError:
        comm = edge_tts.Communicate(text, VOICE, rate=RATE)
    words = []
    with open(path, "wb") as fh_:
        async for ch in comm.stream():
            if ch["type"] == "audio":
                fh_.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append((ch["text"], ch["offset"] / 1e7, ch["duration"] / 1e7))
    return words


def decode(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def estimate_words(text, t0, dur):
    toks = text.split()
    w = [len(t) + 2 for t in toks]
    total, out, t = sum(w), [], t0
    for tok, x in zip(toks, w):
        d = dur * x / total
        out.append((tok, t, d))
        t += d
    return out


def align_words(text, events, t0, dur):
    """Script tokens (with $ and punctuation) timed by the TTS word events; unmatched tokens take the next unused
    event between their neighbours, else an interpolated time."""
    toks = text.split()
    if not events:
        return estimate_words(text, t0, dur)
    norm = lambda x: re.sub(r"[^a-z0-9]", "", x.lower())
    hits, p = [], 0
    for tok in toks:
        nt, hit = norm(tok), None
        for q in range(p, min(p + 4, len(events))):
            ne = norm(events[q][0])
            if ne and nt and (nt.startswith(ne) or ne.startswith(nt)):
                hit = q
                break
        hits.append(hit)
        if hit is not None:
            p = hit + 1
    used = {h for h in hits if h is not None}
    for k, h in enumerate(hits):
        if h is None:
            lo = max([x for x in hits[:k] if x is not None], default=-1)
            hi = min([x for x in hits[k + 1:] if x is not None], default=len(events))
            free = [q for q in range(lo + 1, hi) if q not in used]
            if free:
                hits[k] = free[0]
                used.add(free[0])
    out, last = [], t0
    for k, tok in enumerate(toks):
        if hits[k] is not None:
            st, du = events[hits[k]][1], events[hits[k]][2]
        else:
            nxt = next((events[h][1] for h in hits[k + 1:] if h is not None), None)
            st, du = (last if nxt is None or nxt <= last else (last + nxt) / 2), 0.2
        st = max(st, last)
        out.append((tok, st, du))
        last = st + 0.01
    return out


def make_voice(lines, beats):
    """TTS each line, trim silence, place with short gaps (a longer breath before the reveal)."""
    tts = TTS_FN
    t, segs, info = 0.12, [], []
    for k, text in enumerate(lines):
        mp3 = WORK / f"line{k}.mp3"
        words = pcm = None
        for attempt in range(3):
            try:
                words = tts(text, mp3)
                pcm = decode(mp3)
                break
            except Exception as e:
                print("voice failed:", type(e).__name__, str(e)[:120])
                time.sleep(3 + 4 * attempt)
        if pcm is None:
            return None
        loud = np.where(np.abs(pcm) > 0.02 * max(1e-6, float(np.abs(pcm).max())))[0] if len(pcm) else []
        if len(pcm) < SR * 0.2 or len(loud) == 0:
            return None
        a = max(0, int(loud[0]) - int(0.02 * SR))
        b = min(len(pcm), int(loud[-1]) + int(0.06 * SR))
        seg = pcm[a:b]
        lead = a / SR
        dur = len(seg) / SR
        words = align_words(text, [(w, t + max(0.0, o - lead), d) for w, o, d in words or []], t, dur)
        info.append({"text": text, "start": t, "end": t + dur, "words": words})
        segs.append((int(t * SR), seg))
        nxt = beats[k + 1] if k + 1 < len(beats) else None
        t += dur + (0.42 if nxt in ("reveal", "close") else 0.13)
    total = int((t + 2.0) * SR)
    voice = np.zeros(total, dtype=np.float32)
    for pos, seg in segs:
        voice[pos:pos + len(seg)] += seg[: max(0, total - pos)]
    return {"lines": info, "pcm": voice, "end": info[-1]["end"]}


def silent_voice(lines, beats):
    t, info = 0.3, []
    for k, text in enumerate(lines):
        dur = 0.36 * len(text.split()) + 0.35
        info.append({"text": text, "start": t, "end": t + dur, "words": estimate_words(text, t, dur)})
        nxt = beats[k + 1] if k + 1 < len(beats) else None
        t += dur + (0.45 if nxt in ("reveal", "close") else 0.15)
    return {"lines": info, "pcm": np.zeros(int((t + 2.0) * SR), dtype=np.float32), "end": info[-1]["end"]}


def edge_tts_fn(text, path):
    return asyncio.run(_tts_line(text, path))


TTS_FN = edge_tts_fn


def write_wav(path, pcm, rate=SR):
    data = (np.clip(pcm, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data.tobytes())


class Sfx:
    def __init__(self, total):
        self.buf = np.zeros(int(total * SR) + SR, dtype=np.float32)
        self.rng = np.random.default_rng(7)

    def add(self, t, sig, gain=1.0):
        i = int(max(0, t) * SR)
        n = min(len(sig), len(self.buf) - i)
        if n > 0:
            self.buf[i:i + n] += sig[:n] * gain

    def env(self, n, attack=0.005, decay=0.2):
        tt = np.arange(n) / SR
        return np.minimum(1, tt / max(attack, 1e-4)) * np.exp(-tt / decay)

    def noise(self, n, smooth=0.2):
        x = self.rng.uniform(-1, 1, n).astype(np.float32)
        y = np.empty_like(x)
        acc = 0.0
        for i in range(n):                              # one-pole low-pass
            acc += smooth * (x[i] - acc)
            y[i] = acc
        return y

    def whoosh(self, d=0.5):
        n = int(d * SR)
        nz = self.noise(n, 0.12)
        shape = np.sin(np.linspace(0, np.pi, n)) ** 2
        return nz * shape * 1.6

    def tick(self):
        n = int(0.025 * SR)
        tt = np.arange(n) / SR
        return np.sin(2 * np.pi * 2600 * tt) * np.exp(-tt / 0.004) * 0.6

    def ding(self):
        n = int(0.9 * SR)
        tt = np.arange(n) / SR
        return (np.sin(2 * np.pi * 1318.5 * tt) + 0.6 * np.sin(2 * np.pi * 1975.5 * tt)) * np.exp(-tt / 0.25) * 0.5

    def drop(self):
        n = int(0.7 * SR)
        tt = np.arange(n) / SR
        f = 420 * np.exp(-tt * 3.2) + 60
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt / 0.35) * 0.8

    def riser(self, d=1.2):
        n = int(d * SR)
        tt = np.arange(n) / SR
        p = tt / d
        f = 140 + 700 * p ** 2
        tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.25
        return (self.noise(n, 0.08 + 0.3 * 0.5) * 1.2 + tone) * p ** 2

    def boom(self):
        n = int(1.4 * SR)
        tt = np.arange(n) / SR
        f = 58 * (1 - 0.35 * tt / 1.4)
        return (np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.25 * self.noise(n, 0.05) * 3) * np.exp(-tt / 0.42)


def music_track(mood):
    tracks = sorted(MUSIC_DIR.glob("**/*.mp3")) if MUSIC_DIR.exists() else []
    if not tracks:
        return None
    words = {"negative": ("dark", "sad", "cinematic", "tense", "suspense", "slowed"),
             "neutral": ("lofi", "chill", "calm", "ambient", "vlog", "focus", "study")}

    def mood_of(p):
        nm = p.as_posix().lower()
        for m, ws in words.items():
            if any(w in nm for w in ws):
                return m
        return "positive"

    fit = [p for p in tracks if mood_of(p) == mood] or tracks
    return random.choice(fit)


def probe_duration(path):
    try:
        return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                     "default=nw=1:nk=1", str(path)], capture_output=True, text=True,
                                    check=True).stdout.strip())
    except Exception:
        return 0.0


def make_audio(story, timing, voice):
    T = timing["T"]
    vpath, spath, out = WORK / "voice.wav", WORK / "sfx.wav", WORK / "mix.wav"
    pcm = voice["pcm"][: int(T * SR)]
    pcm = np.pad(pcm, (0, max(0, int(T * SR) - len(pcm))))
    write_wav(vpath, pcm)
    sfx = Sfx(T)
    if SFX_ON:
        sfx.add(0.0, sfx.whoosh(0.45), 0.5)
        for t in timing.get("ticks", []):
            sfx.add(t, sfx.tick(), 0.18)
        for ev in timing.get("event_times", []):
            if ev["kind"] in ("drawdown", "half", "bottom"):
                sfx.add(ev["t"], sfx.drop(), 0.55)
            elif ev["kind"] in ("milestone", "person"):
                sfx.add(ev["t"], sfx.ding(), 0.35)
            else:
                sfx.add(ev["t"] - 0.15, sfx.whoosh(0.4), 0.45)
        tr = timing.get("t_reveal")
        if tr:
            sfx.add(max(0, tr - 1.1), sfx.riser(1.1), 0.35)
            sfx.add(tr, sfx.boom(), 0.7)
            if story.get("gain"):
                sfx.add(tr + 0.05, sfx.ding(), 0.3)
    peak = float(np.abs(sfx.buf).max()) or 1.0
    write_wav(spath, sfx.buf[: int(T * SR)] / max(peak, 1.0) * 0.9)
    args, chains = ["-i", str(vpath)], ["[0:a]aresample=44100,highpass=f=70,"
                                         "acompressor=threshold=-20dB:ratio=3:attack=5:release=90[v]"]
    mix = "[v]"
    n_in = 1
    track = music_track(story["mood"])
    if track:
        dur = probe_duration(track)
        start = round(random.uniform(0, max(0.0, dur - T - 3) * 0.5), 1)
        args += ["-ss", str(start), "-stream_loop", "-1", "-i", str(track)]
        chains.append(f"[{n_in}:a]aresample=44100,volume={MUSIC_VOL},afade=t=in:d=0.4,"
                      f"afade=t=out:st={max(0, T - 1.3):.2f}:d=1.3[m]")
        mix += "[m]"
        n_in += 1
        print("music:", track.name)
    args += ["-i", str(spath)]
    chains.append(f"[{n_in}:a]aresample=44100,volume={0.55 * SFX_VOL:.3f}[s]")
    mix += "[s]"
    n_in += 1
    chains.append(f"{mix}amix=inputs={n_in}:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    try:
        subprocess.run(["ffmpeg", "-y", "-v", "error", *args, "-filter_complex", ";".join(chains), "-map", "[a]",
                        "-t", f"{T:.3f}", "-ar", "44100", "-ac", "2", str(out)], check=True)
    except subprocess.CalledProcessError:
        if not track:
            raise
        print("music skipped (ffmpeg error)")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(vpath), "-i", str(spath), "-filter_complex",
                        "[0:a]aresample=44100,highpass=f=70,acompressor=threshold=-20dB:ratio=3:attack=5:release=90[v];"
                        f"[1:a]aresample=44100,volume={0.55 * SFX_VOL:.3f}[s];"
                        "[v][s]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]",
                        "-map", "[a]", "-t", f"{T:.3f}", "-ar", "44100", "-ac", "2", str(out)], check=True)
    return out


# =========================================================================================================
# timing: chart progress follows the voice (each event is reached exactly when its line starts)
# =========================================================================================================
def make_timing(story, voice, beats):
    lines = voice["lines"]
    starts = {b: ln["start"] for b, ln in zip(beats, lines)}
    T = max(12.0, voice["end"] + 1.8)
    timing = {"T": T, "lines": lines, "starts": starts, "voice_end": voice["end"], "event_times": []}
    if story["series"] == "shock":
        tc = max(1.6, starts.get("compare", starts.get("person", 2.0)) - 0.2)
        timing["t_count"] = tc
        timing["t_reveal"] = tc                        # the counter lands = the hit
        for b in ("compare", "person"):
            if b in starts:
                timing["event_times"].append({"t": starts[b], "kind": b, "i": 0})
        ticks, last_v, last_t = [], 0.0, -1.0
        for k in range(int(tc * FPS)):
            t = k / FPS
            v = shock_value(t, tc)
            if v - last_v >= 0.05 and t - last_t >= 0.085:
                ticks.append(t)
                last_v, last_t = v, t
        timing["ticks"] = ticks
        return timing
    n = len(story["months"])
    anchors = [(0.0, 0.0)]
    for e in story["events"]:
        t = starts[e["id"]]
        f = max(anchors[-1][1] + 0.02, e["i"] / (n - 1))
        anchors.append((t, min(f, 0.97)))
    t_rev = starts["reveal"]
    anchors.append((max(t_rev, anchors[-1][0] + 0.4), 1.0))
    timing["anchors"] = anchors
    timing["t_reveal"] = t_rev
    timing["t_kicker"] = starts.get("kicker")
    for e in story["events"]:
        timing["event_times"].append({"t": starts[e["id"]], "kind": e["kind"], "i": e["i"]})
    # counter ticks: one per 4% change of the value, at most ~12 per second
    vals = story["lines"][0]
    ticks, last_v, last_t = [], vals[0], -1.0
    for k in range(int(t_rev * FPS) + 1):
        t = k / FPS
        v = interp(vals, progress(anchors, t) * (n - 1))
        if abs(math.log(max(v, 1e-6) / max(last_v, 1e-6))) >= 0.04 and t - last_t >= 0.085:
            ticks.append(t)
            last_v, last_t = v, t
    timing["ticks"] = ticks
    return timing


def shock_value(t, tc):
    """Share of the day's move shown by the counter (starts at 35% so the first frame already hits)."""
    return 0.35 + 0.65 * ease_out(t / tc)


def progress(anchors, t):
    if t <= anchors[0][0]:
        return anchors[0][1]
    for (t0, f0), (t1, f1) in zip(anchors, anchors[1:]):
        if t <= t1:
            x = (t - t0) / max(1e-6, t1 - t0)
            if (t1, f1) == anchors[-1]:
                x = 1 - (1 - x) ** 1.6                 # ease into the reveal
            else:
                x = 0.55 * x + 0.45 * x * x * (3 - 2 * x)   # slow down at each event
            return f0 + (f1 - f0) * x
    return anchors[-1][1]


def interp(vals, x):
    x = clamp(x, 0, len(vals) - 1)
    i = int(x)
    if i >= len(vals) - 1:
        return vals[-1]
    return vals[i] + (vals[i + 1] - vals[i]) * (x - i)


STOPWORDS = {"a", "an", "the", "in", "into", "of", "to", "by", "at", "on", "for", "and", "or", "your", "its", "it",
             "was", "is", "just", "about", "than", "had", "has", "with", "from", "that", "this", "you", "be"}
BREAK_BEFORE = {"in", "into", "by", "at", "on", "for", "to", "from", "with", "than", "and", "or", "but"}


def caption_chunks(lines):
    """1-4 word chunks that follow the phrasing: break on punctuation or before a preposition, never end a chunk
    on a little word, never leave one word hanging."""
    chunks = []
    for ln in lines:
        words = ln["words"]
        cur = []
        for k, w in enumerate(words):
            cur.append(w)
            txt = " ".join(x[0] for x in cur)
            left = len(words) - k - 1
            nxt = re.sub(r"[^a-z]", "", words[k + 1][0].lower()) if left else ""
            punct = re.search(r"[.,!?;:]$", w[0])
            small = re.sub(r"[^a-z']", "", w[0].lower()) in STOPWORDS
            full = len(cur) >= 3 or len(txt) >= 15
            soft = len(cur) >= 2 and nxt in BREAK_BEFORE and left >= 3 and len(txt) >= 8
            brk = punct or ((full or soft) and not small) or len(cur) >= 4
            if brk and not punct and left == 1 and len(txt) + len(words[-1][0]) <= 20:
                brk = False
            if brk or left == 0:
                chunks.append({"words": cur, "t0": cur[0][1], "line_end": ln["end"]})
                cur = []
    for k, c in enumerate(chunks):
        nxt = chunks[k + 1]["t0"] if k + 1 < len(chunks) else c["line_end"] + 0.3
        c["t1"] = min(nxt, c["line_end"] + 0.3) if nxt - c["line_end"] > 0.05 else nxt
    return chunks


# =========================================================================================================
# drawing
# =========================================================================================================
FONT_URLS = {
    "anton": "https://raw.githubusercontent.com/google/fonts/main/ofl/anton/Anton-Regular.ttf",
    "barlow": "https://raw.githubusercontent.com/google/fonts/main/ofl/barlowsemicondensed/"
              "BarlowSemiCondensed-Bold.ttf",
    "barlowm": "https://raw.githubusercontent.com/google/fonts/main/ofl/barlowsemicondensed/"
               "BarlowSemiCondensed-SemiBold.ttf",
}
FONT_FALLBACK = ["/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def ensure_fonts():
    FONT_DIR.mkdir(exist_ok=True)
    for name, url in FONT_URLS.items():
        p = FONT_DIR / f"{name}.ttf"
        if p.exists() or env("FONT_DOWNLOAD", "1") != "1":
            continue
        r = http_get(url, tries=2)
        if r is not None and r.status_code == 200 and len(r.content) > 10000:
            p.write_bytes(r.content)


@functools.lru_cache(maxsize=None)
def font(name, size):
    for p in [FONT_DIR / f"{name}.ttf"] + FONT_FALLBACK:
        try:
            return ImageFont.truetype(str(p), size)
        except OSError:
            continue
    return ImageFont.load_default()


def text_w(d, txt, f, stroke=0):
    b = d.textbbox((0, 0), txt, font=f, stroke_width=stroke)
    return b[2] - b[0]


def pill(d, x, y, txt, f, fg, bg, pad=(18, 9), anchor="l", outline=None):
    w = text_w(d, txt, f)
    asc, desc = f.getmetrics()
    h = asc + desc
    x0 = x if anchor == "l" else x - (w + 2 * pad[0]) / 2 if anchor == "c" else x - (w + 2 * pad[0])
    box = [x0, y, x0 + w + 2 * pad[0], y + h + 2 * pad[1]]
    d.rounded_rectangle(box, radius=(h + 2 * pad[1]) // 2, fill=bg, outline=outline, width=3 if outline else 0)
    d.text((x0 + pad[0], y + pad[1]), txt, font=f, fill=fg)
    return box


def mix(c1, c2, a):
    return tuple(int(c1[i] * (1 - a) + c2[i] * a) for i in range(3))


def brand_mark(size=40):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 5, fill=(18, 34, 66, 255))
    s = size
    d.polygon([(s * 0.18, s * 0.62), (s * 0.36, s * 0.26), (s * 0.54, s * 0.62)], fill=GREEN + (255,))
    d.polygon([(s * 0.48, s * 0.40), (s * 0.82, s * 0.40), (s * 0.65, s * 0.78)], fill=RED + (255,))
    return im


def logo_tile(sym, size):
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    td = ImageDraw.Draw(tile)
    lg = None if sym in ETFS else logo_image(sym)
    if lg is not None:
        td.rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 5, fill=(255, 255, 255, 255))
        lg = lg.copy()
        lg.thumbnail((int(size * 0.76), int(size * 0.76)), Image.LANCZOS)
        tile.alpha_composite(lg, ((size - lg.width) // 2, (size - lg.height) // 2))
        return tile
    td.rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 5, fill=(28, 48, 92, 255))
    label = "S&P" if sym == "SPY" else "NDX" if sym == "QQQ" else sym[:4]
    f = font("anton", int(size * (0.42 if len(label) <= 3 else 0.34)))
    w = text_w(td, label, f)
    asc, desc = f.getmetrics()
    td.text(((size - w) / 2, (size - asc - desc) / 2), label, font=f, fill=WHITE)
    return tile


def gradient_bg(story):
    y = np.linspace(0, 1, HT, dtype=np.float32)[:, None]
    top, bot = np.array(BG1, np.float32), np.array(BG2, np.float32)
    if story["series"] == "shock" and not story["gain"]:
        top = np.array((44, 12, 20), np.float32)
    col = top * (1 - y) + bot * y
    img = np.repeat(col[:, None, :], WD, axis=1)
    xx = np.linspace(-1, 1, WD, dtype=np.float32)[None, :]
    yy = np.linspace(-1, 1, HT, dtype=np.float32)[:, None]
    vig = 1 - 0.35 * np.clip(xx ** 2 * 0.8 + yy ** 2 * 0.6, 0, 1)
    img = (img * vig[..., None]).clip(0, 255).astype(np.uint8)
    return Image.fromarray(img, "RGB")


def headline_image(segs_lines):
    tmp = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    size = 96
    while size > 52:
        f = font("anton", size)
        if all(text_w(tmp, "".join(s for s, _ in line), f) <= 930 for line in segs_lines):
            break
        size -= 4
    f = font("anton", size)
    lh = int(size * 1.08)
    im = Image.new("RGBA", (WD, lh * len(segs_lines) + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for k, line in enumerate(segs_lines):
        w = text_w(d, "".join(s for s, _ in line), f)
        x = (WD - w) / 2
        for s, c in line:
            d.text((x, k * lh), s, font=f, fill=c, stroke_width=3, stroke_fill=(0, 0, 0))
            x += text_w(d, s, f)
    return im


class Scene:
    def __init__(self, story, script, timing):
        self.s, self.sc, self.tm = story, script, timing
        self.kind = story["series"]
        self.bg = self.static_bg()
        self.head = headline_image(story["headline"])
        self.caps = caption_chunks(timing["lines"])
        self.n = len(story["months"])
        self.ymax = self.ymin = None
        self.tiles = {sym: logo_tile(sym, 72) for sym in story["tickers"]}
        self.big_tiles = {sym: logo_tile(sym, 64) for sym in story["tickers"]}
        rng = random.Random(3)
        self.parts = [(rng.uniform(120, 960), rng.uniform(560, 660), rng.uniform(-260, 260), rng.uniform(-900, -350),
                       rng.choice([GREEN, GOLD, WHITE, CYAN]), rng.uniform(8, 16)) for _ in range(110)]
        if self.n:
            self.cmax = [max(max(line[: i + 1]) for line in story["lines"]) for i in range(self.n)]
            self.cmin = [min(min(line[: i + 1]) for line in story["lines"]) for i in range(self.n)]
            if story["ghost"]:
                g = story["ghost"]
                gn = [1000 * v / g[0] for v in g]
                self.ghost = gn
                self.cmax = [max(a, max(gn[: i + 1])) for i, a in enumerate(self.cmax)]
                self.cmin = [min(a, min(gn[: i + 1])) for i, a in enumerate(self.cmin)]
            else:
                self.ghost = None
            self.grads = {}
        self.events = story["events"]

    # ---- static layer ---------------------------------------------------------------------------------
    def static_bg(self):
        s = self.s
        img = gradient_bg(s)
        d = ImageDraw.Draw(img)
        for x in range(0, WD, 90):
            d.line([(x, 0), (x, HT)], fill=mix(BG2, GRID, 0.35), width=1)
        for y in range(0, HT, 90):
            d.line([(0, y), (WD, y)], fill=mix(BG2, GRID, 0.35), width=1)
        mark = brand_mark(40)
        img.paste(mark, (70, BRAND_Y), mark)
        d.text((122, BRAND_Y + 3), CHANNEL, font=font("barlow", 32), fill=(214, 222, 236))
        num = sum(1 for v in STATE["videos"] if v.get("series") == s["series"]) + 1
        tag = f"{SERIES_INFO[s['series']][0]} #{num}"
        col = {"time_machine": BLUE, "peak": RED, "battle": (124, 58, 237), "shock": RED}[s["series"]]
        pill(d, 900, BRAND_Y - 2, tag, font("barlow", 28), WHITE, col, pad=(16, 6), anchor="r")
        if self.kind != "shock":
            d.line([(CX0, CY1), (CX1, CY1)], fill=mix(BG2, MUTED, 0.45), width=2)
            months = s["months"]
            n = len(months)
            f = font("barlowm", 26)
            for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
                i = round(frac * (n - 1))
                lab = "NOW" if frac == 1.0 else months[i][:4]
                x = CX0 + frac * (CX1 - CX0)
                w = text_w(d, lab, f)
                d.text((min(max(CX0, x - w / 2), CX1 - w), CY1 + 8), lab, font=f, fill=MUTED)
            note = ("ADJ. FOR SPLITS & DIVIDENDS" if s.get("div") else "PRICE ONLY") + \
                   " · HYPOTHETICAL · NOT FINANCIAL ADVICE"
            d.text((CX0, CY1 + 40), note, font=font("barlowm", 21), fill=DIM)
        else:
            d.text((CX0, 1290), "MARKET VALUE = SHARES OUTSTANDING × PRICE · NOT FINANCIAL ADVICE",
                   font=font("barlowm", 21), fill=DIM)
        return img

    # ---- helpers ---------------------------------------------------------------------------------------
    def f_at(self, t):
        return progress(self.tm["anchors"], t)

    def X(self, i):
        return CX0 + (i / max(1, self.n - 1)) * (CX1 - CX0)

    def Y(self, v):
        return CY1 - 6 - (v - self.ymin) / max(1e-6, self.ymax - self.ymin) * (CY1 - CY0 - 12)

    def scale_to(self, x):
        i = min(self.n - 1, int(math.ceil(x)))
        hi = self.cmax[i] * 1.14
        lo = max(0.0, min(self.cmin[i], 1000) * 0.86)
        if self.ymax is None:
            self.ymax, self.ymin = hi, lo
            return
        self.ymax += (hi - self.ymax) * (0.35 if hi > self.ymax else 0.08)
        self.ymin += (lo - self.ymin) * (0.35 if lo < self.ymin else 0.08)
        vals = [interp(line, x) for line in self.s["lines"]] + ([interp(self.ghost, x)] if self.ghost else [])
        span = self.ymax - self.ymin
        if max(vals) > self.ymax - 0.03 * span:            # the line always stays inside the box
            self.ymax = max(vals) + 0.05 * span
        if min(vals) < self.ymin + 0.03 * span:
            self.ymin = max(0.0, min(vals) - 0.05 * span)

    def grad(self, col):
        if col not in self.grads:
            h = CY1 - CY0
            a = (np.linspace(120, 0, h, dtype=np.float32) ** 1.0).astype(np.uint8)
            alpha = Image.fromarray(np.repeat(a[:, None], CX1 - CX0 + 2, axis=1), "L")
            self.grads[col] = (Image.new("RGB", alpha.size, col), alpha)
        return self.grads[col]

    # ---- frame -----------------------------------------------------------------------------------------
    def frame(self, t):
        img = self.bg.copy()
        d = ImageDraw.Draw(img)
        self.draw_head(img, t)
        if self.kind == "shock":
            self.draw_shock(img, d, t)
        else:
            x = self.f_at(t) * (self.n - 1)
            self.scale_to(x)
            if self.kind == "battle":
                self.draw_battle_cards(img, d, t, x)
            else:
                self.draw_single_top(img, d, t, x)
            self.draw_chart(img, d, t, x)
        self.draw_captions(d, t)
        self.draw_cta(d, t)
        return self.effects(img, t)

    def draw_head(self, img, t):
        img.paste(self.head, (0, HEAD_Y), self.head)

    def draw_single_top(self, img, d, t, x):
        s = self.s
        sym = s["tickers"][0]
        tile = self.tiles[sym]
        img.paste(tile, (70, ROW_Y - 8), tile)
        box = pill(d, 160, ROW_Y + 4, sym, font("barlow", 36), WHITE, (36, 56, 98), pad=(14, 4))
        sub = {"ago": "", "crash": " · COVID CRASH", "ipo": " · IPO MONTH", "peak": " · ALL-TIME HIGH"}[s["mode"]]
        d.text((box[2] + 16, ROW_Y + 10), f"BOUGHT {month_label(s['months'][0]).upper()}{sub}", font=font("barlow", 36),
               fill=RED if s["mode"] == "peak" else MUTED)
        v = interp(s["lines"][0], x)
        col = GREEN if v > 1000.5 else RED if v < 999.5 else WHITE
        tr = self.tm["t_reveal"]
        size = 168
        if tr and t >= tr:
            size = int(168 * (1 + 0.16 * (1 - ease_out((t - tr) / 0.35))))
            col = GREEN if s["gain"] else RED
        f = font("anton", size)
        d.text((70, COUNTER_Y + (168 - size) * 0.6), money(v), font=f, fill=col, stroke_width=2, stroke_fill=(0, 0, 0))
        m = v / 1000
        cx = 70
        if m >= 1.25 or m <= 0.9:
            box = pill(d, cx, CHIP_Y, mult_chip(m), font("anton", 46), (10, 10, 10), GOLD if m >= 1 else RED,
                       pad=(18, 4))
            cx = box[2] + 14
        ym = s["months"][min(self.n - 1, int(round(x)))]
        tk = self.tm.get("t_kicker")
        if tk and t >= tk and self.ghost:
            pill(d, cx, CHIP_Y, f"S&P 500: {money(self.ghost[-1])}", font("anton", 46), WHITE, (52, 64, 92),
                 pad=(18, 4))
        else:
            lab = "TODAY" if (tr and t >= tr) else month_label(ym).upper()
            pill(d, cx, CHIP_Y, lab, font("anton", 46), WHITE, CARD, pad=(18, 4), outline=(46, 66, 104))

    def draw_battle_cards(self, img, d, t, x):
        s = self.s
        tr = self.tm["t_reveal"]
        done = bool(tr and t >= tr)
        vals = [interp(line, x) for line in s["lines"]]
        lead = None if abs(vals[0] / vals[1] - 1) < 0.01 else (0 if vals[0] > vals[1] else 1)
        top = ROW_Y + 22
        for k, (sym, col) in enumerate(zip(s["tickers"], (CYAN, ORANGE))):
            x0 = 70 if k == 0 else 495
            box = [x0, top, x0 + 405, top + 230]
            win = done and sym == s["winner"]
            hot = (k == lead) if not done else win
            d.rounded_rectangle(box, radius=26, fill=CARD, outline=col if hot else mix(CARD, col, 0.35),
                                width=6 if hot else 3)
            tile = self.big_tiles[sym]
            img.paste(tile, (x0 + 18, top + 26), tile)
            nm = screen_name(sym)
            fz = 40
            while text_w(d, nm, font("barlow", fz)) > 285 and fz > 24:
                fz -= 2
            d.text((x0 + 94, top + 38), nm, font=font("barlow", fz), fill=WHITE)
            size = 92
            if win:
                size = int(92 * (1 + 0.16 * (1 - ease_out((t - tr) / 0.35))))
            txt = money(vals[k])
            while text_w(d, txt, font("anton", size)) > 370 and size > 50:
                size -= 4
            d.text((x0 + 20, top + 96 + (92 - size) * 0.9), txt, font=font("anton", size), fill=col)
            if hot and not done:
                self.crown(d, x0 + 360, top - 34)
            if win:
                pill(d, x0 + 202, top - 30, "WINNER", font("anton", 36), (10, 10, 10), GOLD, pad=(20, 2), anchor="c")
        ym = s["months"][min(self.n - 1, int(round(x)))]
        lab = "TODAY" if done else month_label(ym).upper()
        pill(d, 70, top + 250, lab, font("anton", 40), WHITE, CARD, pad=(16, 3), outline=(46, 66, 104))

    def crown(self, d, x, y):
        pts = [(x - 26, y + 26), (x - 30, y), (x - 13, y + 12), (x, y - 6), (x + 13, y + 12), (x + 30, y), (x + 26, y + 26)]
        d.polygon(pts, fill=GOLD)
        d.rectangle([x - 26, y + 24, x + 26, y + 32], fill=GOLD)

    def draw_chart(self, img, d, t, x):
        s = self.s
        # grid + y labels
        span = self.ymax - self.ymin
        step = 10 ** math.floor(math.log10(max(span / 3, 1e-6)))
        for mlt in (1, 2, 5, 10):
            if span / (step * mlt) <= 4:
                step *= mlt
                break
        f = font("barlowm", 24)
        yb = self.Y(1000)
        v = math.ceil(self.ymin / step) * step
        while v < self.ymax:
            y = self.Y(v)
            if CY0 + 10 < y < CY1 - 14:
                d.line([(CX0, y), (CX1, y)], fill=mix(BG2, GRID, 0.9), width=1)
                if abs(y - yb) > 34:
                    d.text((CX0 + 6, y - 28), short_money(v), font=f, fill=DIM)
            v += step
        # $1,000 baseline
        if CY0 < yb < CY1:
            for xx in range(CX0, CX1, 26):
                d.line([(xx, yb), (min(xx + 13, CX1), yb)], fill=(170, 180, 200), width=2)
            below = s["gain"] and yb + 34 < CY1
            if x > 0.15 * (self.n - 1):                    # the line itself starts on top of the label
                d.text((CX0 + 6, yb + 4 if below else yb - 30), "$1,000", font=f, fill=(190, 198, 215))
        upto = int(x)
        # ghost S&P line
        if self.ghost:
            gp = [(self.X(i), self.Y(self.ghost[i])) for i in range(upto + 1)] + [(self.X(x), self.Y(interp(self.ghost, x)))]
            if len(gp) >= 2:
                d.line(gp, fill=SPY_C, width=4, joint="curve")
                hx, hy = gp[-1]
                lab = "S&P 500"
                lw = text_w(d, lab, f)
                if x > 0.12 * (self.n - 1):
                    d.text((min(hx + 10, CX1 - lw), hy + 8), lab, font=f, fill=SPY_C)
        # main line(s): fill, glow, line, head
        for line, col in zip(s["lines"], s["colors"]):
            pts = [(self.X(i), self.Y(line[i])) for i in range(upto + 1)] + [(self.X(x), self.Y(interp(line, x)))]
            if len(pts) < 2:
                continue
            if len(s["lines"]) == 1:
                rgb, alpha = self.grad(col)
                mask = Image.new("L", alpha.size, 0)
                md = ImageDraw.Draw(mask)
                md.polygon([(px - CX0, py - CY0) for px, py in pts] + [(pts[-1][0] - CX0, CY1 - CY0),
                                                                       (0, CY1 - CY0)], fill=255)
                img.paste(rgb, (CX0, CY0), ImageChops.multiply(alpha, mask))
            gw, gh = (CX1 - CX0 + 60) // 2, (CY1 - CY0 + 60) // 2
            glow = Image.new("L", (gw, gh), 0)
            ImageDraw.Draw(glow).line([((px - CX0 + 30) / 2, (py - CY0 + 30) / 2) for px, py in pts],
                                      fill=200, width=9, joint="curve")
            glow = glow.filter(ImageFilter.GaussianBlur(7)).resize((gw * 2, gh * 2), Image.BILINEAR)
            img.paste(Image.new("RGB", glow.size, col), (CX0 - 30, CY0 - 30), glow)
            d.line(pts, fill=col, width=8, joint="curve")
            d.line(pts, fill=mix(col, WHITE, 0.55), width=2, joint="curve")
            hx, hy = pts[-1]
            ph = (t * 1.6) % 1.0
            r = 12 + 22 * ph
            d.ellipse([hx - r, hy - r, hx + r, hy + r], outline=mix(col, BG1, ph), width=3)
            d.ellipse([hx - 11, hy - 11, hx + 11, hy + 11], fill=WHITE, outline=col, width=4)
        # event markers + callouts
        for e, et in zip(self.events, self.tm["event_times"]):
            if t < et["t"]:
                continue
            line = s["lines"][0] if s["series"] != "battle" else s["lines"][0 if e["leader"] == s["tickers"][0] else 1]
            ex, ey = self.X(e["i"]), self.Y(line[e["i"]])
            d.ellipse([ex - 8, ey - 8, ex + 8, ey + 8], fill=e["color"], outline=WHITE, width=2)
            age = t - et["t"]
            if s["series"] == "battle":                 # the callout only while that side really leads
                cur = [interp(ln, x) for ln in s["lines"]]
                if (cur[0] >= cur[1]) != (e["leader"] == s["tickers"][0]):
                    age = 99
            if age < 2.3:
                pop = 1 + 0.25 * (1 - ease_out(age / 0.18))
                fz = int(44 * pop)
                txt = e["label"] if s["series"] != "battle" else \
                    f"{screen_name(e['leader']) if len(screen_name(e['leader'])) <= 10 else e['leader']} {e['label']}"
                fe = font("anton", fz)
                w = text_w(d, txt, fe) + 36
                bx = min(max(CX0, ex - w / 2), CX1 - w)
                below = e["kind"] in ("drawdown", "half", "bottom")
                by = ey + 22 if below else ey - fz - 40
                by = min(max(CY0 - 10, by), CY1 - fz - 30)
                d.rounded_rectangle([bx, by, bx + w, by + fz + 18], radius=14, fill=e["color"])
                d.text((bx + 18, by + 4), txt, font=fe, fill=(10, 10, 10) if e["color"] in (GOLD, CYAN, ORANGE)
                       else WHITE)

    def draw_shock(self, img, d, t):
        s = self.s
        sym = s["tickers"][0]
        tile = self.tiles[sym]
        img.paste(tile, (70, ROW_Y - 8), tile)
        box = pill(d, 160, ROW_Y + 4, sym, font("barlow", 36), WHITE, (36, 56, 98), pad=(14, 4))
        d.text((box[2] + 16, ROW_Y + 10), "MARKET VALUE · ONE DAY", font=font("barlow", 36), fill=MUTED)
        tc = self.tm["t_count"]
        v = s["delta"] * shock_value(t, tc)
        col = RED if v < 0 else GREEN
        txt = ("–" if v < 0 else "+") + short_money(abs(v))
        d.text((70, COUNTER_Y - 10), txt, font=font("anton", 190), fill=col, stroke_width=2, stroke_fill=(0, 0, 0))
        box = pill(d, 70, CHIP_Y + 18, f"{'–' if s['pct'] < 0 else '+'}{abs(s['pct']):.1f}% TODAY",
                   font("anton", 46), WHITE, col, pad=(18, 4))
        pill(d, box[2] + 14, CHIP_Y + 18, money2(s["price"]), font("anton", 46), WHITE, CARD, pad=(18, 4),
             outline=(46, 66, 104))
        st = self.tm["starts"]
        tcmp = st.get("compare")
        if s.get("comp") and tcmp is not None and t >= tcmp:
            k = ease_out((t - tcmp) / 0.7)
            a, b = abs(s["delta"]), s["comp"]["mcap"]
            mx = max(a, b)
            rows = [(f"{sym} {'LOST' if s['delta'] < 0 else 'ADDED'} TODAY", a, col),
                    (f"ALL OF {name_of(s['comp']['sym']).upper()}", b, BLUE)]
            for j, (lab, val, c) in enumerate(rows):
                y = 880 + j * 138
                d.text((70, y), lab, font=font("barlow", 36), fill=WHITE)
                wbar = int(640 * (val / mx) * k)
                d.rounded_rectangle([70, y + 46, 70 + max(wbar, 8), y + 104], radius=12, fill=c)
                d.text((70 + max(wbar, 8) + 14, y + 44), short_money(val), font=font("anton", 52), fill=WHITE)
        tp = st.get("person")
        if tp is not None and t >= tp:
            pop = 1 + 0.2 * (1 - ease_out((t - tp) / 0.2))
            pill(d, 70, 1166, f"≈ {money(abs(s['delta']) / US_POP)} PER AMERICAN", font("anton", int(50 * pop)),
                 (10, 10, 10), GOLD, pad=(22, 6))

    def draw_captions(self, d, t):
        for c in self.caps:
            if c["t0"] <= t < c["t1"]:
                words = [w[0].upper() for w in c["words"]]
                size = 84
                while text_w(d, " ".join(words), font("anton", size), 7) > CAP_W and size > 52:
                    size -= 4
                fc = font("anton", size)
                pop = t - c["t0"] < 0.08
                if pop:
                    fc = font("anton", size + 6)
                total = text_w(d, " ".join(words), fc, 7)
                x = CAP_X - total / 2
                bb = d.textbbox((0, 0), "HG0$", font=fc)
                y = CAP_Y - (bb[1] + bb[3]) / 2
                for k, w in enumerate(c["words"]):
                    nxt = c["words"][k + 1][1] if k + 1 < len(c["words"]) else c["t1"]
                    active = w[1] <= t < nxt
                    txt = words[k]
                    d.text((x, y), txt, font=fc, fill=GOLD if active else WHITE, stroke_width=7, stroke_fill=(0, 0, 0))
                    x += text_w(d, txt + " ", fc, 0)
                break

    def draw_cta(self, d, t):
        tc = self.tm["voice_end"] + 0.35
        if t < tc:
            return
        pop = 1 + 0.18 * (1 - ease_out((t - tc) / 0.25))
        f = font("anton", int(60 * pop))
        asc, desc = f.getmetrics()
        box = pill(d, CAP_X, CAP_Y - (asc + desc + 16) / 2, "COMMENT A STOCK", f, WHITE, BLUE, pad=(30, 8),
                   anchor="c")
        ax = (box[0] + box[2]) / 2
        ay = box[3] + 14
        d.polygon([(ax - 26, ay), (ax + 26, ay), (ax, ay + 28)], fill=BLUE)

    def effects(self, img, t):
        tr = self.tm.get("t_reveal")
        if not tr or t < tr:
            return img
        age = t - tr
        if age < 0.3:
            img = Image.blend(img, Image.new("RGB", img.size, WHITE), 0.45 * (1 - age / 0.3))
        if self.s["gain"] and age < 2.4 and self.kind != "shock":
            d = ImageDraw.Draw(img)
            g = 1500
            for x0, y0, vx, vy, c, sz in self.parts:
                px, py = x0 + vx * age, y0 + vy * age + 0.5 * g * age * age
                if 0 < py < HT:
                    d.rectangle([px, py, px + sz, py + sz * 0.6], fill=c)
        if not self.s["gain"] and age < 0.45:
            dx = int(10 * math.sin(age * 90) * (1 - age / 0.45))
            img = ImageChops.offset(img, dx, 0)
        return img


def render_video(story, script, timing, audio, out):
    scene = Scene(story, script, timing)
    T = timing["T"]
    nfr = int(T * FPS)
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{WD}x{HT}", "-r", str(FPS),
           "-i", "-", "-i", str(audio), "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags",
           "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0 = time.time()
    for k in range(nfr):
        proc.stdin.write(scene.frame(k / FPS).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg failed")
    print(f"render: {nfr} frames in {time.time() - t0:.1f}s -> {out}")
    return scene


# =========================================================================================================
# YouTube
# =========================================================================================================
def youtube():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=Credentials(
        None, refresh_token=os.environ["YT_REFRESH_TOKEN"], token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"]))


def description(story, script):
    f, s = story["facts"], story["series"]
    q = script.get("question", "")
    body = "\n".join(script["lines"])
    if s == "shock":
        how = (f"How we calculated it: change in market value = shares outstanding × today's price change "
               f"({f['date']}). Data: Finnhub. Per-American figure uses a US population of about 340 million.")
        tags = f"#shorts #stocks #stockmarket #{story['tickers'][0].replace('-', '')}"
    else:
        names = " vs ".join(f"{n} ({t})" for n, t in zip(story["names"], story["tickers"]))
        how = (f"How we calculated it: a hypothetical $1,000 invested at the {f['start']} monthly close in "
               f"{names}, held to {f['as_of']}, "
               + ("dividends reinvested (adjusted prices)" if story["div"] else "price only, dividends not included")
               + f". No fees or taxes. Data: {story['src']}" + (", Finnhub" if env("FINNHUB_API_KEY") else "")
               + (". Benchmark: SPDR S&P 500 ETF (SPY)." if story.get("ghost") else "."))
        tags = "#shorts #stocks #investing " + " ".join("#" + t.replace("-", "") for t in story["tickers"])
    return (f"{q} 👇\n\n{body}\n\n{how}\nHypothetical illustration. Past performance does not guarantee future "
            f"results. Not financial advice.\n\n{tags}")[:4900]


def translate(title, question, story_text):
    if not LANGS:
        return {}
    tr = gemini(
        f"Translate this YouTube Short metadata about stocks into these languages: {', '.join(LANGS)} (ISO 639-1). "
        "Natural, catchy wording; keep company names, tickers, numbers and dollar amounts exact; title max 80 "
        f"characters; no hashtags.\nTITLE: {title}\nQUESTION: {question}\nSTORY:\n{story_text}\n"
        'Return JSON: {"<code>": {"title": "...", "question": "...", "story": "..."}, ...}',
        lambda d: isinstance(d, dict) and sum(isinstance(d.get(l), dict) and bool(d[l].get("title"))
                                              for l in LANGS) >= max(1, len(LANGS) // 2), rounds=1)
    return {l: v for l, v in (tr or {}).items() if l in LANGS and isinstance(v, dict) and v.get("title")}


def upload(yt, story, script, path):
    from googleapiclient.http import MediaFileUpload
    title = script["title"].strip()
    desc = description(story, script)
    tags = list(dict.fromkeys(["stocks", "investing", "stock market", "shorts"] + story["names"] + story["tickers"]
                              + [str(x) for x in script.get("tags", [])]))
    tags = [t for t in tags if len(t) < 30][:15]
    body = {"snippet": {"title": f"{title[:90]} #shorts", "description": desc, "tags": tags, "categoryId": "27",
                        "defaultLanguage": "en", "defaultAudioLanguage": "en"},
            "status": {"privacyStatus": env("PRIVACY", "public"), "selfDeclaredMadeForKids": False}}
    tail = desc.split("\n\n", 2)[-1]
    loc = {l: {"title": f"{str(v['title'])[:90]} #shorts",
               "description": (f"{v.get('question', '')} 👇\n\n{v.get('story', '')}\n\n{tail}")[:4900]}
           for l, v in translate(title, script.get("question", ""), "\n".join(script["lines"])).items()}
    if loc:
        body["localizations"] = loc
    send = lambda part: yt.videos().insert(part=part, body=body, media_body=MediaFileUpload(
        str(path), chunksize=-1, resumable=True)).execute()
    try:
        res = send("snippet,status" + (",localizations" if loc else ""))
    except Exception as e:
        if not loc or "uploadLimitExceeded" in str(e) or "quota" in str(e).lower():
            raise
        print("localizations rejected:", str(e)[:160])
        body.pop("localizations")
        res = send("snippet,status")
    STATE["channel_id"] = res.get("snippet", {}).get("channelId", STATE.get("channel_id"))
    print("uploaded:", res["id"])
    return res["id"]


def add_to_playlist(yt, vid, series):
    name = SERIES_INFO[series][1]
    try:
        items = yt.playlists().list(part="snippet", mine=True, maxResults=50).execute().get("items", [])
        pl = next((i["id"] for i in items if i["snippet"]["title"] == name), None) or yt.playlists().insert(
            part="snippet,status", body={"snippet": {"title": name, "description": f"{name} - Bull & Bear Daily"},
                                         "status": {"privacyStatus": "public"}}).execute()["id"]
        yt.playlistItems().insert(part="snippet", body={"snippet": {
            "playlistId": pl, "resourceId": {"kind": "youtube#video", "videoId": vid}}}).execute()
    except Exception as e:
        print("playlist skipped:", str(e)[:160])


def post_comment(yt, vid, script):
    q = script.get("question", "").strip()
    try:
        yt.commentThreads().insert(part="snippet", body={"snippet": {"videoId": vid, "topLevelComment": {
            "snippet": {"textOriginal": f"{q} 👇\nComment a stock and we'll run the numbers next."}}}}).execute()
    except Exception as e:
        print("comment skipped:", str(e)[:160])


# =========================================================================================================
# main
# =========================================================================================================
def make(story, hook):
    script = write_script(story, hook)
    print(json.dumps({"hook": hook, "lines": script["lines"], "title": script["title"]}, ensure_ascii=False))
    voice = make_voice(script["lines"], script["beats"]) if env("NARRATION", "1") == "1" else None
    if voice is None:
        if env("NARRATION", "1") == "1":
            gh_note("warning", "Voice", "edge-tts failed: this video has no voice-over")
        voice = silent_voice(script["lines"], script["beats"])
    timing = make_timing(story, voice, script["beats"])
    audio = make_audio(story, timing, voice)
    out = WORK / "final.mp4"
    render_video(story, script, timing, audio, out)
    return script, out


def main():
    ensure_fonts()
    yt = None
    req = Counter()
    if not DRY:
        yt = youtube()
        if LEARN:
            update_views(yt)
        req = comment_requests(yt)
    story = choose_story(req)
    gh_note("notice", "Story", f"{story['series']} | {story['key']} | prices: {story.get('src')}")
    if PROVIDER_ERR:
        gh_note("warning", "Price sources", " | ".join(PROVIDER_ERR.values()))
    if story["asked"]:
        hook = "asked"
    elif env("HOOK") in HOOK_STYLE:
        hook = env("HOOK")
    elif story["series"] == "shock":
        hook = "number"
    else:
        hook = pick(weights_for("hook", HOOKS, {h: 1.0 for h in HOOKS}))
    script, out = make(story, hook)
    meta = {"title": script["title"], "description": description(story, script), "series": story["series"],
            "key": story["key"], "hook": hook}
    save_json(WORK / "metadata.json", meta)
    if DRY:
        print("dry run: video at", out)
        gh_note("notice", "Dry run", f"{script['title']} || " + " / ".join(script["lines"]))
        return
    vid = upload(yt, story, script, out)
    STATE["videos"].append({"id": vid, "series": story["series"], "hook": hook, "mode": story["mode"],
                            "key": story["key"], "tickers": story["tickers"], "date": NOW.isoformat()[:16],
                            "title": script["title"]})
    if story["asked"]:
        STATE["requests_done"][story["tickers"][0]] = TODAY
    save_state()
    add_to_playlist(yt, vid, story["series"])
    post_comment(yt, vid, script)
    save_state()
    gh_note("notice", "Uploaded", f"https://youtube.com/shorts/{vid} | {script['title']} | "
            f"{time.time() - START:.0f}s")


if __name__ == "__main__":
    main()
