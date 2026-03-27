"""
RentKarachi — Fast Zameen.com rental search API + web app.
Run: uvicorn main:app --reload --port 8000
Open: http://localhost:8000
"""
from dotenv import load_dotenv
load_dotenv()

import asyncio, hashlib, json, logging, os, random, re, time
from difflib import SequenceMatcher
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urlencode
import anthropic
import httpx
import instructor
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("zameenrentals")
app = FastAPI(title="ZameenRentals", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

KARACHI_AREAS = {
    # --- DHA Defence ---
    "DHA Defence": ("Karachi_DHA_Defence", 213, 24.8007, 67.0531),
    "DHA Phase 1": ("Karachi_DHA_Defence_DHA_Phase_1", 1478, 24.8120, 67.0380),
    "DHA Phase 2": ("Karachi_DHA_Defence_DHA_Phase_2", 1479, 24.8080, 67.0480),
    "DHA Phase 2 Extension": ("Karachi_DHA_Defence_DHA_Phase_2_Extension", 1672, 24.8050, 67.0610),
    "DHA Phase 3": ("Karachi_DHA_Defence_DHA_Phase_3", 1480, 24.8040, 67.0550),
    "DHA Phase 4": ("Karachi_DHA_Defence_DHA_Phase_4", 1481, 24.7980, 67.0590),
    "DHA Phase 5": ("Karachi_DHA_Defence_DHA_Phase_5", 1482, 24.7920, 67.0650),
    "DHA Phase 6": ("Karachi_DHA_Defence_DHA_Phase_6", 1483, 24.7850, 67.0720),
    "DHA Phase 7": ("Karachi_DHA_Defence_DHA_Phase_7", 1673, 24.7780, 67.0780),
    "DHA Phase 7 Extension": ("Karachi_DHA_Defence_DHA_Phase_7_Extension", 1674, 24.7720, 67.0830),
    "DHA Phase 8": ("Karachi_DHA_Defence_DHA_Phase_8", 7294, 24.7660, 67.0880),
    "DHA City Karachi": ("Karachi_DHA_City_Karachi", 1429, 24.7790, 67.3160),
    # --- Clifton ---
    "Clifton": ("Karachi_Clifton", 5, 24.8200, 67.0280),
    "Clifton Block 2": ("Karachi_Clifton_Block_2", 1664, 24.8220, 67.0320),
    "Clifton Block 3": ("Karachi_Clifton_Block_3", 1665, 24.8200, 67.0310),
    "Clifton Block 4": ("Karachi_Clifton_Block_4", 1666, 24.8190, 67.0300),
    "Clifton Block 5": ("Karachi_Clifton_Block_5", 1667, 24.8210, 67.0290),
    "Clifton Block 6": ("Karachi_Clifton_Block_6", 1668, 24.8230, 67.0270),
    "Clifton Block 7": ("Karachi_Clifton_Block_7", 1669, 24.8240, 67.0260),
    "Clifton Block 8": ("Karachi_Clifton_Block_8", 1670, 24.8250, 67.0240),
    "Clifton Block 9": ("Karachi_Clifton_Block_9", 1671, 24.8260, 67.0220),
    "Sea View Apartments": ("Karachi_Sea_View_Apartments", 7292, 24.8190, 67.0230),
    "Boat Basin": ("Karachi_Boat_Basin", 6738, 24.8210, 67.0270),
    # --- Gulshan / Gulistan ---
    "Gulshan-e-Iqbal": ("Karachi_Gulshan_e_Iqbal", 233, 24.9180, 67.0920),
    "Gulshan-e-Iqbal Town": ("Karachi_Gulshan_e_Iqbal_Town", 6858, 24.9200, 67.0900),
    "Gulistan-e-Jauhar": ("Karachi_Gulistan_e_Jauhar", 232, 24.9240, 67.1180),
    "Gulistan-e-Jauhar Block 1": ("Karachi_Gulistan_e_Jauhar_Block_1", 6823, 24.9250, 67.1200),
    "Gulistan-e-Jauhar Block 2": ("Karachi_Gulistan_e_Jauhar_Block_2", 6825, 24.9270, 67.1220),
    "Gulberg": ("Karachi_Gulberg", 231, 24.8910, 67.0810),
    "Gulshan-e-Maymar": ("Karachi_Gulshan_e_Maymar", 440, 25.0100, 67.0840),
    "Gulshan-e-Hadeed": ("Karachi_Gulshan_e_Hadeed", 234, 24.8330, 67.3530),
    # --- Bahria ---
    "Bahria Town Karachi": ("Karachi_Bahria_Town_Karachi", 8298, 24.9600, 67.3400),
    # --- Nazimabad ---
    "North Nazimabad": ("Karachi_North_Nazimabad", 11, 24.9420, 67.0360),
    "North Nazimabad Block A": ("Karachi_North_Nazimabad_Block_A", 7209, 24.9440, 67.0380),
    "North Nazimabad Block H": ("Karachi_North_Nazimabad_Block_H", 7216, 24.9460, 67.0340),
    "Nazimabad": ("Karachi_Nazimabad", 278, 24.9340, 67.0340),
    "Naya Nazimabad": ("Karachi_Naya_Nazimabad", 10079, 24.9490, 67.0520),
    # --- Central ---
    "Federal B Area": ("Karachi_Federal_B._Area", 12, 24.9260, 67.0340),
    "North Karachi": ("Karachi_North_Karachi", 282, 24.9650, 67.0480),
    "Saddar": ("Karachi_Saddar_Town", 7269, 24.8560, 67.0180),
    "PECHS": ("Karachi_PECHS", 283, 24.8680, 67.0620),
    "Bahadurabad": ("Karachi_Bahadurabad", 6730, 24.8810, 67.0560),
    "Tariq Road": ("Karachi_Tariq_Road", 532, 24.8760, 67.0640),
    "Liaquatabad": ("Karachi_Liaquatabad", 260, 24.9100, 67.0400),
    "Mehmoodabad": ("Karachi_Mehmoodabad", 7158, 24.8580, 67.0720),
    "Karimabad": ("Karachi_Karimabad", 6949, 24.9210, 67.0370),
    "PIB Colony": ("Karachi_PIB_Colony", 7236, 24.8840, 67.0510),
    # --- Garden / Jamshed ---
    "Garden West": ("Karachi_Garden_West", 10984, 24.8720, 67.0380),
    "Garden East": ("Karachi_Garden_East", 6805, 24.8700, 67.0420),
    "Jamshed Town": ("Karachi_Jamshed_Town", 6916, 24.8750, 67.0560),
    # --- Faisal ---
    "Shah Faisal Town": ("Karachi_Shah_Faisal_Town", 774, 24.8690, 67.1070),
    "Shahra-e-Faisal": ("Karachi_Shahra_e_Faisal", 310, 24.8610, 67.0780),
    "Shaheed-e-Millat Road": ("Karachi_Shaheed_e_Millat_Road", 7282, 24.8690, 67.0570),
    "Karsaz": ("Karachi_Karsaz", 6943, 24.8720, 67.0890),
    # --- Cantonment ---
    "Cantt": ("Karachi_Cantt", 525, 24.8580, 67.0470),
    "Askari 5": ("Karachi_Askari_5", 6726, 24.8550, 67.0710),
    "Defence View": ("Karachi_Defence_View", 6788, 24.8650, 67.0920),
    # --- South-west ---
    "Frere Town": ("Karachi_Frere_Town", 224, 24.8440, 67.0230),
    "Bath Island": ("Karachi_Bath_Island", 198, 24.8340, 67.0230),
    "Gizri": ("Karachi_Gizri", 6809, 24.8120, 67.0410),
    "Old Clifton": ("Karachi_Old_Clifton", 9052, 24.8240, 67.0290),
    "Zamzama": ("Karachi_Zamzama", 416, 24.8140, 67.0340),
    # --- South-east / Malir ---
    "Malir": ("Karachi_Malir", 476, 24.8860, 67.1870),
    "Korangi": ("Karachi_Korangi", 255, 24.8400, 67.1360),
    "Landhi": ("Karachi_Landhi", 258, 24.8700, 67.2270),
    "Model Colony": ("Karachi_Model_Colony", 277, 24.8530, 67.1280),
    "Saadi Town": ("Karachi_Saadi_Town", 7271, 24.8800, 67.1360),
    "Scheme 33": ("Karachi_Scheme_33", 495, 24.8950, 67.1710),
    "Safoora Goth": ("Karachi_Safoora_Goth", 7273, 24.9150, 67.1420),
    # --- Hill / University ---
    "Hill Park": ("Karachi_Hill_Park", 758, 24.8700, 67.0570),
    "University Road": ("Karachi_University_Road", 324, 24.9190, 67.1050),
    # --- Buffer Zone / Surjani ---
    "Buffer Zone": ("Karachi_Buffer_Zone", 6748, 24.9550, 67.0550),
    "Surjani Town": ("Karachi_Surjani_Town", 303, 24.9780, 67.0120),
    # --- West Karachi ---
    "Orangi Town": ("Karachi_Orangi_Town", 285, 24.9460, 67.0080),
    "Baldia Town": ("Karachi_Baldia_Town", 6734, 24.9310, 66.9960),
    "Lyari": ("Karachi_Lyari", 262, 24.8680, 67.0100),
    "Kemari": ("Karachi_Keamari_Town", 7098, 24.8460, 66.9850),
    # --- Remote ---
    "Gadap Town": ("Karachi_Gadap_Town", 6803, 25.0700, 67.1500),
    "Bin Qasim Town": ("Karachi_Bin_Qasim_Town", 6740, 24.8350, 67.3200),
    # --- Overall ---
    "Karachi": ("Karachi", 2, 24.8607, 67.0011),
}

PROPERTY_TYPES = {
    "house": {"label": "House", "slug": "Rentals_Houses_Property"},
    "apartment": {"label": "Apartment / Flat", "slug": "Rentals_Flats_Apartments"},
    "flat": {"label": "Apartment / Flat", "slug": "Rentals_Flats_Apartments"},
    "upper_portion": {"label": "Upper Portion", "slug": "Rentals_Upper_Portions"},
    "lower_portion": {"label": "Lower Portion", "slug": "Rentals_Lower_Portions"},
    "room": {"label": "Room", "slug": "Rentals_Rooms"},
    "penthouse": {"label": "Penthouse", "slug": "Rentals_Penthouse"},
    "farm_house": {"label": "Farm House", "slug": "Rentals_Farm_Houses"},
}

URDU_AREAS = {
    "ڈی ایچ اے": "DHA Defence",
    "ڈی ایچ اے فیز 1": "DHA Phase 1",
    "ڈی ایچ اے فیز 2": "DHA Phase 2",
    "ڈی ایچ اے فیز 2 ایکسٹینشن": "DHA Phase 2 Extension",
    "ڈی ایچ اے فیز 3": "DHA Phase 3",
    "ڈی ایچ اے فیز 4": "DHA Phase 4",
    "ڈی ایچ اے فیز 5": "DHA Phase 5",
    "ڈی ایچ اے فیز 6": "DHA Phase 6",
    "ڈی ایچ اے فیز 7": "DHA Phase 7",
    "ڈی ایچ اے فیز 7 ایکسٹینشن": "DHA Phase 7 Extension",
    "ڈی ایچ اے فیز 8": "DHA Phase 8",
    "ڈی ایچ اے سٹی": "DHA City Karachi",
    "کلفٹن": "Clifton",
    "کلفٹن بلاک 2": "Clifton Block 2",
    "کلفٹن بلاک 3": "Clifton Block 3",
    "کلفٹن بلاک 4": "Clifton Block 4",
    "کلفٹن بلاک 5": "Clifton Block 5",
    "کلفٹن بلاک 6": "Clifton Block 6",
    "کلفٹن بلاک 7": "Clifton Block 7",
    "کلفٹن بلاک 8": "Clifton Block 8",
    "کلفٹن بلاک 9": "Clifton Block 9",
    "سی ویو اپارٹمنٹس": "Sea View Apartments",
    "بوٹ بیسن": "Boat Basin",
    "گلشن اقبال": "Gulshan-e-Iqbal",
    "گلشن اقبال ٹاؤن": "Gulshan-e-Iqbal Town",
    "گلستان جوہر": "Gulistan-e-Jauhar",
    "گلستان جوہر بلاک 1": "Gulistan-e-Jauhar Block 1",
    "گلستان جوہر بلاک 2": "Gulistan-e-Jauhar Block 2",
    "گلبرگ": "Gulberg",
    "گلشن معمار": "Gulshan-e-Maymar",
    "گلشن حدید": "Gulshan-e-Hadeed",
    "بحریہ ٹاؤن": "Bahria Town Karachi",
    "نارتھ ناظم آباد": "North Nazimabad",
    "نارتھ ناظم آباد بلاک اے": "North Nazimabad Block A",
    "نارتھ ناظم آباد بلاک ایچ": "North Nazimabad Block H",
    "ناظم آباد": "Nazimabad",
    "نیا ناظم آباد": "Naya Nazimabad",
    "فیڈرل بی ایریا": "Federal B Area",
    "نارتھ کراچی": "North Karachi",
    "صدر": "Saddar",
    "پی ای سی ایچ ایس": "PECHS",
    "بہادر آباد": "Bahadurabad",
    "طارق روڈ": "Tariq Road",
    "لیاقت آباد": "Liaquatabad",
    "محمود آباد": "Mehmoodabad",
    "کریم آباد": "Karimabad",
    "پی آئی بی کالونی": "PIB Colony",
    "گارڈن ویسٹ": "Garden West",
    "گارڈن ایسٹ": "Garden East",
    "جمشید ٹاؤن": "Jamshed Town",
    "شاہ فیصل ٹاؤن": "Shah Faisal Town",
    "شاہراہ فیصل": "Shahra-e-Faisal",
    "شہید ملت روڈ": "Shaheed-e-Millat Road",
    "کارساز": "Karsaz",
    "کینٹ": "Cantt",
    "عسکری 5": "Askari 5",
    "ڈیفینس ویو": "Defence View",
    "فریئر ٹاؤن": "Frere Town",
    "باتھ آئی لینڈ": "Bath Island",
    "گزری": "Gizri",
    "اولڈ کلفٹن": "Old Clifton",
    "زم زمہ": "Zamzama",
    "ملیر": "Malir",
    "کورنگی": "Korangi",
    "لانڈھی": "Landhi",
    "ماڈل کالونی": "Model Colony",
    "سعدی ٹاؤن": "Saadi Town",
    "اسکیم 33": "Scheme 33",
    "صفورا گوٹھ": "Safoora Goth",
    "ہل پارک": "Hill Park",
    "یونیورسٹی روڈ": "University Road",
    "بفر زون": "Buffer Zone",
    "سرجانی ٹاؤن": "Surjani Town",
    "اورنگی ٹاؤن": "Orangi Town",
    "بلدیہ ٹاؤن": "Baldia Town",
    "لیاری": "Lyari",
    "کیماری": "Kemari",
    "گڈاپ ٹاؤن": "Gadap Town",
    "بن قاسم ٹاؤن": "Bin Qasim Town",
    "کراچی": "Karachi",
}

# Reverse lookup: English name -> Urdu name
_ENGLISH_TO_URDU = {v: k for k, v in URDU_AREAS.items()}

ROMAN_URDU_TYPES = {
    "house": "house", "ghar": "house", "makan": "house", "makaan": "house",
    "apartment": "apartment", "flat": "apartment", "flaat": "apartment",
    "upper portion": "upper_portion", "bala hissa": "upper_portion", "uper portion": "upper_portion", "bala": "upper_portion",
    "lower portion": "lower_portion", "nichla hissa": "lower_portion", "nichla": "lower_portion",
    "room": "room", "kamra": "room",
    "penthouse": "penthouse", "pent house": "penthouse",
    "farm house": "farm_house", "farmhouse": "farm_house",
    "portion": "upper_portion",
}

URDU_TYPES = {
    "گھر": "house", "مکان": "house",
    "فلیٹ": "apartment", "اپارٹمنٹ": "apartment",
    "بالا حصہ": "upper_portion", "اوپر والا حصہ": "upper_portion",
    "نچلا حصہ": "lower_portion", "نیچے والا حصہ": "lower_portion",
    "کمرہ": "room",
    "پینٹ ہاؤس": "penthouse",
    "فارم ہاؤس": "farm_house",
}

ROMAN_URDU_AREAS = {
    "dha": "DHA Defence", "defence": "DHA Defence", "defense": "DHA Defence",
    "dha phase 1": "DHA Phase 1", "dha 1": "DHA Phase 1",
    "dha phase 2": "DHA Phase 2", "dha 2": "DHA Phase 2",
    "dha phase 3": "DHA Phase 3", "dha 3": "DHA Phase 3",
    "dha phase 4": "DHA Phase 4", "dha 4": "DHA Phase 4",
    "dha phase 5": "DHA Phase 5", "dha 5": "DHA Phase 5",
    "dha phase 6": "DHA Phase 6", "dha 6": "DHA Phase 6",
    "dha phase 7": "DHA Phase 7", "dha 7": "DHA Phase 7",
    "dha phase 8": "DHA Phase 8", "dha 8": "DHA Phase 8",
    "dha city": "DHA City Karachi",
    "clifton": "Clifton", "klifton": "Clifton",
    "boat basin": "Boat Basin",
    "gulshan": "Gulshan-e-Iqbal", "gulshan e iqbal": "Gulshan-e-Iqbal", "gulshan iqbal": "Gulshan-e-Iqbal",
    "johar": "Gulistan-e-Jauhar", "jauhar": "Gulistan-e-Jauhar", "gulistan e johar": "Gulistan-e-Jauhar", "gulistan e jauhar": "Gulistan-e-Jauhar",
    "gulberg": "Gulberg",
    "gulshan e maymar": "Gulshan-e-Maymar", "maymar": "Gulshan-e-Maymar",
    "gulshan e hadeed": "Gulshan-e-Hadeed", "hadeed": "Gulshan-e-Hadeed",
    "bahria": "Bahria Town Karachi", "bahria town": "Bahria Town Karachi",
    "nazimabad": "Nazimabad", "naazimabad": "Nazimabad",
    "north nazimabad": "North Nazimabad", "n nazimabad": "North Nazimabad",
    "naya nazimabad": "Naya Nazimabad",
    "north karachi": "North Karachi",
    "saddar": "Saddar", "sadar": "Saddar",
    "pechs": "PECHS", "pecs": "PECHS",
    "bahadurabad": "Bahadurabad",
    "tariq road": "Tariq Road",
    "liaquatabad": "Liaquatabad", "liyaqat abad": "Liaquatabad",
    "mehmoodabad": "Mehmoodabad", "mahmoodabad": "Mehmoodabad",
    "karimabad": "Karimabad",
    "pib colony": "PIB Colony", "pib": "PIB Colony",
    "fb area": "Federal B Area", "federal b area": "Federal B Area",
    "garden": "Garden West", "garden west": "Garden West",
    "garden east": "Garden East",
    "shah faisal": "Shah Faisal Town",
    "shahra e faisal": "Shahra-e-Faisal",
    "shaheed e millat": "Shaheed-e-Millat Road", "millat road": "Shaheed-e-Millat Road",
    "karsaz": "Karsaz",
    "cantt": "Cantt", "cant": "Cantt",
    "askari": "Askari 5", "askari 5": "Askari 5",
    "defence view": "Defence View",
    "bath island": "Bath Island",
    "frere town": "Frere Town",
    "gizri": "Gizri",
    "zamzama": "Zamzama",
    "old clifton": "Old Clifton",
    "sea view": "Sea View Apartments",
    "malir": "Malir", "mallir": "Malir",
    "korangi": "Korangi",
    "landhi": "Landhi", "landi": "Landhi",
    "model colony": "Model Colony",
    "saadi town": "Saadi Town",
    "scheme 33": "Scheme 33",
    "safoora": "Safoora Goth", "safoora goth": "Safoora Goth",
    "hill park": "Hill Park",
    "university road": "University Road",
    "buffer zone": "Buffer Zone",
    "surjani": "Surjani Town", "surjani town": "Surjani Town",
    "orangi": "Orangi Town", "orangi town": "Orangi Town",
    "baldia": "Baldia Town", "baldia town": "Baldia Town",
    "lyari": "Lyari",
    "kemari": "Kemari", "keamari": "Kemari",
    "gadap": "Gadap Town", "gadap town": "Gadap Town",
    "bin qasim": "Bin Qasim Town",
}


def _parse_price_token(text):
    """Parse a price value from text like '50k', '50000', '1.5lac', '2lakh', '50 hazar'."""
    text = text.strip().lower().replace(',', '')
    m = re.match(r'([\d.]+)\s*(?:lac|lakh|lacs|laakh)', text)
    if m: return int(float(m.group(1)) * 100_000)
    m = re.match(r'([\d.]+)\s*(?:k|hazar|hazaar)', text)
    if m: return int(float(m.group(1)) * 1_000)
    m = re.match(r'([\d.]+)\s*(?:crore|cr)', text)
    if m: return int(float(m.group(1)) * 10_000_000)
    m = re.match(r'[\d.]+', text)
    if m:
        v = float(m.group(0))
        if v <= 500: return int(v * 1_000)  # "50" likely means 50k
        return int(v)
    return None


def parse_natural_query(query: str) -> dict:
    """Parse a natural language rental query into structured filters.
    Supports English, Roman Urdu, and Urdu script."""
    result = {}
    q = query.strip()
    if not q:
        return result
    ql = q.lower()

    # --- Furnished ---
    if re.search(r'\b(?:furnished|furnish|فرنشڈ|فرنش)\b', q, re.I):
        result['furnished'] = True
        ql = re.sub(r'\b(?:furnished|furnish)\b', ' ', ql, flags=re.I)

    # --- Sort ---
    if re.search(r'\b(?:cheapest|sasta|سستا|cheap|affordable|budget)\b', q, re.I):
        result['sort'] = 'price_low'
    elif re.search(r'\b(?:expensive|mehenga|مہنگا|luxury|premium)\b', q, re.I):
        result['sort'] = 'price_high'
    elif re.search(r'\b(?:newest|latest|naya|نیا|new|recent)\b', q, re.I):
        result['sort'] = 'newest'

    # --- Bedrooms ---
    # English/Roman: "2 bed", "3 bedroom", "1br", "studio", "1 bhk", "2 kamre"
    m = re.search(r'(\d+)\s*(?:bed(?:room)?s?|br|bhk|kamr[eao]|کمر[ےوں]|بیڈ)', ql)
    if m:
        result['bedrooms'] = min(int(m.group(1)), 10)
    elif re.search(r'\b(?:studio|اسٹوڈیو)\b', q, re.I):
        result['bedrooms'] = 1

    # --- Property type (Urdu script first) ---
    for ur_type, key in sorted(URDU_TYPES.items(), key=lambda x: -len(x[0])):
        if ur_type in q:
            result['property_type'] = key
            break
    if 'property_type' not in result:
        # Roman Urdu / English type matching (longest first to match "upper portion" before "portion")
        for alias, key in sorted(ROMAN_URDU_TYPES.items(), key=lambda x: -len(x[0])):
            if re.search(r'\b' + re.escape(alias) + r'\b', ql):
                result['property_type'] = key
                break

    # --- Price ---
    # Range: "50k-100k", "50k to 100k", "50k se 100k"
    m = re.search(r'([\d.]+\s*(?:k|lac|lakh|lacs|laakh|hazar|hazaar|crore|cr)?)\s*(?:-|to|se|سے|تک)\s*([\d.]+\s*(?:k|lac|lakh|lacs|laakh|hazar|hazaar|crore|cr)?)', ql)
    if m:
        pmin = _parse_price_token(m.group(1))
        pmax = _parse_price_token(m.group(2))
        if pmin is not None: result['price_min'] = pmin
        if pmax is not None: result['price_max'] = pmax
    else:
        # "under/below/max/tak 50k", "50k ke andar", "50k se kam"
        m = re.search(r'(?:under|below|max|upto|up\s*to|tak|تک|andar|kam|کم|se\s*kam|سے\s*کم|ke\s*andar)\s*([\d.]+\s*(?:k|lac|lakh|lacs|laakh|hazar|hazaar|crore|cr)?)', ql)
        if m:
            pmax = _parse_price_token(m.group(1))
            if pmax is not None: result['price_max'] = pmax
        else:
            m = re.search(r'([\d.]+\s*(?:k|lac|lakh|lacs|laakh|hazar|hazaar|crore|cr)?)\s*(?:ke\s*andar|se\s*kam|tak|تک|کم)', ql)
            if m:
                pmax = _parse_price_token(m.group(1))
                if pmax is not None: result['price_max'] = pmax

        # "above/over/min 100k", "100k se zyada"
        m2 = re.search(r'(?:above|over|min(?:imum)?|from|zyada|زیادہ|se\s*zyada|سے\s*زیادہ)\s*([\d.]+\s*(?:k|lac|lakh|lacs|laakh|hazar|hazaar|crore|cr)?)', ql)
        if m2:
            pmin = _parse_price_token(m2.group(1))
            if pmin is not None: result['price_min'] = pmin
        elif not m:
            m2 = re.search(r'([\d.]+\s*(?:k|lac|lakh|lacs|laakh|hazar|hazaar|crore|cr)?)\s*(?:se\s*zyada|سے\s*زیادہ|plus|\+)', ql)
            if m2:
                pmin = _parse_price_token(m2.group(1))
                if pmin is not None: result['price_min'] = pmin

    # --- Area ---
    # Urdu script areas (check first since they're unambiguous)
    for ur_area, en_area in sorted(URDU_AREAS.items(), key=lambda x: -len(x[0])):
        if ur_area in q:
            result['area'] = en_area
            break
    if 'area' not in result:
        # Roman Urdu / English area aliases (longest first)
        for alias, area_name in sorted(ROMAN_URDU_AREAS.items(), key=lambda x: -len(x[0])):
            if re.search(r'\b' + re.escape(alias) + r'\b', ql):
                result['area'] = area_name
                break
    if 'area' not in result:
        # Fallback: try matching against KARACHI_AREAS keys
        for name in sorted(KARACHI_AREAS.keys(), key=lambda x: -len(x)):
            if name.lower() in ql:
                result['area'] = name
                break

    return result


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.5 Safari/605.1.15",
]

