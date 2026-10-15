"""Description presentation is derived on read; stored source evidence stays intact."""
from fastapi.testclient import TestClient
from app import app
from app.db_listings import upsert_listing, get_listing_by_zameen_id

URL = 'https://www.zameen.com/Property/test-910001-1-1.html'


def seed(description, details=None, amenities=None, title='Rental apartment'):
    upsert_listing(zameen_id='910001', url=URL, city='karachi',
                   card_data={'title': title, 'price': 50000, 'property_type': 'Apartment'})
    upsert_listing(zameen_id='910001', url=URL, city='karachi', detail_data={'description': description, 'details': details or {},
                                'amenities': amenities or [], 'latitude': 24.8,
                                'longitude': 67.0, 'location_source': 'listing_exact'})


def test_existing_stored_html_is_readable_in_search_and_detail_without_rewriting_source():
    raw = '<p>Apartment on the <b>third floor</b>.</p><ul><li>No lift available.</li><li>Separate entrance &amp; parking.</li></ul><script>alert(1)</script>'
    seed(raw)
    client = TestClient(app)
    detail = client.get('/api/listing-detail', params={'url': URL}).json()
    search = client.get('/api/search', params={'city': 'karachi', 'price_min': 49000}).json()['results'][0]
    for result in (detail, search):
        assert result['description'] == 'Apartment on the third floor.\n\n• No lift available.\n• Separate entrance & parking.'
        assert result['floor']['label'] == '3rd floor'
        assert result['floor']['source'] == 'description'
    assert any('No lift available.' in h['text'] for h in detail['description_highlights'])
    assert get_listing_by_zameen_id('910001')['description'] == raw


def test_floor_disagreement_retains_both_sources():
    seed('Apartment on the third floor.', details={'Floor': '2'})
    client = TestClient(app)
    result = client.get('/api/listing-detail', params={'url': URL}).json()
    assert result['floor']['conflict'] is True
    assert {(m['label'], m['source']) for m in result['floor_mentions']} == {('2nd floor', 'listing field'), ('3rd floor', 'description')}


import pytest
from app.description_insights import readable_description, with_listing_insights


@pytest.mark.parametrize(('raw', 'expected'), [
    ('&lt;p&gt;Water &amp;amp; gas&lt;/p&gt;&lt;script&gt;bad()&lt;/script&gt;', 'Water & gas'),
    ('<p>One <strong>large</strong> room<br>Two baths</p><p>Next paragraph</p>', 'One large room\nTwo baths\n\nNext paragraph'),
    ('Rent < 50000 & deposit > 0', 'Rent < 50000 & deposit > 0'),
    ('<div>Safe<img src=x onerror=alert(1)><style>bad</style><iframe>bad</iframe></div>', 'Safe'),
])
def test_plain_text_preserves_readability_without_active_markup(raw, expected):
    assert readable_description(raw) == expected


@pytest.mark.parametrize('description', [
    'A 5 floor building with an upper portion.', 'Ground floor parking.',
    'Lift till the third floor.', 'Not on the second floor.',
    'Apartment in a 12-storey building.', 'Upper portion with rooftop access.',
])
def test_does_not_guess_unit_floor(description):
    assert with_listing_insights({'description': description})['floor'] is None


@pytest.mark.parametrize(('description', 'label'), [
    ('Ground floor apartment.', 'Ground floor'), ('Flat on 21st floor.', '21st floor'),
    ('Floor: 2', '2nd floor'), ('First floor, no lift.', '1st floor'),
])
def test_explicit_floor_mentions(description, label):
    assert with_listing_insights({'description': description})['floor']['label'] == label


def test_multiple_floors_are_ambiguous_not_a_single_floor():
    result = with_listing_insights({'description': 'Ground floor and first floor available.'})
    assert result['floor']['conflict'] is True
    assert {m['label'] for m in result['floor_mentions']} == {'Ground floor', '1st floor'}


