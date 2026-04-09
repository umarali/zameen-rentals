"""Static data: area definitions, property types, and translations.

Areas are loaded from JSON files (scraped from Zameen.com via tools/deep_discover.py).
Supports multiple cities: Karachi, Lahore, Islamabad.
"""
import json
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent

# City definitions: name, Zameen.com ID, default lat/lng, area file
CITIES = {
    "karachi":   {"name": "Karachi",   "id": 2, "lat": 24.8607, "lng": 67.0011, "file": "areas.json"},
    "lahore":    {"name": "Lahore",    "id": 1, "lat": 31.5204, "lng": 74.3587, "file": "areas_lahore.json"},
    "islamabad": {"name": "Islamabad", "id": 3, "lat": 33.6844, "lng": 73.0479, "file": "areas_islamabad.json"},
}

def _load_areas(filename, city_name, city_id, default_lat, default_lng):
    p = _DATA_DIR / filename
    if not p.exists():
        return {city_name: (city_name, city_id, default_lat, default_lng)}
    with open(p) as f:
        raw = json.load(f)
    areas = {}
    for name, info in raw.items():
        areas[name] = (info["slug"], info["id"], info.get("lat", default_lat), info.get("lng", default_lng))
    if city_name not in areas:
        areas[city_name] = (city_name, city_id, default_lat, default_lng)
    return areas

# All city areas: {"karachi": {name: (slug, id, lat, lng), ...}, ...}
CITY_AREAS = {}
for _ck, _ci in CITIES.items():
    CITY_AREAS[_ck] = _load_areas(_ci["file"], _ci["name"], _ci["id"], _ci["lat"], _ci["lng"])

# Backwards compatibility
KARACHI_AREAS = CITY_AREAS["karachi"]

def get_areas(city="karachi"):
    """Get areas dict for a city."""
    return CITY_AREAS.get(city, CITY_AREAS["karachi"])

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

# Property type URL slugs used by the crawler (subset of PROPERTY_TYPES — only distinct slugs)
CRAWL_PROPERTY_TYPES = [
    # (slug, label) — label overrides property_type on crawled listings
    ("Rentals_Houses_Property", "House"),
    ("Rentals_Flats_Apartments", "Apartment / Flat"),
    ("Rentals_Upper_Portions", "Upper Portion"),
    ("Rentals_Lower_Portions", "Lower Portion"),
    ("Rentals_Rooms", "Room"),
]

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
    "ooper ka portion": "upper_portion", "ooper portion": "upper_portion",
    "upar ka portion": "upper_portion", "upar portion": "upper_portion",
    "uper ka portion": "upper_portion",
    "lower portion": "lower_portion", "nichla hissa": "lower_portion", "nichla": "lower_portion",
    "neechay ka portion": "lower_portion", "neechay portion": "lower_portion",
    "neeche ka portion": "lower_portion", "neeche portion": "lower_portion",
    "nichay ka portion": "lower_portion", "nichay portion": "lower_portion",
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
    "gulshan e iqbal block 1": "Gulshan-e-Iqbal Block 1", "gulshan block 1": "Gulshan-e-Iqbal Block 1",
    "gulshan e iqbal block 2": "Gulshan-e-Iqbal Block 2", "gulshan block 2": "Gulshan-e-Iqbal Block 2",
    "gulshan e iqbal block 4": "Gulshan-e-Iqbal Block 4", "gulshan block 4": "Gulshan-e-Iqbal Block 4",
    "gulshan e iqbal block 5": "Gulshan-e-Iqbal Block 5", "gulshan block 5": "Gulshan-e-Iqbal Block 5",
    "gulshan e iqbal block 7": "Gulshan-e-Iqbal Block 7", "gulshan block 7": "Gulshan-e-Iqbal Block 7",
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
    "falcon": "Falcon Complex Faisal", "falcon complex": "Falcon Complex Faisal",
    "gulshan e kaneez fatima": "Scheme 33 Gulshan-e-Kaneez Fatima",
    "kaneez fatima": "Scheme 33 Gulshan-e-Kaneez Fatima",
}