_cache = {}
CACHE_TTL = 300

def _cache_key(**kw):
    return hashlib.md5(json.dumps(kw, sort_keys=True).encode()).hexdigest()

def _cache_get(key):
    if key in _cache:
        ts, data = _cache[key]
        if time.time() - ts < CACHE_TTL: return data
        del _cache[key]
    return None

def _cache_set(key, data):
    _cache[key] = (time.time(), data)
    if len(_cache) > 200:
        for k in sorted(_cache, key=lambda k: _cache[k][0])[:50]: del _cache[k]

class RateLimiter:
    def __init__(self, rate=2.0, burst=3):
        self.rate, self.burst, self.tokens, self.last = rate, burst, float(burst), time.monotonic()
        self._lock = asyncio.Lock()
    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            self.tokens = min(self.burst, self.tokens + (now - self.last) * self.rate)
            self.last = now
            if self.tokens < 1:
                await asyncio.sleep((1 - self.tokens) / self.rate)
                self.tokens = 0
            else: self.tokens -= 1

rate_limiter = RateLimiter()

def match_area(query):
    q = query.strip()
    # Check Urdu names first (exact then partial)
    for ur, en in URDU_AREAS.items():
        if ur == q: return en
    for ur, en in URDU_AREAS.items():
        if q in ur or ur in q: return en
    q = q.lower()
    for name in KARACHI_AREAS:
        if name.lower() == q: return name
    for name in KARACHI_AREAS:
        if q in name.lower() or name.lower() in q: return name
    qt = set(re.findall(r'\w+', q))
    best, best_score = None, 0
    for name in KARACHI_AREAS:
        score = len(qt & set(re.findall(r'\w+', name.lower())))
        if score > best_score: best_score, best = score, name
    if best_score >= 1: return best
    best, best_ratio = None, 0.0
    for name in KARACHI_AREAS:
        r = SequenceMatcher(None, q, name.lower()).ratio()
        if r > best_ratio: best_ratio, best = r, name
    return best if best_ratio >= 0.5 else None