def test_quotes_preserve_negation_and_qualifications():
    description = 'Lift not available. Water only at night. No parking. Families only; no bachelors.'
    result = with_listing_insights({'description': description})
    assert [h['text'] for h in result['description_highlights']] == ['Lift not available.', 'Water only at night.', 'No parking.', 'Families only; no bachelors.']


def test_structured_floor_and_title_without_description():
    assert with_listing_insights({'amenities': ['Floor: 4']})['floor']['label'] == '4th floor'
    assert with_listing_insights({'title': '2nd floor apartment'})['floor']['source'] == 'title'
    assert with_listing_insights({'details': {'Number of floors': '5'}})['floor'] is None


def test_new_crawl_keeps_floor_beyond_old_description_cutoff():
    from app.scraper import detail_from_state
    description = ('Spacious room. ' * 170) + 'Apartment on third floor.'
    import json
    html = '<script>window.state = ' + json.dumps({'property': {'data': {'description': description}}}) + ';</script>'
    result = detail_from_state(html)
    assert result['description'].endswith('Apartment on third floor.')


@pytest.mark.parametrize('description', [
    'Upper portion for rent, owner lives on ground floor.',
    'Parking on ground floor.', 'Gym on 5th floor.', 'Shops on ground floor.',
    'Lift up to 8th floor.', 'Stairs to 3rd floor.', 'Ground floor not available.',
])
def test_other_subjects_and_unavailable_floors_do_not_label_unit(description):
    assert with_listing_insights({'description': description})['floor'] is None


def test_house_layout_remains_in_description_without_a_unit_floor_claim():
    result = with_listing_insights({'property_type': 'House', 'description': 'Ground floor: drawing, kitchen. First floor: 3 beds.'})
    assert result['floor'] is None
    assert result['description_highlights']


@pytest.mark.parametrize('value', ['Basement', 'Lower Ground', 'Mezzanine', 'Penthouse', 'Top'])
def test_unrecognized_structured_floor_is_preserved_and_conflict_visible(value):
    result = with_listing_insights({'details': {'Floor': value}, 'description': 'Apartment on third floor.'})
    assert result['floor']['conflict'] is True
    assert any(m['source'] == 'listing field' and value in m['text'] for m in result['floor_mentions'])


def test_floor_number_abbreviation_is_not_split():
    result = with_listing_insights({'description': 'Floor No. 3. No lift.'})
    assert result['floor']['label'] == '3rd floor'
    assert result['description_highlights'][0]['text'] == 'Floor No. 3.'


def test_list_payload_stays_compact_but_reads_floor_after_old_cutoff():
    seed('Spacious room. ' * 170 + 'Apartment on third floor.')
    client = TestClient(app)
    result = client.get('/api/search', params={'city': 'karachi', 'price_min': 49000}).json()['results'][0]
    assert result['floor']['label'] == '3rd floor'
    assert len(result['description']) <= 2000
    assert 'description_highlights' not in result
    assert 'floor_mentions' not in result


def test_floor_amenity_retains_non_numeric_value():
    result = with_listing_insights({'amenities': ['Floor: Basement'], 'description': 'Apartment on third floor.'})
    assert result['floor']['conflict'] is True
    assert result['floor_mentions'][0]['label'] == 'Basement'


def test_map_and_nearby_use_real_sqlite_projection(monkeypatch):
    import app.routes as routes
    async def no_enrichment(**kwargs):
        return False
    monkeypatch.setattr(routes, '_maybe_enrich_nearby_exact_locations', no_enrichment)
    seed('Apartment on third floor.')
    client = TestClient(app)
    for endpoint, params in [
        ('map-search', {'south': 24.7, 'north': 24.9, 'west': 66.9, 'east': 67.1}),
        ('nearby-search', {'lat': 24.8, 'lng': 67.0, 'radius_km': 1}),
    ]:
        response = client.get('/api/' + endpoint, params={'city': 'karachi', **params})
        assert response.status_code == 200
        result = response.json()['results'][0]
        assert result['floor']['label'] == '3rd floor'
        assert 'description_highlights' not in result


