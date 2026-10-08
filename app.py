"""
StoreGuard
----------
A Streamlit app for tracking stored grain and produce condition, scoring spoilage risk,
prioritizing inspection/sale actions, tracking losses, and generating weekly PDF reports.

Important:
- All code is intentionally kept in this single app.py file.
- Google Gemini is optional. If GEMINI_API_KEY is available, the app uses gemini-2.0-flash.
- If no API key is available, the app still runs fully using a local fallback engine.
- Demo data is loaded automatically on first run.
- A light live simulation is enabled by default on the Dashboard page.
"""

import os
import json
import re
import time
import math
import random
import hashlib
import sqlite3
import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from fpdf import FPDF


# ----------------------------------------------------------------------------
# Page configuration
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="StoreGuard",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------
DB_PATH = "storeguard.db"
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

MENU = [
    "Dashboard",
    "Units",
    "Stocks",
    "Readings",
    "Limits",
    "Photos",
    "Risk & Forecast",
    "Priority",
    "Losses",
    "Alerts",
    "Reports",
    "Demo Data",
]

LANG_DISPLAY_TO_CODE = {
    "English": "en",
    "اردو": "ur",
    "हिन्दी": "hi",
}
LANG_CODE_TO_NAME = {
    "en": "English",
    "ur": "Urdu",
    "hi": "Hindi",
}

# Generic safe limits. These are intentionally conservative and labelled for local verification.
LIMIT_SEED = [
    ("wheat", 12.5, 30.0, 70.0, "Generic – verify locally"),
    ("rice", 13.0, 30.0, 70.0, "Generic – verify locally"),
    ("maize", 13.5, 30.0, 70.0, "Generic – verify locally"),
    ("sorghum", 12.0, 30.0, 70.0, "Generic – verify locally"),
    ("millet", 12.0, 30.0, 70.0, "Generic – verify locally"),
    ("barley", 13.0, 30.0, 70.0, "Generic – verify locally"),
    ("oats", 12.0, 30.0, 70.0, "Generic – verify locally"),
    ("pulses", 12.0, 30.0, 70.0, "Generic – verify locally"),
    ("gram", 12.0, 30.0, 70.0, "Generic – verify locally"),
    ("lentil", 12.0, 30.0, 70.0, "Generic – verify locally"),
    ("potato", 75.0, 10.0, 90.0, "Generic – verify locally"),
    ("onion", 70.0, 15.0, 75.0, "Generic – verify locally"),
    ("tomato", 90.0, 12.0, 90.0, "Generic – verify locally"),
]

# ----------------------------------------------------------------------------
# Translation dictionary for AI-written / risk-explanation text
# ----------------------------------------------------------------------------
T = {
    "en": {
        "action_header": "AI action guidance",
        "risk_level": "Risk level",
        "low": "Low",
        "medium": "Medium",
        "high": "High",
        "critical": "Critical",
        "why": "Why this score",
        "next_steps": "Next steps",
        "moisture_high": "Moisture {value}% is above the safe limit {limit}%.",
        "temp_high": "Temperature {value}°C is above the safe limit {limit}°C.",
        "humidity_high": "Relative humidity {value}% is above the safe limit {limit}%.",
        "storage_long": "Stock has been stored {days} days; expected sale in {days_to} days.",
        "overdue": "Expected sale date has passed by {days} days.",
        "insects": "Photo check reports insects.",
        "mold": "Photo check reports mold signs.",
        "discoloration": "Photo check reports discoloration.",
        "damaged": "Estimated damaged grain: {percent}%.",
        "step_dry": "Dry or aerate the affected lot; separate wetter grain from drier grain.",
        "step_ventilate_turn": "Ventilate during cool, dry conditions and turn/reduce the pile if safe to do so.",
        "step_humidity": "Improve airflow or dehumidify the storage space.",
        "step_inspect_clean": "Inspect closely, remove infested material, clean surroundings, and isolate the lot.",
        "step_licensed_fumigation": "If insects or mold are confirmed, contact a licensed operator for fumigation/treatment. Do not apply chemicals yourself.",
        "step_sell_first": "Sell or move this stock first because risk is high or sale is due.",
        "step_inspect_today": "Inspect today and re-check readings after corrective action.",
        "step_monitor": "Keep monitoring; no urgent action beyond routine inspection.",
        "step_no_chemical_doses": "Never use chemical dose advice from this app; follow local regulations and expert supervision.",
        "sell_first": "Sell first",
        "inspect_today": "Inspect today",
        "stable": "Stable",
        "alert_high_risk": "High/Critical spoilage risk detected.",
        "alert_moisture_trend": "Moisture trend is approaching the safe limit.",
        "alert_temp_trend": "Temperature trend is approaching the safe limit.",
        "alert_sale_due": "Expected sale date is near.",
        "photo_notes_fallback": "Fallback visual assessment: {flags}. Confidence {conf}%. This is not a laboratory test.",
        "photo_flag_insects": "insects likely",
        "photo_flag_mold": "mold likely",
        "photo_flag_discoloration": "discoloration likely",
        "photo_flag_clean": "no obvious defects detected",
    },
    "ur": {
        "action_header": "AI اقدام کی رہنمائی",
        "risk_level": "خطرے کی سطح",
        "low": "کم",
        "medium": "درمیانہ",
        "high": "زیادہ",
        "critical": "انتہائی",
        "why": "یہ اسکور کیوں",
        "next_steps": "اگلے اقدامات",
        "moisture_high": "نمی {value}% محفوظ حد {limit}% سے اوپر ہے۔",
        "temp_high": "درجہ حرارت {value}°C محفوظ حد {limit}°C سے اوپر ہے۔",
        "humidity_high": "نسبی نمی {value}% محفوظ حد {limit}% سے اوپر ہے۔",
        "storage_long": "اسٹاک {days} دن سے ذخیرہ شدہ ہے؛ توقع کی فروخت {days_to} دن میں۔",
        "overdue": "توقع کی فروخت کی تاریخ {days} دن گزر چکی ہے۔",
        "insects": "فوٹو جانچ میں کیڑے نظر آئے۔",
        "mold": "فوٹو جانچ میں پھپھوندی کے نشانات۔",
        "discoloration": "فوٹو جانچ میں رنگت تبدیل۔",
        "damaged": "تخمینی خراب اناج: {percent}%۔",
        "step_dry": "متاثرہ لاٹ کو خشک یا ہوا دیں؛ گیلے اناج کو سوکھے سے الگ کریں۔",
        "step_ventilate_turn": "ٹھنڈے اور خشک موسم میں ہوا دینا اور اگر محفوظ ہو تو ڈھیر پلٹیں/کم کریں۔",
        "step_humidity": "ہوا کی روانی بہتر کریں یا اسٹوریج جگہ کی نمی کم کریں۔",
        "step_inspect_clean": "قریب سے معائنہ کریں، متاثرہ مال ہٹائیں، اردگرد صاف کریں، اور لاٹ الگ کریں۔",
        "step_licensed_fumigation": "اگر کیڑے یا پھپھوندی کی تصدیق ہو تو فومیگیشن کے لیے لائسنس یافتہ آپریٹر سے رابطہ کریں۔ خود کیمیکل استعمال نہ کریں۔",
        "step_sell_first": "یہ اسٹاک پہلے بیچیں یا منتقل کریں کیونکہ خطرہ زیادہ ہے یا فروخت کی تاریخ قریب ہے۔",
        "step_inspect_today": "آج معائنہ کریں اور اصلاح کے بعد دوبارہ ریڈنگ چیک کریں۔",
        "step_monitor": "نگرانی جاری رکھیں؛ معمول کے معائنے کے سوا کوئی فوری اقدام نہیں۔",
        "step_no_chemical_doses": "اس ایپ سے کیمیائی خوراک کا مشورہ ہرگز استعمال نہ کریں؛ مقامی قوانین اور ماہر کی نگرانی فالو کریں۔",
        "sell_first": "پہلے بیچیں",
        "inspect_today": "آج معائنہ کریں",
        "stable": "مستحکم",
        "alert_high_risk": "زیادہ/انتہائی خرابی کا خطرہ پایا گیا۔",
        "alert_moisture_trend": "نمی کا رجحان محفوظ حد کے قریب جا رہا ہے۔",
        "alert_temp_trend": "درجہ حرارت کا رجحان محفوظ حد کے قریب جا رہا ہے۔",
        "alert_sale_due": "توقع کی فروخت کی تاریخ قریب ہے۔",
        "photo_notes_fallback": "فرض بصری جانچ: {flags}۔ اعتماد {conf}٪۔ یہ لیبارٹری ٹیسٹ نہیں ہے۔",
        "photo_flag_insects": "کیڑے ممکنہ",
        "photo_flag_mold": "پھپھوندی ممکنہ",
        "photo_flag_discoloration": "رنگت تبدیل ممکنہ",
        "photo_flag_clean": "کوئی واضح نقص نہیں دیکھا گیا",
    },
    "hi": {
        "action_header": "AI कार्रवाई मार्गदर्शन",
        "risk_level": "जोखिम स्तर",
        "low": "कम",
        "medium": "मध्यम",
        "high": "उच्च",
        "critical": "गंभीर",
        "why": "यह स्कोर क्यों",
        "next_steps": "अगले कदम",
        "moisture_high": "नमी {value}% सुरक्षित सीमा {limit}% से ऊपर है।",
        "temp_high": "तापमान {value}°C सुरक्षित सीमा {limit}°C से ऊपर है।",
        "humidity_high": "सापेक्ष आर्द्रता {value}% सुरक्षित सीमा {limit}% से ऊपर है।",
        "storage_long": "स्टॉक {days} दिनों से भंडारित है; अपेक्षित बिक्री {days_to} दिनों में।",
        "overdue": "अपेक्षित बिक्री की तिथि {days} दिन बीत चुकी है।",
        "insects": "फोटो जांच में कीड़े दिखाई दिए।",
        "mold": "फोटो जांच में फफूंद के संकेत।",
        "discoloration": "फोटो जांच में रंग परिवर्तन।",
        "damaged": "अनुमानित क्षतिग्रस्त अनाज: {percent}%।",
        "step_dry": "प्रभावित लॉट को सुखाएं या हवा दें; गीले अनाज को सूखे से अलग करें।",
        "step_ventilate_turn": "ठंडी और सूखी स्थिति में हवा दें और सुरक्षित हो तो ढेर पलटें/कम करें।",
        "step_humidity": "हवा का प्रवाह बेहतर करें या भंडारण स्थान की नमी कम करें।",
        "step_inspect_clean": "बारीकी से निरीक्षण करें, प्रभावित सामग्री हटाएं, आसपास साफ करें और लॉट अलग करें।",
        "step_licensed_fumigation": "यदि कीड़े या फफूंद की पुष्टि हो तो फ्यूमिगेशन/उपचार के लिए लाइसेंस प्राप्त ऑपरेटर से संपर्क करें। स्वयं रसायन का उपयोग न करें।",
        "step_sell_first": "यह स्टॉक पहले बेचें या स्थानांतरित करें क्योंकि जोखिम अधिक है या बिक्री की तारीख निकट है।",
        "step_inspect_today": "आज निरीक्षण करें और सुधार के बाद फिर से रीडिंग जांचें।",
        "step_monitor": "निगरानी जारी रखें; नियमित निरीक्षण के अलावा कोई तत्काल कार्रवाई नहीं।",
        "step_no_chemical_doses": "इस ऐप से रासायनिक खुराक की सलाह कभी न उपयोग करें; स्थानीय नियमों और विशेषज्ञ की निगरानी का पालन करें।",
        "sell_first": "पहले बेचें",
        "inspect_today": "आज निरीक्षण करें",
        "stable": "स्थिर",
        "alert_high_risk": "उच्च/गंभीर खराबी जोखिम पाया गया।",
        "alert_moisture_trend": "नमी का रुझान सुरक्षित सीमा के करीब जा रहा है।",
        "alert_temp_trend": "तापमान का रुझान सुरक्षित सीमा के करीब जा रहा है।",
        "alert_sale_due": "अपेक्षित बिक्री की तारीख निकट है।",
        "photo_notes_fallback": "वैकल्पिक दृश्य जांच: {flags}। विश्वास {conf}٪। यह प्रयोगशाला परीक्षण नहीं है।",
        "photo_flag_insects": "कीड़े संभावित",
        "photo_flag_mold": "फफूंद संभावित",
        "photo_flag_discoloration": "रंग परिवर्तन संभावित",
        "photo_flag_clean": "कोई स्पष्ट दोष नहीं देखा गया",
    },
}