ROMAN_URDU_AREAS_LAHORE = {
    # DHA Lahore
    "dha": "DHA Defence", "defence": "DHA Defence", "defense": "DHA Defence",
    "dha lahore": "DHA Defence",
    "dha phase 1": "Defence  DHA  Phase 1", "dha 1": "Defence  DHA  Phase 1",
    "dha phase 2": "DHA Defence DHA Phase 2", "dha 2": "DHA Defence DHA Phase 2",
    "dha phase 3": "Defence  DHA  Phase 3", "dha 3": "Defence  DHA  Phase 3",
    "dha phase 4": "Defence  DHA  Phase 4", "dha 4": "Defence  DHA  Phase 4",
    "dha phase 5": "Defence  DHA  Phase 5", "dha 5": "Defence  DHA  Phase 5",
    "dha phase 6": "Defence  DHA  Phase 6", "dha 6": "Defence  DHA  Phase 6",
    "dha phase 7": "Defence  DHA  Phase 7", "dha 7": "Defence  DHA  Phase 7",
    "dha phase 8": "DHA Defence DHA Phase 8", "dha 8": "DHA Defence DHA Phase 8",
    "dha phase 9": "DHA Defence DHA Phase 9 Prism", "dha 9": "DHA Defence DHA Phase 9 Prism",
    "dha rahbar": "DHA 11 Rahbar",
    # Bahria
    "bahria": "Bahria Town", "bahria town": "Bahria Town", "bahria town lahore": "Bahria Town",
    "bahria orchard": "Bahria Orchard", "bahria nasheman": "Bahria Nasheman",
    # Gulberg
    "gulberg": "Gulberg", "gulberg lahore": "Gulberg",
    "gulberg 1": "Gulberg 1", "gulberg 2": "Gulberg 2", "gulberg 3": "Gulberg 3",
    "mm alam": "Gulberg", "mm alam road": "Gulberg",
    # Johar Town
    "johar": "Johar Town", "johar town": "Johar Town",
    "johar town phase 1": "Johar Town Phase 1", "johar town phase 2": "Johar Town Phase 2",
    # Model Town
    "model town": "Model Town", "model town lahore": "Model Town",
    # Garden Town
    "garden town": "Garden Town",
    # Allama Iqbal Town / Iqbal Town
    "iqbal town": "Allama Iqbal Town", "allama iqbal town": "Allama Iqbal Town",
    # Faisal Town
    "faisal town": "Faisal Town",
    # Township
    "township": "Township Sector A2",
    # Wapda Town
    "wapda town": "Wapda Town",
    # Cantt
    "cantt": "Cantt", "cant": "Cantt", "lahore cantt": "Cantt",
    # Askari
    "askari": "Askari", "askari 10": "Askari Askari 10", "askari 11": "Askari Askari 11",
    # Cavalry Ground
    "cavalry": "Cavalry Ground", "cavalry ground": "Cavalry Ground",
    # EME Society
    "eme": "EME Society", "eme society": "EME Society",
    # State Life
    "state life": "State Life Housing Society",
    # Samanabad
    "samanabad": "Samanabad",
    # Lake City
    "lake city": "Raiwind Road Lake City",
    # Valencia
    "valencia": "Valencia Housing Society",
    # Raiwind Road area
    "raiwind": "Raiwind Road",
    # Punjab Coop
    "punjab coop": "Punjab Co operative Housing Society",
}

ROMAN_URDU_AREAS_ISLAMABAD = {
    # DHA Islamabad
    "dha": "DHA Defence", "defence": "DHA Defence", "defense": "DHA Defence",
    "dha islamabad": "DHA Defence",
    "dha phase 1": "DHA Defence Phase 1", "dha phase 2": "DHA Defence Phase 2",
    # Bahria
    "bahria": "Bahria Town", "bahria town": "Bahria Town",
    "bahria town islamabad": "Bahria Town",
    "bahria enclave": "Bahria Town Bahria Enclave",
    # Gulberg
    "gulberg": "Gulberg", "gulberg greens": "Gulberg Gulberg Greens",
    "gulberg residencia": "Gulberg Gulberg Residencia",
    # Sector F (area file uses "F 6", "F 7", etc.)
    "f6": "F 6", "f-6": "F 6", "f 6": "F 6",
    "f7": "F 7", "f-7": "F 7", "f 7": "F 7",
    "f8": "F 8", "f-8": "F 8", "f 8": "F 8",
    "f10": "F 10", "f-10": "F 10", "f 10": "F 10",
    "f11": "F 11", "f-11": "F 11", "f 11": "F 11",
    # Sector G
    "g9": "G 9", "g-9": "G 9", "g 9": "G 9",
    "g10": "G 10", "g-10": "G 10", "g 10": "G 10",
    "g11": "G 11", "g-11": "G 11", "g 11": "G 11",
    "g13": "G 13", "g-13": "G 13", "g 13": "G 13",
    # Sector E
    "e11": "E 11", "e-11": "E 11", "e 11": "E 11",
    "e12": "E 12", "e-12": "E 12", "e 12": "E 12",
    # Sector I (note: "I  8" has double space in area file)
    "i8": "I  8", "i-8": "I  8", "i 8": "I  8",
    "i10": "I 10", "i-10": "I 10", "i 10": "I 10",
    "i14": "I 14", "i-14": "I 14", "i 14": "I 14",
    # Sector B/D/H
    "b17": "B 17", "b-17": "B 17", "b 17": "B 17",
    "d12": "D 12", "d-12": "D 12", "d 12": "D 12",
    "h13": "H 13", "h-13": "H 13", "h 13": "H 13",
    # Blue Area
    "blue area": "Blue Area",
    # CBR Town
    "cbr": "CBR Town", "cbr town": "CBR Town",
    # Soan Garden
    "soan garden": "Soan Garden", "soan": "Soan Garden",
    # PWD
    "pwd": "PWD Housing Scheme", "pwd housing": "PWD Housing Scheme",
    # Pakistan Town
    "pakistan town": "Pakistan Town",
    # Bani Gala
    "bani gala": "Bani Gala",
    # Chak Shahzad
    "chak shahzad": "Chak Shahzad",
}