def parse_price(text):
    if not text: return None
    text = text.strip().replace(",","").replace("PKR","").replace("Rs.","").replace("Rs","").strip()
    m = re.search(r'([\d.]+)\s*crore', text, re.I)
    if m: return int(float(m.group(1)) * 10_000_000)
    m = re.search(r'([\d.]+)\s*la(?:kh|c)', text, re.I)
    if m: return int(float(m.group(1)) * 100_000)
    m = re.search(r'([\d.]+)\s*thousand', text, re.I)
    if m: return int(float(m.group(1)) * 1_000)
    m = re.search(r'[\d.]+', text)
    return int(float(m.group(0))) if m else None

def build_url(area=None, property_type=None, bedrooms=None, price_min=None, price_max=None, furnished=None, page=1, sort=None):
    ptype_slug = "Rentals"
    if property_type and property_type.lower() in PROPERTY_TYPES:
        ptype_slug = PROPERTY_TYPES[property_type.lower()]["slug"]
    area_slug, area_id = "Karachi", 2
    if area:
        matched = match_area(area)
        if matched: area_slug, area_id = KARACHI_AREAS[matched][:2]
    url = f"https://www.zameen.com/{ptype_slug}/{area_slug}-{area_id}-{page}.html"
    params = {}
    if bedrooms is not None: params["beds_in"] = str(bedrooms)
    if price_min is not None: params["price_min"] = str(price_min)
    if price_max is not None: params["price_max"] = str(price_max)
    if furnished: params["furnishing"] = "furnished"
    if sort:
        sm = {"price_low":"price_asc","price_high":"price_desc","newest":"date_desc"}
        if sort in sm: params["sort"] = sm[sort]
    if params: url += "?" + urlencode(params)
    return url