# ----------------------------------------------------------------------------
# UI styling
# ----------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 4rem;
    }
    .kpi-card {
        background: linear-gradient(135deg, #ffffff 0%, #f3f7ff 100%);
        border: 1px solid #e6eef8;
        border-radius: 16px;
        padding: 14px 16px;
        margin-bottom: 10px;
        box-shadow: 0 4px 14px rgba(15, 23, 42, 0.06);
        min-height: 92px;
    }
    .kpi-label {
        font-size: 0.85rem;
        color: #475569;
        margin-bottom: 4px;
    }
    .kpi-value {
        font-size: 1.55rem;
        font-weight: 800;
        color: #0f172a;
        line-height: 1.1;
    }
    .kpi-sub {
        font-size: 0.8rem;
        color: #64748b;
        margin-top: 4px;
    }
    .small-note {
        font-size: 0.85rem;
        color: #475569;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ----------------------------------------------------------------------------
# Small utilities
# ----------------------------------------------------------------------------
def tr(key: str, lang: Optional[str] = None, **kwargs: Any) -> str:
    """Translate a key into the selected language, with formatting support."""
    lang = lang or st.session_state.get("lang", "en")
    template = T.get(lang, T["en"]).get(key) or T["en"].get(key, key)
    try:
        return template.format(**kwargs)
    except Exception:
        return template


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert a value to float."""
    try:
        if value is None or value == "":
            return float(default)
        if pd.isna(value):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def parse_date(value: Any) -> Optional[dt.date]:
    """Parse a date-like value into datetime.date."""
    d = parse_dt(value)
    return d.date() if d else None


def parse_dt(value: Any) -> Optional[dt.datetime]:
    """Parse a date/datetime-like value into datetime.datetime."""
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return dt.datetime(value.year, value.month, value.day)

    s = str(value).strip()
    if not s:
        return None

    try:
        return dt.datetime.fromisoformat(s)
    except Exception:
        pass

    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y",
        "%d-%m-%Y",
    ):
        try:
            return dt.datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def score_to_level(score: float) -> str:
    """Convert numeric risk score to categorical level."""
    if score < 25:
        return "Low"
    if score < 50:
        return "Medium"
    if score < 75:
        return "High"
    return "Critical"


def kpi_card(label: str, value: str, sub: str = "", col: Any = None) -> None:
    """Render a compact KPI card."""
    html = f"""
    <div class="kpi-card">
      <div class="kpi-label">{label}</div>
      <div class="kpi-value">{value}</div>
      <div class="kpi-sub">{sub}</div>
    </div>
    """
    if col is None:
        st.markdown(html, unsafe_allow_html=True)
    else:
        col.markdown(html, unsafe_allow_html=True)


def pdf_safe(text: Any) -> str:
    """Make text safe for basic PDF fonts."""
    return str(text).encode("latin-1", "replace").decode("latin-1")


def get_api_key() -> Optional[str]:
    """Read Gemini API key from Streamlit secrets or environment. Never hardcode it."""
    try:
        key = st.secrets.get("GEMINI_API_KEY")  # type: ignore[attr-defined]
    except Exception:
        key = None
    if not key:
        key = os.environ.get("GEMINI_API_KEY")
    return key


def load_genai():
    """Lazy-load google-generativeai so the app still runs if package/import fails."""
    try:
        import google.generativeai as genai
        return genai
    except Exception:
        return None


# ----------------------------------------------------------------------------
# Database helpers
# ----------------------------------------------------------------------------
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create tables and seed default limits if needed."""
    conn = get_conn()
    c = conn.cursor()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS units (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            capacity_kg REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_id INTEGER NOT NULL,
            commodity TEXT NOT NULL,
            quantity_kg REAL DEFAULT 0,
            entry_date TEXT,
            expected_sale_date TEXT,
            value_per_kg REAL DEFAULT 0,
            FOREIGN KEY(unit_id) REFERENCES units(id)
        );

        CREATE TABLE IF NOT EXISTS limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            commodity TEXT UNIQUE NOT NULL,
            max_moisture_pct REAL,
            max_temp_c REAL,
            max_humidity_pct REAL,
            label TEXT
        );

        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id INTEGER NOT NULL,
            reading_date TEXT NOT NULL,
            temp_c REAL,
            rh_pct REAL,
            moisture_pct REAL,
            co2_ppm REAL,
            smell_notes TEXT,
            photo_path TEXT,
            FOREIGN KEY(stock_id) REFERENCES stocks(id)
        );

        CREATE TABLE IF NOT EXISTS photo_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reading_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            insects_visible INTEGER DEFAULT 0,
            mold_signs INTEGER DEFAULT 0,
            discoloration INTEGER DEFAULT 0,
            damaged_grain_estimate_percent REAL DEFAULT 0,
            confidence REAL DEFAULT 0,
            notes TEXT,
            source TEXT,
            FOREIGN KEY(reading_id) REFERENCES readings(id)
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            level TEXT,
            message TEXT,
            acknowledged INTEGER DEFAULT 0,
            FOREIGN KEY(stock_id) REFERENCES stocks(id)
        );

        CREATE TABLE IF NOT EXISTS losses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id INTEGER NOT NULL,
            event_date TEXT NOT NULL,
            kg_lost REAL DEFAULT 0,
            value_lost REAL DEFAULT 0,
            reason TEXT,
            prevented_kg REAL DEFAULT 0,
            prevented_value REAL DEFAULT 0,
            FOREIGN KEY(stock_id) REFERENCES stocks(id)
        );
        """
    )
    conn.commit()

    # Seed default limits if table is empty
    count = c.execute("SELECT COUNT(*) AS c FROM limits").fetchone()["c"]
    if count == 0:
        seed_limits(c)
    conn.commit()
    conn.close()


def seed_limits(cursor: sqlite3.Cursor) -> None:
    """Insert generic commodity limits."""
    cursor.executemany(
        """
        INSERT OR IGNORE INTO limits
        (commodity, max_moisture_pct, max_temp_c, max_humidity_pct, label)
        VALUES (?, ?, ?, ?, ?)
        """,
        LIMIT_SEED,
    )


def seed_demo_data(force: bool = False) -> None:
    """
    Load realistic demo data automatically.
    If force=True, clear existing operational data and reload demo data.
    """
    conn = get_conn()
    c = conn.cursor()

    unit_count = c.execute("SELECT COUNT(*) AS c FROM units").fetchone()["c"]
    if unit_count > 0 and not force:
        conn.close()
        return

    if force:
        # Clear child tables first
        c.execute("DELETE FROM photo_checks")
        c.execute("DELETE FROM alerts")
        c.execute("DELETE FROM losses")
        c.execute("DELETE FROM readings")
        c.execute("DELETE FROM stocks")
        c.execute("DELETE FROM units")
        c.execute("DELETE FROM limits")
        seed_limits(c)

    today = dt.date.today()
    now_iso = dt.datetime.now().isoformat()
    rng = random.Random(42)

    # Units
    units_data = [
        ("Godown A", "godown", 10000.0),
        ("Silo B", "silo", 20000.0),
        ("Hermetic Bags C", "hermetic bags", 5000.0),
        ("Cold Room D", "cold room", 8000.0),
    ]
    unit_ids: List[int] = []
    for name, typ, cap in units_data:
        c.execute(
            "INSERT INTO units (name, type, capacity_kg) VALUES (?, ?, ?)",
            (name, typ, cap),
        )
        unit_ids.append(c.lastrowid)

    # Stocks
    stocks_data = [
        (unit_ids[0], "Wheat", 5000.0, today - dt.timedelta(days=45), today + dt.timedelta(days=15), 35.0),
        (unit_ids[1], "Maize", 12000.0, today - dt.timedelta(days=20), today + dt.timedelta(days=60), 28.0),
        (unit_ids[2], "Rice", 2500.0, today - dt.timedelta(days=70), today + dt.timedelta(days=10), 42.0),
        (unit_ids[3], "Onion", 3000.0, today - dt.timedelta(days=12), today + dt.timedelta(days=30), 22.0),
    ]
    stock_ids: List[int] = []
    for unit_id, commodity, qty, entry, expected, val in stocks_data:
        c.execute(
            """
            INSERT INTO stocks
            (unit_id, commodity, quantity_kg, entry_date, expected_sale_date, value_per_kg)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (unit_id, commodity, qty, entry.isoformat(), expected.isoformat(), val),
        )
        stock_ids.append(c.lastrowid)

    # Readings: 14 points over roughly the last month
    last_reading_ids: Dict[int, int] = {}
    for idx, stock_id in enumerate(stock_ids, start=1):
        points = 14
        for i in range(points):
            reading_day = today - dt.timedelta(days=(points - 1 - i) * 2)

            if idx == 1:  # Wheat: deteriorating
                moisture = 11.5 + i * 0.16 + rng.uniform(-0.08, 0.08)
                temp = 27.0 + i * 0.55 + rng.uniform(-0.4, 0.4)
                rh = 62.0 + i * 1.2 + rng.uniform(-2.0, 2.0)
                smell = "clean" if i < 5 else ("slight musty" if i < 10 else "musty, warm")
                co2 = 450 + i * 18 + rng.uniform(-20, 20)
            elif idx == 2:  # Maize: stable
                moisture = 12.4 + math.sin(i / 2.0) * 0.12 + rng.uniform(-0.05, 0.05)
                temp = 25.5 + math.cos(i / 3.0) * 0.4 + rng.uniform(-0.2, 0.2)
                rh = 58.0 + rng.uniform(-2.0, 2.0)
                smell = "normal"
                co2 = 420 + rng.uniform(-15, 15)
            elif idx == 3:  # Rice: mostly stable, minor discoloration risk
                moisture = 12.3 - i * 0.02 + rng.uniform(-0.05, 0.05)
                temp = 22.5 + rng.uniform(-0.5, 0.5)
                rh = 50.0 + rng.uniform(-2.0, 2.0)
                smell = "clean"
                co2 = 400 + rng.uniform(-10, 10)
            else:  # Onion: cold room, humidity concern
                moisture = 67.0 + i * 0.08 + rng.uniform(-0.2, 0.2)
                temp = 3.8 + i * 0.04 + rng.uniform(-0.1, 0.1)
                rh = 76.0 + i * 0.25 + rng.uniform(-1.0, 1.0)
                smell = "mild onion odour"
                co2 = None

            c.execute(
                """
                INSERT INTO readings
                (stock_id, reading_date, temp_c, rh_pct, moisture_pct, co2_ppm, smell_notes, photo_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stock_id,
                    reading_day.isoformat(),
                    round(temp, 2),
                    round(rh, 2),
                    round(moisture, 2),
                    round(co2, 1) if co2 is not None else None,
                    smell,
                    "",
                ),
            )
            last_reading_ids[idx] = c.lastrowid

    # Photo checks for demo
    c.execute(
        """
        INSERT INTO photo_checks
        (reading_id, created_at, insects_visible, mold_signs, discoloration,
         damaged_grain_estimate_percent, confidence, notes, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            last_reading_ids[1],
            now_iso,
            1,
            1,
            1,
            14.5,
            0.81,
            "Visible weevils and surface mold; damp/musty odour reported.",
            "seed demo",
        ),
    )
    c.execute(
        """
        INSERT INTO photo_checks
        (reading_id, created_at, insects_visible, mold_signs, discoloration,
         damaged_grain_estimate_percent, confidence, notes, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            last_reading_ids[3],
            now_iso,
            0,
            0,
            1,
            2.0,
            0.72,
            "Minor discoloration; no obvious insects or mold.",
            "seed demo",
        ),
    )
    c.execute(
        """
        INSERT INTO photo_checks
        (reading_id, created_at, insects_visible, mold_signs, discoloration,
         damaged_grain_estimate_percent, confidence, notes, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            last_reading_ids[4],
            now_iso,
            0,
            0,
            1,
            5.0,
            0.68,
            "Outer skins slightly discolored; no sprouting visible.",
            "seed demo",
        ),
    )

    # Losses and prevented losses
    c.execute(
        """
        INSERT INTO losses
        (stock_id, event_date, kg_lost, value_lost, reason, prevented_kg, prevented_value)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            stock_ids[0],
            (today - dt.timedelta(days=7)).isoformat(),
            120.0,
            120.0 * 35.0,
            "Heating and mold after rain exposure",
            0.0,
            0.0,
        ),
    )
    c.execute(
        """
        INSERT INTO losses
        (stock_id, event_date, kg_lost, value_lost, reason, prevented_kg, prevented_value)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            stock_ids[3],
            (today - dt.timedelta(days=4)).isoformat(),
            80.0,
            80.0 * 22.0,
            "Soft rot and sprouting in cold room",
            0.0,
            0.0,
        ),
    )
    c.execute(
        """
        INSERT INTO losses
        (stock_id, event_date, kg_lost, value_lost, reason, prevented_kg, prevented_value)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            stock_ids[1],
            (today - dt.timedelta(days=3)).isoformat(),
            0.0,
            0.0,
            "Early ventilation prevented heating",
            220.0,
            220.0 * 28.0,
        ),
    )
    c.execute(
        """
        INSERT INTO losses
        (stock_id, event_date, kg_lost, value_lost, reason, prevented_kg, prevented_value)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            stock_ids[2],
            (today - dt.timedelta(days=5)).isoformat(),
            0.0,
            0.0,
            "Hermetic bag inspection prevented infestation spread",
            130.0,
            130.0 * 42.0,
        ),
    )

    conn.commit()
    conn.close()


