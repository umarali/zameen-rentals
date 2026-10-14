"""Readable source text and conservative, attributed listing highlights.

Computed on read for old and new listings. Never replaces stored source data or
structured property fields. Excerpts are quotations, not verified amenities.
"""
import re
from html import unescape
from functools import lru_cache

from bs4 import BeautifulSoup

_BLOCKS = ('p', 'div', 'section', 'article', 'h1', 'h2', 'h3', 'h4', 'blockquote', 'ul', 'ol', 'table', 'tr')
_WORDS = {'ground': 0, 'first': 1, 'second': 2, 'third': 3, 'fourth': 4,
          'fifth': 5, 'sixth': 6, 'seventh': 7, 'eighth': 8, 'ninth': 9,
          'tenth': 10, 'eleventh': 11, 'twelfth': 12}
_NUMBER = r'(?:ground|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|\d{1,2}(?:st|nd|rd|th)?)'
_FLOOR = re.compile(rf'\b({_NUMBER})\s+floor\b|\bfloor\s*(?:number|no\.?|level)?\s*[:#-]?\s*({_NUMBER})\b', re.I)
_TOPICS = (
    ('Floor & access', re.compile(r'\bfloors?\b|\blifts?\b|\belevators?\b|\bstairs?\b|\bwheelchair\b|منزل|لفٹ', re.I)),
    ('Parking', re.compile(r'\bparking\b|\bgarage\b|پارکنگ', re.I)),
    ('Utilities', re.compile(r'\bwater\b|\bgas\b|\belectricity\b|\bload\s*shedding\b|\bgenerator\b|\bsolar\b|پانی|بجلی|گیس', re.I)),
    ('Entrance', re.compile(r'\bentrance\b|\bentry\b', re.I)),
    ('Who can rent', re.compile(r'\bfamil(?:y|ies)\b|\bbachelors?\b|\bstudents?\b|\bpets?\b', re.I)),
    ('Costs & conditions', re.compile(r'\bdeposit\b|\badvance\b|\bmaintenance\b|\bcommission\b|\bnotice\b', re.I)),
)


def readable_description(value):
    if not isinstance(value, str) or not value.strip():
        return ''
    return _readable_text(value)


@lru_cache(maxsize=256)
def _readable_text(value):
    # Upstream sometimes encodes the entire markup. Decode before parsing so
    # even encoded script/style content is removed, never rendered as HTML.
    text = value
    for _ in range(2):
        decoded = unescape(text)
        if decoded == text:
            break
        text = decoded
    if '<' not in text:
        return _clean_whitespace(text)
    soup = BeautifulSoup(text, 'html.parser')
    for tag in soup(['script', 'style', 'template', 'svg', 'iframe', 'noscript']):
        tag.decompose()
    for tag in soup.find_all('br'):
        tag.replace_with('\n')
    for tag in soup.find_all('li'):
        tag.insert_before('\n• ')
        tag.insert_after('\n')
    for tag in soup.find_all(_BLOCKS):
        tag.insert_before('\n\n')
        tag.insert_after('\n\n')
    return _clean_whitespace(soup.get_text())