async def fetch_page(url, client):
    for attempt in range(3):
        try:
            await rate_limiter.acquire()
            headers = {"User-Agent": random.choice(USER_AGENTS), "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9", "Accept-Encoding": "gzip, deflate, br", "Connection": "keep-alive"}
            resp = await client.get(url, headers=headers, timeout=15, follow_redirects=True)
            if resp.status_code == 200: return resp.text
            elif resp.status_code == 429:
                await asyncio.sleep((2**attempt) + random.uniform(1,3))
            else:
                logger.warning(f"HTTP {resp.status_code} for {url}")
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Fetch error: {e}")
            await asyncio.sleep(2**attempt)
    return None

def parse_listings(html):
    soup = BeautifulSoup(html, "html.parser")
    listings = []
    cards = soup.select('li[role="article"]') or soup.select('[class*="listing-card"], article[aria-label]')
    for card in cards:
        listing = {}
        h2 = card.select_one("h2")
        if h2:
            a = h2.select_one("a")
            listing["title"] = (a or h2).get_text(strip=True)
            if a and a.get("href"):
                href = a["href"]
                if not href.startswith("http"): href = "https://www.zameen.com" + href
                listing["url"] = href
        if not listing.get("url"):
            a = card.select_one('a[href*="/Property/"]') or card.select_one("a[href]")
            if a:
                href = a["href"]
                if not href.startswith("http"): href = "https://www.zameen.com" + href
                listing["url"] = href
                if not listing.get("title"): listing["title"] = a.get_text(strip=True)
        price_el = card.select_one('span[aria-label="Price"]') or card.select_one('[class*="price"]')
        if price_el:
            listing["price_text"] = price_el.get_text(strip=True)
            listing["price"] = parse_price(listing["price_text"])
        for label, key in [("Beds","bedrooms"),("Baths","bathrooms")]:
            el = card.select_one(f'span[aria-label="{label}"]')
            if el:
                m = re.search(r'(\d+)', el.get_text(strip=True))
                if m: listing[key] = int(m.group(1))
        area_el = card.select_one('span[aria-label="Area"]')
        if area_el: listing["area_size"] = area_el.get_text(strip=True)
        loc_el = card.select_one('span[aria-label="Location"]')
        if loc_el:
            listing["location"] = loc_el.get_text(strip=True)
        else:
            for span in card.select("span, div"):
                t = span.get_text(strip=True)
                if ("DHA" in t or "Commercial" in t or "Karachi" in t or "Block" in t) and 5 < len(t) < 80 and "Thousand" not in t and "sqft" not in t:
                    listing["location"] = t; break
        img = card.select_one("img[src*='zameen'], img[data-src]")
        if img: listing["image_url"] = img.get("src") or img.get("data-src","")
        for span in card.select("span"):
            t = span.get_text(strip=True).lower()
            if "added" in t or "ago" in t: listing["added"] = span.get_text(strip=True); break
        if listing.get("title") or listing.get("price"): listings.append(listing)
    if not listings:
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data] if isinstance(data, dict) and data.get("@type") in ("RealEstateListing","Product","Offer") else [i.get("item",i) for i in data.get("itemListElement",[])] if isinstance(data, dict) else []
                for item in items:
                    l = {"title": item.get("name",""), "url": item.get("url","")}
                    if "offers" in item:
                        offer = item["offers"] if isinstance(item["offers"], dict) else item["offers"][0]
                        l["price"] = parse_price(str(offer.get("price","")))
                        l["price_text"] = str(offer.get("price",""))
                    if l.get("title"): listings.append(l)
            except: continue
    return listings