def reset_database() -> None:
    """Drop all tables and recreate fresh demo database."""
    conn = get_conn()
    c = conn.cursor()
    for table in ["photo_checks", "alerts", "losses", "readings", "stocks", "limits", "units"]:
        c.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()
    conn.close()

    init_db()
    seed_demo_data(force=True)


# ----------------------------------------------------------------------------
# Data access
# ----------------------------------------------------------------------------
def get_units() -> List[Dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM units ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stocks() -> List[Dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT s.*, u.name AS unit_name, u.type AS unit_type
        FROM stocks s
        JOIN units u ON u.id = s.unit_id
        ORDER BY s.id
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stock_by_id(stock_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    row = conn.execute(
        """
        SELECT s.*, u.name AS unit_name, u.type AS unit_type
        FROM stocks s
        JOIN units u ON u.id = s.unit_id
        WHERE s.id = ?
        """,
        (stock_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_limits_df() -> pd.DataFrame:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM limits ORDER BY commodity").fetchall()
    conn.close()
    return pd.DataFrame([dict(r) for r in rows])


def get_limit(commodity: str) -> Dict[str, Any]:
    """Return safe limits for a commodity, with a safe default if missing."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM limits WHERE LOWER(commodity) = LOWER(?)",
        (commodity,),
    ).fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        "id": None,
        "commodity": commodity,
        "max_moisture_pct": 13.0,
        "max_temp_c": 30.0,
        "max_humidity_pct": 70.0,
        "label": "Missing default – verify locally",
    }


def get_latest_reading(stock_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM readings WHERE stock_id = ? ORDER BY reading_date DESC, id DESC LIMIT 1",
        (stock_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_readings_df(stock_id: int) -> pd.DataFrame:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM readings WHERE stock_id = ? ORDER BY reading_date ASC, id ASC",
        (stock_id,),
    ).fetchall()
    conn.close()
    return pd.DataFrame([dict(r) for r in rows])


def get_readings_for_stock(stock_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM readings WHERE stock_id = ? ORDER BY reading_date DESC, id DESC LIMIT ?",
        (stock_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_photo_check(stock_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    row = conn.execute(
        """
        SELECT pc.*
        FROM photo_checks pc
        JOIN readings r ON r.id = pc.reading_id
        WHERE r.stock_id = ?
        ORDER BY r.reading_date DESC, pc.id DESC
        LIMIT 1
        """,
        (stock_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_photo_checks_df() -> pd.DataFrame:
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT pc.*, r.stock_id, r.reading_date, s.commodity, u.name AS unit_name
        FROM photo_checks pc
        JOIN readings r ON r.id = pc.reading_id
        JOIN stocks s ON s.id = r.stock_id
        JOIN units u ON u.id = s.unit_id
        ORDER BY pc.created_at DESC
        """
    ).fetchall()
    conn.close()
    return pd.DataFrame([dict(r) for r in rows])


def get_alerts(acknowledged: Optional[int] = None) -> List[Dict[str, Any]]:
    conn = get_conn()
    if acknowledged is None:
        rows = conn.execute(
            """
            SELECT a.*, s.commodity, u.name AS unit_name
            FROM alerts a
            JOIN stocks s ON s.id = a.stock_id
            JOIN units u ON u.id = s.unit_id
            ORDER BY a.created_at DESC
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT a.*, s.commodity, u.name AS unit_name
            FROM alerts a
            JOIN stocks s ON s.id = a.stock_id
            JOIN units u ON u.id = s.unit_id
            WHERE a.acknowledged = ?
            ORDER BY a.created_at DESC
            """,
            (acknowledged,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_losses_df() -> pd.DataFrame:
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT l.*, s.commodity, u.name AS unit_name
        FROM losses l
        JOIN stocks s ON s.id = l.stock_id
        JOIN units u ON u.id = s.unit_id
        ORDER BY l.event_date DESC
        """
    ).fetchall()
    conn.close()
    return pd.DataFrame([dict(r) for r in rows])


def get_loss_summary() -> Dict[str, float]:
    conn = get_conn()
    row = conn.execute(
        """
        SELECT
            COALESCE(SUM(kg_lost), 0) AS kg_lost,
            COALESCE(SUM(value_lost), 0) AS value_lost,
            COALESCE(SUM(prevented_kg), 0) AS prevented_kg,
            COALESCE(SUM(prevented_value), 0) AS prevented_value
        FROM losses
        """
    ).fetchone()
    conn.close()
    return dict(row) if row else {
        "kg_lost": 0.0,
        "value_lost": 0.0,
        "prevented_kg": 0.0,
        "prevented_value": 0.0,
    }


# ----------------------------------------------------------------------------
# Delete helpers
# ----------------------------------------------------------------------------
def delete_stock(stock_id: int) -> None:
    conn = get_conn()
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys = OFF")
    c.execute(
        "DELETE FROM photo_checks WHERE reading_id IN (SELECT id FROM readings WHERE stock_id = ?)",
        (stock_id,),
    )
    c.execute("DELETE FROM alerts WHERE stock_id = ?", (stock_id,))
    c.execute("DELETE FROM losses WHERE stock_id = ?", (stock_id,))
    c.execute("DELETE FROM readings WHERE stock_id = ?", (stock_id,))
    c.execute("DELETE FROM stocks WHERE id = ?", (stock_id,))
    c.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    conn.close()


def delete_unit(unit_id: int) -> None:
    conn = get_conn()
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys = OFF")
    c.execute(
        """
        DELETE FROM photo_checks
        WHERE reading_id IN (
            SELECT id FROM readings
            WHERE stock_id IN (SELECT id FROM stocks WHERE unit_id = ?)
        )
        """,
        (unit_id,),
    )
    c.execute(
        "DELETE FROM alerts WHERE stock_id IN (SELECT id FROM stocks WHERE unit_id = ?)",
        (unit_id,),
    )
    c.execute(
        "DELETE FROM losses WHERE stock_id IN (SELECT id FROM stocks WHERE unit_id = ?)",
        (unit_id,),
    )
    c.execute(
        "DELETE FROM readings WHERE stock_id IN (SELECT id FROM stocks WHERE unit_id = ?)",
        (unit_id,),
    )
    c.execute("DELETE FROM stocks WHERE unit_id = ?", (unit_id,))
    c.execute("DELETE FROM units WHERE id = ?", (unit_id,))
    c.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    conn.close()


# ----------------------------------------------------------------------------
# Risk engine
# ----------------------------------------------------------------------------
def risk_component(value: float, limit: float, max_points: float) -> float:
    """
    Convert a measured value versus safe limit into a bounded risk component.
    Higher is worse for moisture, temperature, and humidity.
    """
    value = safe_float(value, 0.0)
    limit = safe_float(limit, 0.0)
    if limit <= 0:
        return 0.0

    if value <= limit * 0.90:
        return 0.0
    if value <= limit:
        return max_points * 0.50 * ((value - limit * 0.90) / (limit * 0.10))
    if value <= limit * 1.20:
        return max_points * (0.50 + 0.50 * ((value - limit) / (limit * 0.20)))
    return float(max_points)


def forecast_metric(stock_id: int, field: str, limit: float) -> Optional[Dict[str, Any]]:
    """
    Fit a simple linear trend to the last 10 readings and estimate days until
    the metric crosses the safe limit. Returns None if not enough data.
    """
    df = get_readings_df(stock_id)
    if df.empty or field not in df.columns:
        return None

    df = df.dropna(subset=[field]).copy()
    if len(df) < 2:
        return None

    parsed: List[dt.datetime] = []
    vals: List[float] = []
    for _, row in df.iterrows():
        d = parse_dt(row["reading_date"])
        v = row[field]
        if d is None or pd.isna(v):
            continue
        parsed.append(d)
        vals.append(float(v))

    if len(parsed) < 2:
        return None

    work = pd.DataFrame({"dt": parsed, "val": vals}).sort_values("dt").tail(10)
    if len(work) < 2:
        return None

    min_dt = work["dt"].min()
    xs = [(d - min_dt).total_seconds() / 86400.0 for d in work["dt"]]
    ys = work["val"].tolist()

    n = len(xs)
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    sum_xx = sum(x * x for x in xs)

    denom = n * sum_xx - sum_x * sum_x
    if abs(denom) < 1e-9:
        return None

    slope = (n * sum_xy - sum_x * sum_y) / denom
    current = ys[-1]
    days_to_cross = None

    if current >= limit:
        days_to_cross = 0.0
    elif slope > 1e-5:
        days_to_cross = (limit - current) / slope

    projected_7 = current + slope * 7.0

    return {
        "slope_per_day": float(slope),
        "current": float(current),
        "limit": float(limit),
        "days_to_cross": float(days_to_cross) if days_to_cross is not None else None,
        "projected_7_day": float(projected_7),
    }


def calculate_risk(stock: Dict[str, Any]) -> Dict[str, Any]:
    """
    Core Python risk engine.
    Score 0-100 from:
    - moisture vs limit
    - temperature vs limit
    - humidity vs limit
    - days in storage / expected sale pressure
    - photo findings
    """
    stock_id = stock["id"]
    commodity = stock["commodity"]
    lim = get_limit(commodity)

    read = get_latest_reading(stock_id)
    photo = get_latest_photo_check(stock_id)

    m_limit = safe_float(lim["max_moisture_pct"], 13.0)
    t_limit = safe_float(lim["max_temp_c"], 30.0)
    h_limit = safe_float(lim["max_humidity_pct"], 70.0)

    moisture = safe_float(read["moisture_pct"] if read else None, m_limit)
    temperature = safe_float(read["temp_c"] if read else None, t_limit)
    humidity = safe_float(read["rh_pct"] if read else None, h_limit)
    co2 = safe_float(read["co2_ppm"] if read else None, 0.0)
    smell = read["smell_notes"] if read and read["smell_notes"] else ""

    entry = parse_date(stock["entry_date"])
    expected = parse_date(stock["expected_sale_date"])
    today = dt.date.today()

    days_in_storage = max(0, (today - entry).days) if entry else 0
    days_to_expected = (expected - today).days if expected else None

    m_score = risk_component(moisture, m_limit, 35.0)
    t_score = risk_component(temperature, t_limit, 20.0)
    h_score = risk_component(humidity, h_limit, 15.0)

    # Days/storage pressure: max 10
    if days_to_expected is None:
        d_score = min(10.0, days_in_storage / 120.0 * 10.0)
    elif days_to_expected <= 0:
        d_score = 10.0
    elif days_to_expected <= 7:
        d_score = 7.0
    elif days_to_expected <= 21:
        d_score = 4.0
    else:
        d_score = min(3.0, days_in_storage / 120.0 * 3.0)

    # Photo findings: max 20
    p_score = 0.0
    if photo:
        if bool(photo["insects_visible"]):
            p_score += 6.0
        if bool(photo["mold_signs"]):
            p_score += 7.0
        if bool(photo["discoloration"]):
            p_score += 3.0
        damaged = safe_float(photo["damaged_grain_estimate_percent"], 0.0)
        p_score += min(4.0, damaged / 25.0 * 4.0)

    score = round(min(100.0, m_score + t_score + h_score + d_score + p_score), 1)
    level = score_to_level(score)

    forecast_m = forecast_metric(stock_id, "moisture_pct", m_limit)
    forecast_t = forecast_metric(stock_id, "temp_c", t_limit)

    quantity = safe_float(stock["quantity_kg"], 0.0)
    value_per_kg = safe_float(stock["value_per_kg"], 0.0)

    return {
        "stock": stock,
        "stock_id": stock_id,
        "unit_name": stock.get("unit_name", ""),
        "commodity": commodity,
        "quantity_kg": quantity,
        "value_per_kg": value_per_kg,
        "stock_value": quantity * value_per_kg,
        "entry_date": stock["entry_date"],
        "expected_sale_date": stock["expected_sale_date"],
        "days_in_storage": days_in_storage,
        "days_to_expected": days_to_expected,
        "latest_reading_date": read["reading_date"] if read else "",
        "moisture": moisture,
        "temperature": temperature,
        "humidity": humidity,
        "co2": co2,
        "smell": smell,
        "limit_moisture": m_limit,
        "limit_temp": t_limit,
        "limit_humidity": h_limit,
        "photo": photo,
        "components": {
            "moisture": round(m_score, 1),
            "temperature": round(t_score, 1),
            "humidity": round(h_score, 1),
            "storage_days": round(d_score, 1),
            "photo": round(p_score, 1),
        },
        "score": score,
        "level": level,
        "forecast_moisture": forecast_m,
        "forecast_temp": forecast_t,
    }


def get_all_risks() -> List[Dict[str, Any]]:
    risks: List[Dict[str, Any]] = []
    for s in get_stocks():
        try:
            risks.append(calculate_risk(s))
        except Exception:
            # Keep dashboard resilient if one stock has incomplete data.
            continue
    return risks


def forecast_days(fc: Optional[Dict[str, Any]]) -> Optional[float]:
    if not fc:
        return None
    return fc.get("days_to_cross")


def priority_from_risk(risk: Dict[str, Any]) -> Tuple[str, float]:
    """
    Combine risk and FIFO urgency.
    Returns (priority_code, priority_score).
    priority_code is one of: sell_first, inspect_today, stable.
    """
    score = risk["score"]
    dte = risk["days_to_expected"]
    fmd = forecast_days(risk["forecast_moisture"])
    ftd = forecast_days(risk["forecast_temp"])

    if (
        score >= 75
        or (dte is not None and dte <= 0)
        or (fmd is not None and fmd <= 7)
        or (ftd is not None and ftd <= 7)
    ):
        code = "sell_first"
    elif (
        score >= 45
        or (dte is not None and dte <= 14)
        or (fmd is not None and fmd <= 21)
        or (ftd is not None and ftd <= 21)
    ):
        code = "inspect_today"
    else:
        code = "stable"

    # FIFO urgency component, max 25
    if dte is not None:
        if dte <= 0:
            fifo = 25.0
        else:
            fifo = max(0.0, (30.0 - dte) / 30.0 * 25.0)
    else:
        fifo = min(15.0, risk["days_in_storage"] / 120.0 * 15.0)

    priority_score = round(score * 0.75 + fifo, 1)
    return code, priority_score


def sync_alerts() -> None:
    """Create alerts for high-risk stocks or worrying trends."""
    lang = st.session_state.get("lang", "en")
    conn = get_conn()

    for stock in get_stocks():
        try:
            risk = calculate_risk(stock)
        except Exception:
            continue

        code = None
        if risk["level"] in ("High", "Critical"):
            code = "alert_high_risk"
        elif risk["forecast_moisture"] and risk["forecast_moisture"]["days_to_cross"] is not None and risk["forecast_moisture"]["days_to_cross"] <= 14:
            code = "alert_moisture_trend"
        elif risk["forecast_temp"] and risk["forecast_temp"]["days_to_cross"] is not None and risk["forecast_temp"]["days_to_cross"] <= 14:
            code = "alert_temp_trend"
        elif risk["days_to_expected"] is not None and risk["days_to_expected"] <= 7:
            code = "alert_sale_due"

        if code:
            message = tr(code, lang)
            exists = conn.execute(
                "SELECT 1 FROM alerts WHERE stock_id = ? AND message = ? AND acknowledged = 0",
                (stock["id"], message),
            ).fetchone()
            if not exists:
                conn.execute(
                    """
                    INSERT INTO alerts (stock_id, created_at, level, message, acknowledged)
                    VALUES (?, ?, ?, ?, 0)
                    """,
                    (stock["id"], dt.datetime.now().isoformat(), risk["level"], message),
                )

    conn.commit()
    conn.close()


# ----------------------------------------------------------------------------
# Gemini / fallback AI helpers
# ----------------------------------------------------------------------------
def parse_json_object(text: str) -> Dict[str, Any]:
    """
    Strip code fences and parse strict JSON.
    Raises ValueError if JSON cannot be parsed.
    """
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("No JSON object found in Gemini response.")
    return json.loads(match.group(0))


def normalize_photo_result(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and coerce required Gemini photo JSON keys."""
    required = [
        "insects_visible",
        "mold_signs",
        "discoloration",
        "damaged_grain_estimate_percent",
        "confidence",
        "notes",
    ]
    for key in required:
        if key not in obj:
            raise ValueError(f"Missing required key: {key}")

    def to_bool(v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return bool(v)
        if isinstance(v, str):
            return v.strip().lower() in ("true", "yes", "1")
        return bool(v)

    insects = to_bool(obj["insects_visible"])
    mold = to_bool(obj["mold_signs"])
    discoloration = to_bool(obj["discoloration"])
    damaged = max(0.0, min(100.0, safe_float(obj["damaged_grain_estimate_percent"], 0.0)))
    confidence = max(0.0, min(1.0, safe_float(obj["confidence"], 0.5)))
    notes = str(obj["notes"]).strip()

    return {
        "insects_visible": insects,
        "mold_signs": mold,
        "discoloration": discoloration,
        "damaged_grain_estimate_percent": damaged,
        "confidence": confidence,
        "notes": notes,
    }


def fallback_photo_result(image_bytes: bytes, smell_notes: str = "", lang: str = "en") -> Dict[str, Any]:
    """
    Deterministic fallback visual assessment when Gemini is unavailable.
    This is not a lab test; it only keeps the app usable without an API key.
    """
    h = int(hashlib.sha256(image_bytes).hexdigest(), 16)
    smell_lower = (smell_notes or "").lower()

    mold_keywords = ["mold", "mould", "musty", "sour", "wet", "rot", "damp"]
    insect_keywords = ["insect", "weevil", "worm", "bug", "infest"]

    mold = any(k in smell_lower for k in mold_keywords) or (h % 10) < 3
    insects = any(k in smell_lower for k in insect_keywords) or (h % 10) < 4
    discoloration = (h % 10) < 5

    damaged = (h % 18) + (5.0 if mold else 0.0) + (3.0 if insects else 0.0)
    damaged = max(0.0, min(100.0, round(damaged, 1)))
    confidence = max(0.45, min(0.85, 0.55 + (h % 30) / 100.0))

    flags = []
    if insects:
        flags.append(tr("photo_flag_insects", lang))
    if mold:
        flags.append(tr("photo_flag_mold", lang))
    if discoloration:
        flags.append(tr("photo_flag_discoloration", lang))
    if not flags:
        flags.append(tr("photo_flag_clean", lang))

    notes = tr(
        "photo_notes_fallback",
        lang,
        flags=", ".join(flags),
        conf=int(confidence * 100),
    )

    return {
        "insects_visible": insects,
        "mold_signs": mold,
        "discoloration": discoloration,
        "damaged_grain_estimate_percent": damaged,
        "confidence": confidence,
        "notes": notes,
        "source": "fallback",
    }


def gemini_vision(image_bytes: bytes, mime: str, smell_notes: str, lang: str) -> Dict[str, Any]:
    """
    Call Gemini gemini-2.0-flash for photo analysis.
    Validates strict JSON and retries once on failure.
    """
    genai = load_genai()
    if genai is None:
        raise RuntimeError("google-generativeai is not available.")

    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("No Gemini API key configured.")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    lang_name = LANG_CODE_TO_NAME.get(lang, "English")
    prompt = f"""
You are a post-harvest grain and produce inspection assistant.
Analyze the attached photo carefully.

Return STRICT JSON only, with exactly these keys:
- insects_visible: boolean
- mold_signs: boolean
- discoloration: boolean
- damaged_grain_estimate_percent: number between 0 and 100
- confidence: number between 0 and 1
- notes: string in {lang_name}

Rules:
- Do not include markdown.
- Do not include extra keys.
- Do not give chemical doses.
- If uncertain, lower confidence.
Smell notes from operator: {smell_notes or "none"}
""".strip()

    image_part = {"mime_type": mime, "data": image_bytes}
    contents = [image_part, prompt]

    last_error: Optional[Exception] = None
    for _attempt in range(2):
        try:
            response = model.generate_content(contents)
            raw = getattr(response, "text", "") or ""
            obj = parse_json_object(raw)
            result = normalize_photo_result(obj)
            result["source"] = "gemini-2.0-flash"
            return result
        except Exception as exc:
            last_error = exc

    raise RuntimeError(str(last_error) if last_error else "Gemini photo analysis failed.")


def analyze_uploaded_photo(image_bytes: bytes, mime: str, smell_notes: str, lang: str) -> Dict[str, Any]:
    """
    Wrapper with friendly error handling.
    Uses Gemini if available, otherwise fallback.
    """
    if not get_api_key():
        return fallback_photo_result(image_bytes, smell_notes, lang)

    try:
        return gemini_vision(image_bytes, mime, smell_notes, lang)
    except Exception:
        st.warning("Gemini photo analysis is unavailable right now. A fallback visual estimate was used.")
        return fallback_photo_result(image_bytes, smell_notes, lang)


def local_action_text(risk: Dict[str, Any], lang: str) -> str:
    """Rule-based action guidance in selected language."""
    lines: List[str] = []
    lines.append(f"### {tr('action_header', lang)}")
    lines.append(
        f"**{tr('risk_level', lang)}:** {tr(risk['level'].lower(), lang)} ({risk['score']}/100)"
    )

    factors: List[str] = []
    if risk["moisture"] > risk["limit_moisture"] * 1.0001:
        factors.append(
            tr(
                "moisture_high",
                lang,
                value=round(risk["moisture"], 1),
                limit=round(risk["limit_moisture"], 1),
            )
        )
    if risk["temperature"] > risk["limit_temp"] * 1.0001:
        factors.append(
            tr(
                "temp_high",
                lang,
                value=round(risk["temperature"], 1),
                limit=round(risk["limit_temp"], 1),
            )
        )
    if risk["humidity"] > risk["limit_humidity"] * 1.0001:
        factors.append(
            tr(
                "humidity_high",
                lang,
                value=round(risk["humidity"], 1),
                limit=round(risk["limit_humidity"], 1),
            )
        )

    if risk["days_to_expected"] is not None:
        if risk["days_to_expected"] <= 0:
            factors.append(tr("overdue", lang, days=abs(risk["days_to_expected"])))
        else:
            factors.append(
                tr(
                    "storage_long",
                    lang,
                    days=risk["days_in_storage"],
                    days_to=risk["days_to_expected"],
                )
            )
    else:
        factors.append(
            tr("storage_long", lang, days=risk["days_in_storage"], days_to="n/a")
        )

    photo = risk.get("photo")
    if photo:
        if bool(photo["insects_visible"]):
            factors.append(tr("insects", lang))
        if bool(photo["mold_signs"]):
            factors.append(tr("mold", lang))
        if bool(photo["discoloration"]):
            factors.append(tr("discoloration", lang))
        damaged = safe_float(photo["damaged_grain_estimate_percent"], 0.0)
        if damaged > 0:
            factors.append(tr("damaged", lang, percent=round(damaged, 1)))

    if factors:
        lines.append("")
        lines.append(f"**{tr('why', lang)}**")
        lines.extend([f"- {x}" for x in factors])

    steps: List[str] = []
    if risk["moisture"] > risk["limit_moisture"] * 0.95:
        steps.append(tr("step_dry", lang))
    if risk["temperature"] > risk["limit_temp"] * 0.95:
        steps.append(tr("step_ventilate_turn", lang))
    if risk["humidity"] > risk["limit_humidity"] * 0.95:
        steps.append(tr("step_humidity", lang))

    if photo and (bool(photo["insects_visible"]) or bool(photo["mold_signs"])):
        steps.append(tr("step_inspect_clean", lang))
        steps.append(tr("step_licensed_fumigation", lang))

    priority_code, _ = priority_from_risk(risk)
    if priority_code == "sell_first":
        steps.append(tr("step_sell_first", lang))
    elif priority_code == "inspect_today":
        steps.append(tr("step_inspect_today", lang))
    else:
        steps.append(tr("step_monitor", lang))

    steps.append(tr("step_no_chemical_doses", lang))

    lines.append("")
    lines.append(f"**{tr('next_steps', lang)}**")
    lines.extend([f"- {x}" for x in steps])
    return "\n".join(lines)


def gemini_action_text(risk: Dict[str, Any], lang: str) -> str:
    """Use Gemini to explain risk and suggest next steps in selected language."""
    genai = load_genai()
    if genai is None:
        raise RuntimeError("google-generativeai is not available.")

    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("No Gemini API key configured.")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")
    lang_name = LANG_CODE_TO_NAME.get(lang, "English")

    data = {
        "commodity": risk["commodity"],
        "unit": risk["unit_name"],
        "risk_score": risk["score"],
        "risk_level": risk["level"],
        "moisture_percent": risk["moisture"],
        "moisture_limit": risk["limit_moisture"],
        "temperature_c": risk["temperature"],
        "temperature_limit": risk["limit_temp"],
        "humidity_percent": risk["humidity"],
        "humidity_limit": risk["limit_humidity"],
        "days_in_storage": risk["days_in_storage"],
        "days_to_expected_sale": risk["days_to_expected"],
        "photo_findings": risk["photo"],
        "forecast_moisture": risk["forecast_moisture"],
        "forecast_temperature": risk["forecast_temp"],
    }

    prompt = f"""
You are a practical post-harvest storage advisor.
Write in {lang_name}.
Explain the spoilage risk in simple language and suggest next steps.
Use short bullets.
Allowed actions: ventilate, turn, dry, isolate, inspect, sell first, contact a licensed operator for fumigation/treatment.
Do NOT give chemical doses or product-specific pesticide instructions.
Keep it under 180 words.

Data:
{json.dumps(data, indent=2, default=str)}
""".strip()

    response = model.generate_content(prompt)
    text = getattr(response, "text", "") or ""
    return text.strip()


def get_action_text(risk: Dict[str, Any], lang: str) -> str:
    """
    Return AI action text if Gemini key exists; otherwise local fallback.
    All API calls are wrapped with friendly error handling.
    """
    if not get_api_key():
        return local_action_text(risk, lang)

    try:
        text = gemini_action_text(risk, lang)
        if text:
            return text
    except Exception:
        st.warning("Gemini action guidance is unavailable right now. Using built-in guidance.")

    return local_action_text(risk, lang)


# ----------------------------------------------------------------------------
# Photo/file helpers
# ----------------------------------------------------------------------------
def save_photo(file: Any) -> str:
    """Save uploaded photo to disk and return relative path."""
    content = file.getvalue()
    basename = os.path.basename(file.name or "photo.jpg")
    ext = os.path.splitext(basename)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        ext = ".jpg"
    digest = hashlib.sha256(content).hexdigest()[:16]
    path = os.path.join(UPLOAD_DIR, f"{digest}{ext}")
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(content)
    return path


def guess_mime(file: Any) -> str:
    """Guess MIME type from uploaded file."""
    if getattr(file, "type", None):
        return file.type
    name = (file.name or "").lower()
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


# ----------------------------------------------------------------------------
# Live simulation
# ----------------------------------------------------------------------------
def simulation_tick() -> None:
    """
    Lightweight live simulation for the Dashboard.
    Adds one synthetic reading every ~20 seconds to the first stock.
    This prevents a blank/static demo and lets the user see the app update.
    """
    if not st.session_state.get("sim_enabled", False):
        return
    if st.session_state.get("page", "") != "Dashboard":
        return

    now = time.time()
    last = st.session_state.get("last_sim_time", now)
    if now - last < 20:
        return

    conn = get_conn()
    stock = conn.execute("SELECT id FROM stocks ORDER BY id LIMIT 1").fetchone()
    if not stock:
        conn.close()
        return

    stock_id = stock["id"]
    last_read = conn.execute(
        "SELECT * FROM readings WHERE stock_id = ? ORDER BY reading_date DESC, id DESC LIMIT 1",
        (stock_id,),
    ).fetchone()

    moisture = safe_float(last_read["moisture_pct"] if last_read else None, 12.0)
    temp = safe_float(last_read["temp_c"] if last_read else None, 28.0)
    rh = safe_float(last_read["rh_pct"] if last_read else None, 65.0)

    rng = random.Random(int(now * 1000) % 1000000)
    moisture = min(20.0, moisture + 0.03 + rng.uniform(-0.02, 0.05))
    temp = min(42.0, temp + 0.05 + rng.uniform(-0.03, 0.06))
    rh = min(98.0, rh + 0.04 + rng.uniform(-0.4, 0.7))
    smell = "musty/warm" if moisture > 12.8 else "routine live check"

    c = conn.cursor()
    c.execute(
        """
        INSERT INTO readings
        (stock_id, reading_date, temp_c, rh_pct, moisture_pct, co2_ppm, smell_notes, photo_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            stock_id,
            dt.datetime.now().isoformat(),
            round(temp, 2),
            round(rh, 2),
            round(moisture, 2),
            None,
            smell,
            "",
        ),
    )
    conn.commit()
    conn.close()

    st.session_state.last_sim_time = now
    st.rerun()


# ----------------------------------------------------------------------------
# PDF report
# ----------------------------------------------------------------------------
def generate_weekly_pdf() -> bytes:
    """Generate a simple weekly storage report PDF."""
    risks = get_all_risks()
    loss_summary = get_loss_summary()
    losses_df = get_losses_df()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 8, pdf_safe("StoreGuard Weekly Storage Report"))

    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5, pdf_safe(f"Generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}"))
    pdf.ln(2)

    # Summary
    total_qty = sum(r["quantity_kg"] for r in risks)
    total_value = sum(r["stock_value"] for r in risks)
    high_risk = sum(1 for r in risks if r["level"] in ("High", "Critical"))

    pdf.set_font("Helvetica", "B", 12)
    pdf.multi_cell(0, 7, pdf_safe("1. Summary"))
    pdf.set_font("Helvetica", "", 10)
    for line in [
        f"Active stocks: {len(risks)}",
        f"Total quantity: {total_qty:,.1f} kg",
        f"Total declared value: {total_value:,.2f}",
        f"High/Critical risk stocks: {high_risk}",
        f"Recorded lost quantity: {loss_summary.get('kg_lost', 0):,.1f} kg",
        f"Recorded lost value: {loss_summary.get('value_lost', 0):,.2f}",
        f"Prevented quantity estimate: {loss_summary.get('prevented_kg', 0):,.1f} kg",
        f"Prevented value estimate: {loss_summary.get('prevented_value', 0):,.2f}",
    ]:
        pdf.multi_cell(0, 5, pdf_safe(line))
    pdf.ln(1)

    # Risk per unit
    pdf.set_font("Helvetica", "B", 12)
    pdf.multi_cell(0, 7, pdf_safe("2. Risk per unit"))
    pdf.set_font("Helvetica", "", 10)

    unit_map: Dict[str, Dict[str, Any]] = {}
    for r in risks:
        unit = r["unit_name"] or "Unknown"
        d = unit_map.setdefault(
            unit,
            {"qty": 0.0, "value": 0.0, "max_score": 0.0, "level": "Low", "commodities": set()},
        )
        d["qty"] += r["quantity_kg"]
        d["value"] += r["stock_value"]
        d["commodities"].add(r["commodity"])
        if r["score"] > d["max_score"]:
            d["max_score"] = r["score"]
            d["level"] = r["level"]

    for unit, d in unit_map.items():
        line = (
            f"{unit}: max risk {d['max_score']:.1f} ({d['level']}), "
            f"qty {d['qty']:,.1f} kg, value {d['value']:,.2f}, "
            f"commodities: {', '.join(sorted(d['commodities']))}"
        )
        pdf.multi_cell(0, 5, pdf_safe(line))
    pdf.ln(1)

    # Trends
    pdf.set_font("Helvetica", "B", 12)
    pdf.multi_cell(0, 7, pdf_safe("3. Trends and forecast"))
    pdf.set_font("Helvetica", "", 10)
    for r in risks:
        fm = r.get("forecast_moisture")
        ft = r.get("forecast_temp")
        m_txt = "n/a"
        t_txt = "n/a"
        if fm:
            days = fm.get("days_to_cross")
            m_txt = (
                f"slope {fm['slope_per_day']:.3f}/day, "
                + ("already above limit" if days == 0 else f"days to limit {days:.1f}" if days is not None else "not crossing")
            )
        if ft:
            days = ft.get("days_to_cross")
            t_txt = (
                f"slope {ft['slope_per_day']:.3f}/day, "
                + ("already above limit" if days == 0 else f"days to limit {days:.1f}" if days is not None else "not crossing")
            )
        line = f"{r['unit_name']} - {r['commodity']}: moisture {m_txt}; temperature {t_txt}"
        pdf.multi_cell(0, 5, pdf_safe(line))
    pdf.ln(1)

    # Priority list
    pdf.set_font("Helvetica", "B", 12)
    pdf.multi_cell(0, 7, pdf_safe("4. Priority list"))
    pdf.set_font("Helvetica", "", 10)

    priority_rows = []
    for r in risks:
        code, pscore = priority_from_risk(r)
        priority_rows.append(
            {
                "unit": r["unit_name"],
                "commodity": r["commodity"],
                "score": r["score"],
                "level": r["level"],
                "priority": code,
                "pscore": pscore,
                "days_to_expected": r["days_to_expected"],
            }
        )
    priority_rows.sort(key=lambda x: x["pscore"], reverse=True)

    for row in priority_rows:
        label = {
            "sell_first": "Sell first",
            "inspect_today": "Inspect today",
            "stable": "Stable",
        }.get(row["priority"], row["priority"])
        dte = row["days_to_expected"]
        dte_txt = "n/a" if dte is None else str(dte)
        line = (
            f"{row['unit']} - {row['commodity']}: {label}, risk {row['score']:.1f} "
            f"({row['level']}), days to expected sale {dte_txt}"
        )
        pdf.multi_cell(0, 5, pdf_safe(line))
    pdf.ln(1)

    # Losses
    pdf.set_font("Helvetica", "B", 12)
    pdf.multi_cell(0, 7, pdf_safe("5. Loss tracking"))
    pdf.set_font("Helvetica", "", 10)
    if losses_df.empty:
        pdf.multi_cell(0, 5, pdf_safe("No loss records found."))
    else:
        recent = losses_df.head(20)
        for _, row in recent.iterrows():
            line = (
                f"{row['event_date']} | {row['unit_name']} | {row['commodity']} | "
                f"lost {safe_float(row['kg_lost'], 0):,.1f} kg / {safe_float(row['value_lost'], 0):,.2f} | "
                f"prevented {safe_float(row['prevented_kg'], 0):,.1f} kg / {safe_float(row['prevented_value'], 0):,.2f} | "
                f"{row['reason']}"
            )
            pdf.multi_cell(0, 5, pdf_safe(line))

    return bytes(pdf.output())


# ----------------------------------------------------------------------------
# Pages
# ----------------------------------------------------------------------------
def page_dashboard() -> None:
    st.title("🌾 StoreGuard Dashboard")
    st.caption(
        "Automatic spoilage-risk scoring, FIFO priority, trend forecasts, and loss tracking. "
        "Demo data is loaded automatically."
    )

    sync_alerts()
    risks = get_all_risks()

    if not risks:
        st.info("No stocks found. Go to **Demo Data** to load demo data, or add stocks manually.")
        return

    df = pd.DataFrame(
        [
            {
                "Unit": r["unit_name"],
                "Commodity": r["commodity"],
                "Qty kg": r["quantity_kg"],
                "Value": r["stock_value"],
                "Score": r["score"],
                "Level": r["level"],
                "Moisture %": r["moisture"],
                "Temp °C": r["temperature"],
                "RH %": r["humidity"],
                "Days to sale": r["days_to_expected"],
            }
            for r in risks
        ]
    )

    c1, c2, c3, c4 = st.columns(4)
    kpi_card("Units", str(df["Unit"].nunique()), "storage locations", c1)
    kpi_card("Total stock", f"{df['Qty kg'].sum():,.0f} kg", "across all commodities", c2)
    kpi_card("Declared value", f"{df['Value'].sum():,.0f}", "quantity × value/kg", c3)
    high_count = int((df["Level"].isin(["High", "Critical"])).sum())
    kpi_card("High/Critical", str(high_count), "needs urgent attention", c4)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Risk by unit")
        fig = px.bar(
            df,
            x="Unit",
            y="Score",
            color="Level",
            category_orders={"Level": ["Low", "Medium", "High", "Critical"]},
            labels={"Score": "Risk score"},
        )
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Latest trend for highest-risk stock")
        top = max(risks, key=lambda x: x["score"])
        rdf = get_readings_df(top["stock_id"]).tail(20)
        if rdf.empty:
            st.info("No readings for this stock yet.")
        else:
            rdf = rdf.copy()
            rdf["date"] = rdf["reading_date"].apply(lambda x: parse_dt(x).date() if parse_dt(x) else None)
            rdf = rdf.dropna(subset=["date"])
            fig2 = px.line(
                rdf,
                x="date",
                y="moisture_pct",
                markers=True,
                labels={"moisture_pct": "Moisture %", "date": "Reading date"},
                title=f"{top['unit_name']} - {top['commodity']}",
            )
            fig2.add_hline(
                y=top["limit_moisture"],
                line_dash="dash",
                annotation_text="Safe moisture limit",
            )
            fig2.update_layout(height=320, margin=dict(l=10, r=10, t=50, b=10))
            st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Priority list")
    priority_rows = []
    lang = st.session_state.get("lang", "en")
    for r in risks:
        code, pscore = priority_from_risk(r)
        priority_rows.append(
            {
                "Unit": r["unit_name"],
                "Commodity": r["commodity"],
                "Qty kg": r["quantity_kg"],
                "Risk score": r["score"],
                "Level": tr(r["level"].lower(), lang),
                "Priority": tr(code, lang),
                "Priority score": pscore,
                "Days to sale": r["days_to_expected"],
            }
        )
    priority_df = pd.DataFrame(priority_rows).sort_values("Priority score", ascending=False)
    st.dataframe(priority_df, use_container_width=True, hide_index=True)

    st.subheader("Recent alerts")
    alerts = get_alerts()
    if alerts:
        adf = pd.DataFrame(alerts).head(10)
        adf["acknowledged"] = adf["acknowledged"].map({0: "No", 1: "Yes"})
        st.dataframe(adf[["created_at", "unit_name", "commodity", "level", "message", "acknowledged"]], use_container_width=True, hide_index=True)
    else:
        st.caption("No alerts yet.")


def page_units() -> None:
    st.header("Storage units")

    with st.form("add_unit_form"):
        name = st.text_input("Unit name")
        typ = st.selectbox("Type", ["godown", "silo", "hermetic bags", "cold room", "other"])
        capacity = st.number_input("Capacity kg", min_value=0.0, value=1000.0, step=100.0)
        submitted = st.form_submit_button("Add unit")

        if submitted:
            if not name.strip():
                st.error("Unit name is required.")
            else:
                conn = get_conn()
                conn.execute(
                    "INSERT INTO units (name, type, capacity_kg) VALUES (?, ?, ?)",
                    (name.strip(), typ, capacity),
                )
                conn.commit()
                conn.close()
                st.success("Unit added.")
                st.rerun()

    units = get_units()
    if not units:
        st.info("No units yet. Add one above or load demo data.")
        return

    udf = pd.DataFrame(units)
    st.subheader("Existing units")
    st.dataframe(udf, use_container_width=True, hide_index=True)

    st.subheader("Delete unit")
    selected = st.selectbox(
        "Select unit to delete",
        udf["id"].tolist(),
        format_func=lambda x: f'{udf.loc[udf["id"] == x, "name"].values[0]} (#{x})',
    )
    if st.button("Delete selected unit"):
        delete_unit(int(selected))
        st.success("Unit and related records deleted.")
        st.rerun()


def page_stocks() -> None:
    st.header("Stocks")

    units = get_units()
    if not units:
        st.warning("Add a storage unit first.")
        return

    udf = pd.DataFrame(units)
    with st.form("add_stock_form"):
        unit_sel = st.selectbox(
            "Storage unit",
            udf["id"].tolist(),
            format_func=lambda x: udf.loc[udf["id"] == x, "name"].values[0],
        )
        commodity = st.text_input("Commodity", value="Wheat")
        quantity = st.number_input("Quantity kg", min_value=0.0, value=1000.0, step=100.0)
        entry_date = st.date_input("Entry date", dt.date.today())
        expected_sale = st.date_input("Expected sale date", dt.date.today() + dt.timedelta(days=30))
        value_per_kg = st.number_input("Purchase/market value per kg", min_value=0.0, value=30.0, step=1.0)
        submitted = st.form_submit_button("Add stock")

        if submitted:
            if not commodity.strip():
                st.error("Commodity is required.")
            else:
                conn = get_conn()
                conn.execute(
                    """
                    INSERT INTO stocks
                    (unit_id, commodity, quantity_kg, entry_date, expected_sale_date, value_per_kg)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(unit_sel),
                        commodity.strip(),
                        quantity,
                        entry_date.isoformat(),
                        expected_sale.isoformat(),
                        value_per_kg,
                    ),
                )
                conn.commit()
                conn.close()
                st.success("Stock added.")
                st.rerun()

    stocks = get_stocks()
    if not stocks:
        st.info("No stocks yet.")
        return

    sdf = pd.DataFrame(stocks)
    st.subheader("Existing stocks")
    st.dataframe(
        sdf[["id", "unit_name", "unit_type", "commodity", "quantity_kg", "entry_date", "expected_sale_date", "value_per_kg"]],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Delete stock")
    selected = st.selectbox(
        "Select stock to delete",
        sdf["id"].tolist(),
        format_func=lambda x: f'{sdf.loc[sdf["id"] == x, "unit_name"].values[0]} - {sdf.loc[sdf["id"] == x, "commodity"].values[0]} (#{x})',
    )
    if st.button("Delete selected stock"):
        delete_stock(int(selected))
        st.success("Stock and related records deleted.")
        st.rerun()


def page_readings() -> None:
    st.header("Readings")

    flash = st.session_state.pop("readings_flash", None)
    if flash:
        st.success(flash)

    stocks = get_stocks()
    if not stocks:
        st.warning("Add a stock first.")
        return

    sdf = pd.DataFrame(stocks)
    lang = st.session_state.get("lang", "en")

    with st.form("add_reading_form"):
        stock_sel = st.selectbox(
            "Stock",
            sdf["id"].tolist(),
            format_func=lambda x: f'{sdf.loc[sdf["id"] == x, "unit_name"].values[0]} - {sdf.loc[sdf["id"] == x, "commodity"].values[0]} (#{x})',
        )
        reading_date = st.date_input("Reading date", dt.date.today())
        temp = st.number_input("Temperature °C", min_value=-50.0, max_value=100.0, value=28.0, step=0.1)
        rh = st.number_input("Relative humidity %", min_value=0.0, max_value=100.0, value=65.0, step=0.1)
        moisture = st.number_input("Grain moisture %", min_value=0.0, max_value=100.0, value=12.0, step=0.1)
        co2 = st.number_input("CO2 ppm (optional, 0 = skip)", min_value=0.0, max_value=200000.0, value=0.0, step=10.0)
        smell = st.text_area("Smell notes", height=80)
        submitted = st.form_submit_button("Save reading")

        if submitted:
            stock_id = int(stock_sel)
            conn = get_conn()
            c = conn.cursor()
            c.execute(
                """
                INSERT INTO readings
                (stock_id, reading_date, temp_c, rh_pct, moisture_pct, co2_ppm, smell_notes, photo_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stock_id,
                    reading_date.isoformat(),
                    temp,
                    rh,
                    moisture,
                    co2 if co2 > 0 else None,
                    smell,
                    "",
                ),
            )
            reading_id = c.lastrowid
            conn.commit()
            conn.close()

            st.session_state["last_reading_id"] = reading_id
            st.session_state["last_reading_stock_id"] = stock_id
            st.session_state["readings_flash"] = "Reading saved. Optionally upload photos below."
            st.rerun()

    st.subheader("Attach photos to latest saved reading")
    last_rid = st.session_state.get("last_reading_id")
    if last_rid:
        photos = st.file_uploader(
            "Photo(s) of grain/produce",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            key="reading_photos",
        )

        if st.button("Analyze and attach photos") and photos:
            conn = get_conn()
            c = conn.cursor()

            row = c.execute("SELECT smell_notes FROM readings WHERE id = ?", (int(last_rid),)).fetchone()
            smell = row["smell_notes"] if row and row["smell_notes"] else ""

            saved_paths: List[str] = []
            for photo in photos:
                path = save_photo(photo)
                saved_paths.append(path)
                result = analyze_uploaded_photo(photo.getvalue(), guess_mime(photo), smell, lang)
                c.execute(
                    """
                    INSERT INTO photo_checks
                    (reading_id, created_at, insects_visible, mold_signs, discoloration,
                     damaged_grain_estimate_percent, confidence, notes, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(last_rid),
                        dt.datetime.now().isoformat(),
                        int(result["insects_visible"]),
                        int(result["mold_signs"]),
                        int(result["discoloration"]),
                        result["damaged_grain_estimate_percent"],
                        result["confidence"],
                        result["notes"],
                        result.get("source", "fallback"),
                    ),
                )

            if saved_paths:
                c.execute(
                    "UPDATE readings SET photo_path = ? WHERE id = ?",
                    (",".join(saved_paths), int(last_rid)),
                )

            conn.commit()
            conn.close()
            st.session_state["readings_flash"] = "Photo check(s) added."
            st.rerun()
    else:
        st.caption("Save a reading first, then upload photos here.")

    st.subheader("CSV upload")
    csv_file = st.file_uploader("Upload readings CSV", type="csv", key="readings_csv")
    if csv_file:
        try:
            cdf = pd.read_csv(csv_file)
            cdf.columns = [str(c).strip().lower() for c in cdf.columns]
            required = {"stock_id", "reading_date", "temp_c", "rh_pct", "moisture_pct"}
            missing = required - set(cdf.columns)
            if missing:
                st.error(f"CSV missing required columns: {', '.join(sorted(missing))}")
            else:
                st.write("Preview")
                st.dataframe(cdf.head(10), use_container_width=True)

                existing_stock_ids = {int(s["id"]) for s in stocks}
                valid_rows: List[Any] = []
                errors: List[str] = []

                for idx, row in cdf.iterrows():
                    try:
                        sid = int(row["stock_id"])
                    except Exception:
                        errors.append(f"Row {idx+2}: invalid stock_id")
                        continue
                    if sid not in existing_stock_ids:
                        errors.append(f"Row {idx+2}: stock_id {sid} does not exist")
                        continue

                    d = parse_date(row["reading_date"])
                    if d is None:
                        errors.append(f"Row {idx+2}: invalid reading_date")
                        continue

                    if pd.isna(row["temp_c"]) or pd.isna(row["rh_pct"]) or pd.isna(row["moisture_pct"]):
                        errors.append(f"Row {idx+2}: temp_c, rh_pct, moisture_pct are required")
                        continue

                    co2_val = None
                    if "co2_ppm" in cdf.columns and not pd.isna(row.get("co2_ppm")):
                        co2_val = safe_float(row.get("co2_ppm"), 0.0)
                        if co2_val <= 0:
                            co2_val = None

                    smell_val = ""
                    if "smell_notes" in cdf.columns and not pd.isna(row.get("smell_notes")):
                        smell_val = str(row.get("smell_notes"))

                    valid_rows.append(
                        (
                            sid,
                            d.isoformat(),
                            float(row["temp_c"]),
                            float(row["rh_pct"]),
                            float(row["moisture_pct"]),
                            co2_val,
                            smell_val,
                            "",
                        )
                    )

                if errors:
                    st.error("Some rows were not imported:\n" + "\n".join(errors[:15]))

                if st.button("Import valid CSV rows") and valid_rows:
                    conn = get_conn()
                    conn.executemany(
                        """
                        INSERT INTO readings
                        (stock_id, reading_date, temp_c, rh_pct, moisture_pct, co2_ppm, smell_notes, photo_path)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        valid_rows,
                    )
                    conn.commit()
                    conn.close()
                    st.success(f"Imported {len(valid_rows)} readings.")
                    st.rerun()
        except Exception as exc:
            st.error(f"Could not read CSV: {exc}")

    st.subheader("Recent readings")
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT r.*, s.commodity, u.name AS unit_name
        FROM readings r
        JOIN stocks s ON s.id = r.stock_id
        JOIN units u ON u.id = s.unit_id
        ORDER BY r.reading_date DESC, r.id DESC
        LIMIT 100
        """
    ).fetchall()
    conn.close()
    if rows:
        st.dataframe(pd.DataFrame([dict(r) for r in rows]), use_container_width=True, hide_index=True)
    else:
        st.caption("No readings yet.")


def page_limits() -> None:
    st.header("Editable safe-limit table")
    st.caption("Generic values are pre-filled and labelled 'verify locally'. Adjust them to local extension guidance.")

    df = get_limits_df()
    edited = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        disabled=["id"],
        column_config={
            "commodity": st.column_config.TextColumn("Commodity"),
            "max_moisture_pct": st.column_config.NumberColumn("Max safe moisture %", min_value=0.0, max_value=100.0, step=0.1),
            "max_temp_c": st.column_config.NumberColumn("Max safe temperature °C", min_value=-50.0, max_value=100.0, step=0.1),
            "max_humidity_pct": st.column_config.NumberColumn("Max humidity %", min_value=0.0, max_value=100.0, step=0.1),
            "label": st.column_config.TextColumn("Label"),
        },
        key="limits_editor",
    )

    if st.button("Save limits"):
        conn = get_conn()
        c = conn.cursor()
        saved = 0
        for _, row in edited.iterrows():
            commodity_raw = row["commodity"]
            commodity = "" if pd.isna(commodity_raw) else str(commodity_raw).strip().lower()
            if not commodity:
                continue

            mm = safe_float(row["max_moisture_pct"], 13.0)
            mt = safe_float(row["max_temp_c"], 30.0)
            mh = safe_float(row["max_humidity_pct"], 70.0)

            label_raw = row["label"]
            label = "Generic – verify locally" if pd.isna(label_raw) else str(label_raw).strip()

            try:
                if pd.isna(row["id"]):
                    c.execute(
                        """
                        INSERT INTO limits (commodity, max_moisture_pct, max_temp_c, max_humidity_pct, label)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (commodity, mm, mt, mh, label),
                    )
                else:
                    c.execute(
                        """
                        UPDATE limits
                        SET commodity = ?, max_moisture_pct = ?, max_temp_c = ?, max_humidity_pct = ?, label = ?
                        WHERE id = ?
                        """,
                        (commodity, mm, mt, mh, label, int(row["id"])),
                    )
                saved += 1
            except sqlite3.IntegrityError:
                st.error(f"Commodity already exists: {commodity}")

        conn.commit()
        conn.close()
        st.success(f"Saved {saved} limit rows.")
        st.rerun()


def page_photos() -> None:
    st.header("Photo checks")
    lang = st.session_state.get("lang", "en")

    stocks = get_stocks()
    if not stocks:
        st.warning("Add a stock first.")
        return

    sdf = pd.DataFrame(stocks)
    stock_sel = st.selectbox(
        "Stock",
        sdf["id"].tolist(),
        format_func=lambda x: f'{sdf.loc[sdf["id"] == x, "unit_name"].values[0]} - {sdf.loc[sdf["id"] == x, "commodity"].values[0]} (#{x})',
        key="photo_stock",
    )

    readings = get_readings_for_stock(int(stock_sel), limit=30)
    if not readings:
        st.info("No readings for this stock. Add a reading first.")
        return

    rdf = pd.DataFrame(readings)
    reading_sel = st.selectbox(
        "Reading to attach photo check to",
        rdf["id"].tolist(),
        format_func=lambda x: f'{rdf.loc[rdf["id"] == x, "reading_date"].values[0]} | M={rdf.loc[rdf["id"] == x, "moisture_pct"].values[0]} | T={rdf.loc[rdf["id"] == x, "temp_c"].values[0]}',
        key="photo_reading",
    )

    photos = st.file_uploader(
        "Upload grain/produce photo(s)",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        key="standalone_photos",
    )

    if st.button("Analyze and save photo check") and photos:
        conn = get_conn()
        c = conn.cursor()
        for photo in photos:
            result = analyze_uploaded_photo(photo.getvalue(), guess_mime(photo), "", lang)
            c.execute(
                """
                INSERT INTO photo_checks
                (reading_id, created_at, insects_visible, mold_signs, discoloration,
                 damaged_grain_estimate_percent, confidence, notes, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(reading_sel),
                    dt.datetime.now().isoformat(),
                    int(result["insects_visible"]),
                    int(result["mold_signs"]),
                    int(result["discoloration"]),
                    result["damaged_grain_estimate_percent"],
                    result["confidence"],
                    result["notes"],
                    result.get("source", "fallback"),
                ),
            )
        conn.commit()
        conn.close()
        st.success("Photo check saved.")
        st.rerun()

    st.subheader("Recent photo checks")
    pcdf = get_photo_checks_df()
    if pcdf.empty:
        st.caption("No photo checks yet.")
    else:
        show_cols = [
            "created_at",
            "unit_name",
            "commodity",
            "reading_date",
            "insects_visible",
            "mold_signs",
            "discoloration",
            "damaged_grain_estimate_percent",
            "confidence",
            "notes",
            "source",
        ]
        st.dataframe(pcdf[show_cols].head(100), use_container_width=True, hide_index=True)


def page_risk_forecast() -> None:
    st.header("Risk & Forecast")

    stocks = get_stocks()
    if not stocks:
        st.warning("Add a stock first.")
        return

    sdf = pd.DataFrame(stocks)
    lang = st.session_state.get("lang", "en")
    stock_sel = st.selectbox(
        "Stock",
        sdf["id"].tolist(),
        format_func=lambda x: f'{sdf.loc[sdf["id"] == x, "unit_name"].values[0]} - {sdf.loc[sdf["id"] == x, "commodity"].values[0]} (#{x})',
        key="risk_stock",
    )

    stock = get_stock_by_id(int(stock_sel))
    if not stock:
        st.error("Stock not found.")
        return

    risk = calculate_risk(stock)

    c1, c2, c3, c4 = st.columns(4)
    kpi_card("Risk score", f"{risk['score']:.1f}", tr(risk["level"].lower(), lang), c1)
    kpi_card("Moisture", f"{risk['moisture']:.1f}%", f"limit {risk['limit_moisture']:.1f}%", c2)
    kpi_card("Temperature", f"{risk['temperature']:.1f}°C", f"limit {risk['limit_temp']:.1f}°C", c3)
    kpi_card("Humidity", f"{risk['humidity']:.1f}%", f"limit {risk['limit_humidity']:.1f}%", c4)

    col1, col2 = st.columns([1, 2])
    with col1:
        fig = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=risk["score"],
                number={"suffix": " / 100"},
                title={"text": "Spoilage risk"},
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"color": "#2563eb"},
                    "steps": [
                        {"range": [0, 25], "color": "#dcfce7"},
                        {"range": [25, 50], "color": "#fef9c3"},
                        {"range": [50, 75], "color": "#fed7aa"},
                        {"range": [75, 100], "color": "#fecaca"},
                    ],
                    "threshold": {
                        "line": {"color": "#111827", "width": 3},
                        "value": risk["score"],
                    },
                },
            )
        )
        fig.update_layout(height=300, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Risk components")
        comp_df = pd.DataFrame(
            [
                {"Component": k.replace("_", " ").title(), "Points": v}
                for k, v in risk["components"].items()
            ]
        )
        fig2 = px.bar(comp_df, x="Component", y="Points", labels={"Points": "Risk points"})
        fig2.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Trend forecast")
    fm = risk["forecast_moisture"]
    ft = risk["forecast_temp"]

    fcols = st.columns(2)
    with fcols[0]:
        st.markdown("**Moisture trend**")
        if fm:
            st.write(f"Slope: {fm['slope_per_day']:.3f} %/day")
            st.write(f"Current: {fm['current']:.2f}% | Limit: {fm['limit']:.2f}%")
            if fm["days_to_cross"] is not None:
                if fm["days_to_cross"] <= 0:
                    st.error("Moisture is already above the safe limit.")
                else:
                    st.warning(f"Estimated days until moisture crosses limit: {fm['days_to_cross']:.1f}")
            else:
                st.success("No upward moisture crossing estimated.")
        else:
            st.info("Not enough moisture readings for forecast.")

    with fcols[1]:
        st.markdown("**Temperature trend**")
        if ft:
            st.write(f"Slope: {ft['slope_per_day']:.3f} °C/day")
            st.write(f"Current: {ft['current']:.2f}°C | Limit: {ft['limit']:.2f}°C")
            if ft["days_to_cross"] is not None:
                if ft["days_to_cross"] <= 0:
                    st.error("Temperature is already above the safe limit.")
                else:
                    st.warning(f"Estimated days until temperature crosses limit: {ft['days_to_cross']:.1f}")
            else:
                st.success("No upward temperature crossing estimated.")
        else:
            st.info("Not enough temperature readings for forecast.")

    rdf = get_readings_df(risk["stock_id"])
    if not rdf.empty:
        rdf = rdf.copy()
        rdf["date"] = rdf["reading_date"].apply(lambda x: parse_dt(x).date() if parse_dt(x) else None)
        rdf = rdf.dropna(subset=["date"])

        chart_cols = st.columns(2)
        with chart_cols[0]:
            fig3 = px.line(rdf, x="date", y="moisture_pct", markers=True, labels={"moisture_pct": "Moisture %"})
            fig3.add_hline(y=risk["limit_moisture"], line_dash="dash", annotation_text="Limit")
            fig3.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig3, use_container_width=True)

        with chart_cols[1]:
            fig4 = px.line(rdf, x="date", y="temp_c", markers=True, labels={"temp_c": "Temperature °C"})
            fig4.add_hline(y=risk["limit_temp"], line_dash="dash", annotation_text="Limit")
            fig4.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig4, use_container_width=True)

    st.subheader("Action guidance")
    if not get_api_key():
        st.caption("No Gemini API key detected. Using built-in local guidance. The app remains fully functional.")

    cache = st.session_state.setdefault("action_cache", {})
    cache_key = f"{risk['stock_id']}|{lang}|{risk['score']}|{risk['latest_reading_date']}"

    if st.button("Regenerate AI guidance"):
        cache.pop(cache_key, None)

    if cache_key not in cache:
        cache[cache_key] = get_action_text(risk, lang)

    st.markdown(cache[cache_key])


def page_priority() -> None:
    st.header("Priority list across all units")
    lang = st.session_state.get("lang", "en")

    risks = get_all_risks()
    if not risks:
        st.info("No stocks found.")
        return

    rows = []
    for r in risks:
        code, pscore = priority_from_risk(r)
        rows.append(
            {
                "Unit": r["unit_name"],
                "Commodity": r["commodity"],
                "Quantity kg": r["quantity_kg"],
                "Value": r["stock_value"],
                "Entry date": r["entry_date"],
                "Expected sale": r["expected_sale_date"],
                "Days to sale": r["days_to_expected"],
                "Risk score": r["score"],
                "Level": tr(r["level"].lower(), lang),
                "Priority": tr(code, lang),
                "Priority score": pscore,
                "Moisture forecast days": forecast_days(r["forecast_moisture"]),
                "Temperature forecast days": forecast_days(r["forecast_temp"]),
            }
        )

    df = pd.DataFrame(rows).sort_values("Priority score", ascending=False)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.subheader("Priority chart")
    fig = px.bar(
        df,
        x="Unit",
        y="Priority score",
        color="Priority",
        barmode="group",
        labels={"Priority score": "Priority score"},
    )
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig, use_container_width=True)