# City-indexed Roman Urdu area lookup (for match_area and parse_natural_query)
ROMAN_URDU_AREAS_BY_CITY = {
    "karachi": ROMAN_URDU_AREAS,
    "lahore": ROMAN_URDU_AREAS_LAHORE,
    "islamabad": ROMAN_URDU_AREAS_ISLAMABAD,
}

# Famous landmarks → nearest available area (by city)
LANDMARKS = {
    "karachi": {
        "jinnah airport": "Cantt", "karachi airport": "Cantt",
        "aga khan hospital": "Saddar", "aga khan": "Saddar",
        "dow university": "Saddar",
        "dolmen mall clifton": "Clifton", "dolmen mall": "Clifton",
        "lucky one mall": "Gulshan-e-Iqbal",
        "ocean mall": "Clifton",
        "sea view": "Clifton", "seaview": "Clifton",
        "mazar e quaid": "Saddar", "quaid mausoleum": "Saddar",
        "safari park": "Gulshan-e-Iqbal",
        "port qasim": "Bin Qasim Town",
        "karachi zoo": "Saddar",
        "french beach": "Clifton",
    },
    "lahore": {
        "allama iqbal airport": "Cantt", "lahore airport": "Cantt",
        "lums": "DHA Defence", "lums university": "DHA Defence",
        "uet lahore": "Cantt", "uet": "Cantt",
        "ucp": "Johar Town",
        "punjab university": "Cantt",
        "fast lahore": "DHA Defence",
        "emporium mall": "Johar Town",
        "packages mall": "Gulberg",
        "fortress square": "Cantt",
        "liberty market": "Gulberg", "liberty": "Gulberg",
        "mm alam road": "Gulberg",
        "lahore fort": "Gulberg",
        "badshahi mosque": "Gulberg", "badshahi masjid": "Gulberg",
        "data darbar": "Gulberg",
        "kalma chowk": "Gulberg",
        "canal road": "Gulberg",
    },
    "islamabad": {
        "islamabad airport": "B 17", "new islamabad airport": "B 17",
        "nust": "H 13", "nust islamabad": "H 13",
        "quaid e azam university": "G 9", "qau": "G 9",
        "fast islamabad": "F 7",
        "comsats islamabad": "G 9",
        "centaurus mall": "F 8", "centaurus": "F 8",
        "giga mall": "DHA Defence",
        "jinnah super market": "F 7", "jinnah super": "F 7",
        "f7 markaz": "F 7", "f-7 markaz": "F 7",
        "faisal masjid": "F 8", "faisal mosque": "F 8",
        "pakistan monument": "F 7",
        "margalla hills": "F 6", "margalla": "F 6",
        "daman e koh": "F 6",
        "rawal lake": "G 9",
        "zero point": "G 9",
        "blue area": "Blue Area",
    },
}

USER_AGENTS = [
    # Chrome 145 (current stable, Mar 2026)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    # Chrome 144
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    # Chrome 143
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
    # Firefox 136 (current stable)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:136.0) Gecko/20100101 Firefox/136.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:136.0) Gecko/20100101 Firefox/136.0",
    # Firefox 135
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:135.0) Gecko/20100101 Firefox/135.0",
    # Safari 18 (macOS)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
    # Edge 145
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0",
    # Edge 144
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0",
    # Chrome on Android (mobile variant)
    "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Mobile Safari/537.36",
    # Safari on iPhone
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Mobile/15E148 Safari/604.1",
]