async def search_zameen(area=None, property_type=None, bedrooms=None, price_min=None, price_max=None, furnished=None, page=1, sort=None):
    ck = _cache_key(area=area, property_type=property_type, bedrooms=bedrooms, price_min=price_min, price_max=price_max, furnished=furnished, page=page, sort=sort)
    cached = _cache_get(ck)
    if cached: return cached
    url = build_url(area, property_type, bedrooms, price_min, price_max, furnished, page, sort)
    logger.info(f"Fetching: {url}")
    async with httpx.AsyncClient() as client:
        html = await fetch_page(url, client)
    if not html: raise HTTPException(status_code=502, detail="Could not fetch results from Zameen.com. Try again shortly.")
    listings = parse_listings(html)
    total = len(listings)
    soup = BeautifulSoup(html, "html.parser")
    count_el = soup.select_one('h1, [class*="count"], [class*="total"]')
    if count_el:
        m = re.search(r'(\d[\d,]*)\s+(?:Flats?|Homes?|Houses?|Properties|Rooms?|Portions?|Penthouses?)', count_el.get_text())
        if m: total = int(m.group(1).replace(",",""))
    result = {"total": total, "page": page, "url": url, "results": listings}
    _cache_set(ck, result)
    return result

@app.get("/api/health")
async def health(): return {"status": "ok", "service": "ZameenRentals", "version": "1.0.0"}