def page_losses() -> None:
    st.header("Loss tracking")

    summary = get_loss_summary()
    c1, c2, c3, c4 = st.columns(4)
    kpi_card("Lost quantity", f"{summary['kg_lost']:,.1f} kg", "recorded losses", c1)
    kpi_card("Lost value", f"{summary['value_lost']:,.2f}", "recorded monetary loss", c2)
    kpi_card("Prevented quantity", f"{summary['prevented_kg']:,.1f} kg", "early-action estimate", c3)
    kpi_card("Prevented value", f"{summary['prevented_value']:,.2f}", "early-action estimate", c4)

    stocks = get_stocks()
    if stocks:
        sdf = pd.DataFrame(stocks)
        with st.form("add_loss_form"):
            stock_sel = st.selectbox(
                "Stock",
                sdf["id"].tolist(),
                format_func=lambda x: f'{sdf.loc[sdf["id"] == x, "unit_name"].values[0]} - {sdf.loc[sdf["id"] == x, "commodity"].values[0]} (#{x})',
                key="loss_stock",
            )
            event_date = st.date_input("Event date", dt.date.today())
            kg_lost = st.number_input("Kg lost", min_value=0.0, value=0.0, step=10.0)
            prevented_kg = st.number_input("Prevented kg (early action)", min_value=0.0, value=0.0, step=10.0)
            reason = st.text_input("Reason")
            submitted = st.form_submit_button("Save loss record")

            if submitted:
                if not reason.strip():
                    st.error("Reason is required.")
                elif kg_lost <= 0 and prevented_kg <= 0:
                    st.error("Enter either lost kg or prevented kg.")
                else:
                    stock = get_stock_by_id(int(stock_sel))
                    value_per_kg = safe_float(stock["value_per_kg"] if stock else 0.0, 0.0)
                    conn = get_conn()
                    conn.execute(
                        """
                        INSERT INTO losses
                        (stock_id, event_date, kg_lost, value_lost, reason, prevented_kg, prevented_value)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            int(stock_sel),
                            event_date.isoformat(),
                            kg_lost,
                            kg_lost * value_per_kg,
                            reason.strip(),
                            prevented_kg,
                            prevented_kg * value_per_kg,
                        ),
                    )
                    conn.commit()
                    conn.close()
                    st.success("Loss record saved.")
                    st.rerun()
    else:
        st.info("Add a stock to record losses.")

    st.subheader("Loss records")
    ldf = get_losses_df()
    if ldf.empty:
        st.caption("No loss records yet.")
    else:
        st.dataframe(ldf, use_container_width=True, hide_index=True)

        st.subheader("Loss summary by unit")
        grouped = ldf.groupby("unit_name").agg(
            kg_lost=("kg_lost", "sum"),
            value_lost=("value_lost", "sum"),
            prevented_kg=("prevented_kg", "sum"),
            prevented_value=("prevented_value", "sum"),
        ).reset_index()
        st.dataframe(grouped, use_container_width=True, hide_index=True)


def page_alerts() -> None:
    st.header("Alerts")
    sync_alerts()

    alerts = get_alerts()
    if not alerts:
        st.info("No alerts.")
        return

    adf = pd.DataFrame(alerts)
    adf["acknowledged_label"] = adf["acknowledged"].map({0: "No", 1: "Yes"})
    st.dataframe(
        adf[["created_at", "unit_name", "commodity", "level", "message", "acknowledged_label"]],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Acknowledge alert")
    unack = adf[adf["acknowledged"] == 0]
    if unack.empty:
        st.success("All alerts acknowledged.")
        return

    selected = st.selectbox(
        "Select unacknowledged alert",
        unack["id"].tolist(),
        format_func=lambda x: f'{unack.loc[unack["id"] == x, "unit_name"].values[0]} - {unack.loc[unack["id"] == x, "commodity"].values[0]}: {unack.loc[unack["id"] == x, "message"].values[0]}',
        key="alert_select",
    )

    prevented_kg = st.number_input("Optional: prevented kg due to early action", min_value=0.0, value=0.0, step=10.0)
    if st.button("Acknowledge selected alert"):
        alert_row = unack[unack["id"] == int(selected)].iloc[0]
        stock_id = int(alert_row["stock_id"])
        stock = get_stock_by_id(stock_id)
        value_per_kg = safe_float(stock["value_per_kg"] if stock else 0.0, 0.0)

        conn = get_conn()
        if prevented_kg > 0:
            conn.execute(
                """
                INSERT INTO losses
                (stock_id, event_date, kg_lost, value_lost, reason, prevented_kg, prevented_value)
                VALUES (?, ?, 0, 0, ?, ?, ?)
                """,
                (
                    stock_id,
                    dt.date.today().isoformat(),
                    "Early action prevented loss",
                    prevented_kg,
                    prevented_kg * value_per_kg,
                ),
            )
        conn.execute("UPDATE alerts SET acknowledged = 1 WHERE id = ?", (int(selected),))
        conn.commit()
        conn.close()
        st.success("Alert acknowledged.")
        st.rerun()


def page_reports() -> None:
    st.header("Weekly storage report")
    st.caption("Generates a PDF with risk per unit, trends, priority list, and loss tracking.")

    risks = get_all_risks()
    if not risks:
        st.info("No data available for report.")
        return

    preview = pd.DataFrame(
        [
            {
                "Unit": r["unit_name"],
                "Commodity": r["commodity"],
                "Score": r["score"],
                "Level": r["level"],
                "Moisture": r["moisture"],
                "Temp": r["temperature"],
                "RH": r["humidity"],
            }
            for r in risks
        ]
    )
    st.subheader("Preview")
    st.dataframe(preview, use_container_width=True, hide_index=True)

    if st.button("Generate weekly PDF"):
        with st.spinner("Generating PDF..."):
            st.session_state.weekly_pdf = generate_weekly_pdf()

    if "weekly_pdf" in st.session_state:
        st.download_button(
            label="Download weekly PDF",
            data=st.session_state.weekly_pdf,
            file_name=f"storeguard_weekly_{dt.date.today().isoformat()}.pdf",
            mime="application/pdf",
        )


def page_demo() -> None:
    st.header("Demo data and simulation")

    st.markdown(
        """
        - Demo data is loaded automatically if the database is empty.
        - The Dashboard includes a light live simulation that adds a new reading every ~20 seconds.
        - You can reset to a fresh demo dataset at any time.
        """
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Load demo data if empty"):
            seed_demo_data(force=False)
            st.success("Demo data check completed.")
            st.rerun()

    with c2:
        if st.button("Reset to fresh demo data"):
            reset_database()
            st.success("Fresh demo database created.")
            st.rerun()

    st.subheader("Simulation status")
    st.write(f"Live simulation enabled: **{st.session_state.get('sim_enabled', False)}**")
    st.write(f"Last simulation tick: **{st.session_state.get('last_sim_time', 0)}**")
    st.caption("Turn the simulation on/off from the sidebar.")


# ----------------------------------------------------------------------------
# Main app
# ----------------------------------------------------------------------------
def main() -> None:
    # Initialize database and auto-load demo data if needed
    init_db()
    seed_demo_data(force=False)

    # Sidebar
    st.sidebar.title("🌾 StoreGuard")
    lang_display = st.sidebar.selectbox(
        "AI language",
        list(LANG_DISPLAY_TO_CODE.keys()),
        index=0,
        key="lang_display",
    )
    st.session_state.lang = LANG_DISPLAY_TO_CODE.get(lang_display, "en")

    page = st.sidebar.radio("Menu", MENU, key="page")
    st.sidebar.checkbox("Live simulation", value=True, key="sim_enabled")

    if "last_sim_time" not in st.session_state:
        st.session_state.last_sim_time = time.time()

    if get_api_key():
        st.sidebar.success("Gemini API key detected.")
    else:
        st.sidebar.info("No Gemini API key detected. App still works with local fallback AI.")

    st.sidebar.caption("StoreGuard: manual entry, photos, CSV, SQLite, risk scoring, forecasts, PDF reports.")

    # Run light live simulation only on Dashboard to avoid disrupting forms
    simulation_tick()

    # Route
    if page == "Dashboard":
        page_dashboard()
    elif page == "Units":
        page_units()
    elif page == "Stocks":
        page_stocks()
    elif page == "Readings":
        page_readings()
    elif page == "Limits":
        page_limits()
    elif page == "Photos":
        page_photos()
    elif page == "Risk & Forecast":
        page_risk_forecast()
    elif page == "Priority":
        page_priority()
    elif page == "Losses":
        page_losses()
    elif page == "Alerts":
        page_alerts()
    elif page == "Reports":
        page_reports()
    elif page == "Demo Data":
        page_demo()
    else:
        page_dashboard()


if __name__ == "__main__":
    main()