def _clean_whitespace(text):
    text = text.replace('\r', '\n')
    text = '\n'.join(re.sub(r'[^\S\n]+', ' ', line).strip() for line in text.split('\n'))
    text = re.sub(r'(• [^\n]+)\n+(?=• )', r'\1\n', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def _floor_label(value):
    value = str(value).strip().lower()
    if value in _WORDS:
        number = _WORDS[value]
    elif re.fullmatch(r'\d{1,2}(?:st|nd|rd|th)?', value):
        number = int(re.match(r'\d+', value)[0])
    else:
        return None
    if number == 0:
        return 'Ground floor'
    suffix = 'th' if 10 <= number % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th')
    return f'{number}{suffix} floor'


def _sentences(text):
    # Preserve the common floor-number abbreviation, including its full quote.
    return re.split(r'(?<![Nn][Oo]\.)(?<=[.!?۔])\s+|\n+', text)


def _floor_mentions(text, source):
    mentions = []
    for sentence in _sentences(text):
        # Do not collapse a compressed list/range into its last named floor.
        if re.search(rf'\b{_NUMBER}\s*(?:and|&|or|/|[-–—]|to|\+|,)\s*{_NUMBER}\s+floor\b', sentence, re.I):
            continue
        # Label-first ranges (Floor: 2-3) are equally ambiguous. Inspect the
        # whole sentence so another floor mention cannot hide that ambiguity.
        if any(m[2] and re.match(rf'\s*(?:and|&|or|/|[-–—]|to|\+|,)\s*{_NUMBER}\b(?!\s+floor\b)', sentence[m.end():], re.I)
               for m in _FLOOR.finditer(sentence)):
            continue
        for clause in re.split(r'[,;]', sentence):
            for match in _FLOOR.finditer(clause):
                before = clause[:match.start()].lower().strip(' •')
                after = clause[match.end():].lower()
                if source != 'listing field':
                    # Keep other subjects and exclusions out of the unit label.
                    if re.search(r'\b(?:owner|landlord|parking|garage|gym|shops?|office|lift|elevator|stairs|access|building)\b', before):
                        continue
                    if re.search(r'\b(?:owner|landlord|occupied|rented|not\s+(?:available|for\s+rent))\b', after):
                        continue
                    if re.match(r'\s*(?:building|tower|plaza|complex|block|parking|garage|rooftop|roof|commercial|shops?|gym)\b', after):
                        continue
                    if re.search(r'\b(?:not|no|except|excluding|without)\b', before):
                        continue
                    # A bare count describes storeys, unless explicitly on/at it.
                    if match[1] and re.fullmatch(r'\d+', match[1]) and not re.search(r'\b(?:on|at)(?:\s+the)?$', before):
                        continue
                    if match[1] and match[1].lower() == 'ground' and re.search(r'\b(?:lower|upper)$', before):
                        continue
                    explicit_label = match[2] is not None
                    if explicit_label and before and not re.match(r'floor\s*(?:[:#-]|number|no\.?|level)', match[0], re.I):
                        continue  # Marble floor 3 bedrooms is not Floor: 3.
                    standalone = not before or before in ('on', 'on the', 'at', 'at the')
                    listed_floors = bool(re.fullmatch(rf'(?:{_NUMBER}\s+floor\s*(?:and|&)\s*)+', before, re.I))
                    unit_context = bool(re.search(r'\b(?:flat|apartment|portion|unit)\b', before + after))
                    if not (explicit_label or standalone or listed_floors or unit_context):
                        continue
                label = _floor_label(match[1] or match[2])
                if label:
                    mentions.append({'label': label, 'source': source, 'text': sentence.strip(' •')})
    return mentions


def with_listing_insights(data, title=None, *, property_type=None, compact=False):
    """Return a presentation copy; an absent floor is never guessed."""
    out = dict(data)
    description = readable_description(data.get('description'))
    if 'description' in data:
        out['description'] = description
    mentions = []
    details = data.get('details') or {}
    if isinstance(details, dict):
        for key, value in details.items():
            if re.fullmatch(r'floor(?:\s*(?:number|no\.?|level))?', str(key).strip(), re.I):
                label = _floor_label(value)
                if label:
                    mentions.append({'label': label, 'source': 'listing field', 'text': f'{key}: {value}'})
                elif value is not None and str(value).strip().lower() not in ('', 'none', 'unknown', 'n/a', 'not specified', 'not stated', '--'):
                    raw = readable_description(str(value))
                    parsed = _floor_mentions(raw, 'listing field')
                    mentions.extend(parsed or [{'label': raw, 'source': 'listing field', 'text': f'{key}: {raw}'}])
    for value in data.get('amenities') or []:
        if isinstance(value, str) and re.match(r'^floor\s*[:#-]', value, re.I):
            raw = readable_description(re.split(r'[:#-]', value, maxsplit=1)[1]).strip()
            if raw and raw.lower() not in ('none', 'unknown', 'n/a', 'not specified', 'not stated', '--'):
                parsed = _floor_mentions(value, 'listing field')
                mentions.extend(parsed or [{'label': _floor_label(raw) or raw, 'source': 'listing field', 'text': readable_description(value)}])
    kind = str(property_type or data.get('property_type') or '').lower()
    whole_property = bool(re.search(r'\b(?:house|building|villa|farmhouse)\b', kind))
    if not whole_property:
        mentions.extend(_floor_mentions(readable_description(title or data.get('title')), 'title'))
        mentions.extend(_floor_mentions(description, 'description'))
    seen = set()
    unique = []
    for mention in mentions:
        key = (mention['label'], mention['source'])
        if key not in seen:
            seen.add(key)
            unique.append(mention)
    mentions = unique
    out['floor_mentions'] = mentions
    out['floor'] = None
    if mentions:
        different = len({m['label'] for m in mentions}) > 1
        out['floor'] = {'label': 'Multiple floors mentioned' if different else mentions[0]['label'],
                        'source': mentions[0]['source'], 'conflict': different}
    if compact:
        out.pop('floor_mentions', None)
        out.pop('description_highlights', None)
        if description:
            out['description'] = description[:2000]
        return out
    # Quote the complete sentence/line, retaining negation and qualifications.
    # No positive feature is inferred from merely finding a keyword.
    highlights = []
    for sentence in _sentences(description):
        sentence = sentence.strip(' •')
        if not sentence or len(sentence) > 500:
            continue  # Long unpunctuated text stays in the full description.
        topics = [name for name, pattern in _TOPICS if pattern.search(sentence)]
        if topics and not any(h['text'] == sentence for h in highlights):
            highlights.append({'topic': ' · '.join(topics), 'text': sentence})
    out['description_highlights'] = highlights[:12]
    return out