@app.get("/api/areas")
async def get_areas():
    return [{"name": n, "slug": s, "id": i, "lat": lat, "lng": lng, "name_ur": _ENGLISH_TO_URDU.get(n, "")} for n, (s, i, lat, lng) in sorted(KARACHI_AREAS.items())]

@app.get("/api/property-types")
async def get_property_types():
    seen, types = set(), []
    for key, info in PROPERTY_TYPES.items():
        if key == "flat": continue
        if info["slug"] not in seen: seen.add(info["slug"]); types.append({"key": key, "label": info["label"]})
    return types

class RentalFilters(BaseModel):
    """Structured rental search filters extracted from a natural language query."""
    area: Optional[str] = Field(None, description="Area name in Karachi (use exact English name from available list)")
    property_type: Optional[Literal["house", "apartment", "upper_portion", "lower_portion", "room", "penthouse", "farm_house"]] = Field(None, description="Property type key")
    bedrooms: Optional[int] = Field(None, ge=1, le=10, description="Number of bedrooms")
    price_min: Optional[int] = Field(None, ge=0, description="Minimum price in PKR")
    price_max: Optional[int] = Field(None, ge=0, description="Maximum price in PKR")
    furnished: Optional[bool] = Field(None, description="Whether the property must be furnished")
    sort: Optional[Literal["price_low", "price_high", "newest"]] = Field(None, description="Sort order")