def test_projection_without_details_json_does_not_fail():
    from app.db_listings import _row_to_listing
    seed('Apartment on third floor.')
    row = get_listing_by_zameen_id('910001')
    row.pop('details_json')
    assert _row_to_listing(row)['floor']['label'] == '3rd floor'


@pytest.mark.parametrize('description', [
    'Apartment, not on the ground floor.', 'Flat available except ground floor.',
    'Ground floor owner occupied, upper portion for rent.',
    'Marble floor 3 bedrooms, 2 baths.', 'Basement floor 2 rooms.',
    'Apartment in a 10 floor tower.', 'Apartment in a 10 floor plaza.',
])
def test_negation_counts_and_materials_do_not_become_a_unit_floor(description):
    assert with_listing_insights({'description': description})['floor'] is None


@pytest.mark.parametrize('description', [
    'Ground floor is not available, first floor for rent.',
    'Ground floor already rented, first floor available.',
])
def test_qualifying_floor_after_excluded_clause_is_preserved(description):
    result = with_listing_insights({'description': description})
    assert result['floor']['label'] == '1st floor'
    assert result['floor']['conflict'] is False


def test_uppercase_floor_abbreviation():
    assert with_listing_insights({'description': 'Floor NO. 3.'})['floor']['label'] == '3rd floor'


def test_live_house_detail_uses_card_context_without_a_database_row(monkeypatch):
    import app.routes as routes
    async def live_detail(url):
        return {'description': 'Ground floor: drawing, kitchen. First floor: 3 beds.'}
    monkeypatch.setattr(routes, 'fetch_listing_detail', live_detail)
    result = TestClient(app).get('/api/listing-detail', params={'url': URL, 'property_type': 'House'}).json()
    assert result['floor'] is None
    assert result['description_highlights']


@pytest.mark.parametrize('description', [
    'No ground floor apartment available.', 'Not a ground floor flat.',
    'Apartment available except for ground floor.',
])
def test_negation_with_intervening_words_does_not_become_a_floor(description):
    result = with_listing_insights({'description': description})
    assert result['floor'] is None
    assert result['description_highlights']


@pytest.mark.parametrize('description', [
    'Flat available on 1st and 2nd floor.', 'Apartment on 2nd or 3rd floor.',
    'Flats on 2nd & 3rd floor.', 'Ground and first floor portion.',
    'Flat on 1st floor, 2nd or 3rd floor.',
])
def test_compressed_floor_lists_stay_quoted_instead_of_becoming_one_floor(description):
    result = with_listing_insights({'description': description})
    assert result['floor'] is None
    assert result['description_highlights'][0]['text'] == description


@pytest.mark.parametrize('description', [
    'Floor: 2-3.', 'Floor: 2nd & 3rd.', 'Floor No. 2/3.',
    'Floor: 2-3, Floor: 4.', 'Floor: 2–3.', 'Floor: 2—3.', 'Floor: 2,3.',
])
def test_label_first_floor_ranges_are_not_reduced_to_one_floor(description):
    assert with_listing_insights({'description': description})['floor'] is None


def test_amenity_floor_range_preserves_the_whole_value():
    assert with_listing_insights({'amenities': ['Floor: 2-3']})['floor']['label'] == '2-3'


@pytest.mark.parametrize(('field', 'text', 'expected'), [
    ('description', 'Apartment on 3rd floor, 2 bedrooms.', '3rd floor'),
    ('title', '2nd Floor - 3 Bed Apartment', '2nd floor'),
])
def test_unit_floor_followed_by_room_count_remains_identified(field, text, expected):
    assert with_listing_insights({field: text})['floor']['label'] == expected