_NLQ_SYSTEM = """You extract Karachi rental search filters from natural language queries.
The user may write in English, Roman Urdu (Urdu in Latin script), or Urdu script.

AVAILABLE AREAS: {areas}

Price shorthand: 50k=50000, 1.5lac=150000, 2lakh=200000, 50hazar=50000.
Roman Urdu: ghar=house, flat/apartment=apartment, bala hissa=upper_portion, nichla hissa=lower_portion, kamra=room, sasta=price_low, mehenga=price_high, naya=newest.
Urdu: گھر=house, فلیٹ=apartment, بالا حصہ=upper_portion, نچلا حصہ=lower_portion, کمرہ=room, فرنشڈ=furnished.

Only include fields you are confident about. Omit anything not mentioned."""

_instructor_client = None

def _get_instructor_client():
    global _instructor_client
    if _instructor_client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        _instructor_client = instructor.from_anthropic(anthropic.Anthropic(api_key=api_key))
    return _instructor_client


async def parse_query_with_claude(query: str) -> dict:
    """Use Instructor + Claude Haiku to parse a natural language rental query."""
    client = _get_instructor_client()
    if client is None:
        return parse_natural_query(query)

    cache_key = _cache_key(nlq=query)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    areas_list = ", ".join(sorted(KARACHI_AREAS.keys()))

    try:
        filters = await asyncio.to_thread(
            client.messages.create,
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=_NLQ_SYSTEM.format(areas=areas_list),
            messages=[{"role": "user", "content": query}],
            response_model=RentalFilters,
        )
        result = filters.model_dump(exclude_none=True)
        # Validate area name against known areas
        if "area" in result and result["area"] not in KARACHI_AREAS:
            matched = match_area(result["area"])
            result["area"] = matched if matched else result.pop("area", None)
            if result.get("area") is None:
                result.pop("area", None)

        _cache_set(cache_key, result)
        return result
    except Exception as e:
        logger.warning(f"Instructor parse failed, falling back to regex: {e}")
        return parse_natural_query(query)


@app.get("/api/parse-query")
async def api_parse_query(q: str = Query(..., min_length=1)):
    result = await parse_query_with_claude(q)
    return {"query": q, "filters": result}


@app.get("/api/search")
async def search(area: Optional[str]=Query(None), property_type: Optional[str]=Query(None), bedrooms: Optional[int]=Query(None, ge=1, le=10), price_min: Optional[int]=Query(None, ge=0), price_max: Optional[int]=Query(None, ge=0), furnished: Optional[bool]=Query(None), page: int=Query(1, ge=1), sort: Optional[str]=Query(None)):
    try: return await search_zameen(area=area, property_type=property_type, bedrooms=bedrooms, price_min=price_min, price_max=price_max, furnished=furnished, page=page, sort=sort)
    except HTTPException: raise
    except Exception as e: logger.error(f"Search error: {e}"); raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def serve_frontend():
    p = Path(__file__).parent / "index.html"
    return FileResponse(p, media_type="text/html") if p.exists() else HTMLResponse("<h1>RentKarachi</h1><p>index.html not found</p>")

if __name__ == "__main__":
    import uvicorn; uvicorn.run(app, host="0.0.0.0", port=8000)
