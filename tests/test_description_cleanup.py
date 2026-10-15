"""Presentation cleanup must preserve source evidence and meaningful differences."""
import pytest
from fastapi.testclient import TestClient
from app import app
from app.db_listings import get_listing_by_zameen_id
from app.description_insights import with_listing_insights, readable_description
from tests.test_description_insights import seed, URL


def test_repeated_description_is_collapsed_on_read_with_full_text_available():
    raw = '<p>No lift available. No lift available. Water only at night.</p><script>bad()</script>'
    seed(raw)
    client = TestClient(app)
    result = client.get('/api/listing-detail', params={'url': URL}).json()
    assert result['description'] == 'No lift available. Water only at night.'
    assert result['description_original'] == 'No lift available. No lift available. Water only at night.'
    assert get_listing_by_zameen_id('910001')['description'] == raw
    # Normalization is also used by scraping. It must not discard repetition.
    assert readable_description(raw) == result['description_original']
    search = client.get('/api/search', params={'city': 'karachi', 'price_min': 49000}).json()['results'][0]
    assert search['description'] == result['description_original']
    assert 'description_original' not in search
    assert 'description_conflicts' not in search


@pytest.mark.parametrize(('source', 'expected'), [
    ('Parking available. Parking available. Parking available.', 'Parking available.'),
    ('<ul><li>No lift available. No lift available.</li></ul>', '• No lift available.'),
    ('No lift.\nNo lift.\nWater only at night.', 'No lift.\nWater only at night.'),
    ('<p>Two rooms. Separate entrance.</p><p>Two rooms. Separate entrance.</p>', 'Two rooms. Separate entrance.'),
    ('Floor No. 3. Floor No. 3. No lift.', 'Floor No. 3. No lift.'),
    ('No lift available.\n\nNo lift available.\nWater only at night.', 'No lift available.\n\nWater only at night.'),
])
def test_exact_adjacent_repeats(source, expected):
    result = with_listing_insights({'description': source})
    assert result['description'] == expected
    assert result['description_original'] == readable_description(source)


@pytest.mark.parametrize('source', [
    'Ground floor:\nTwo bedrooms.\nFirst floor:\nTwo bedrooms.',
    'Water available. Water available at night only.',
    'No parking. Parking available.',
    'Rent 50,000. Deposit 50,000.',
    'Call 03001234567. WhatsApp 03001234567.',
    'Lift available? Lift available.',
    'Water available. Gas available. Water available.',
    'No. No.',
    '1. 1.',
    '• Bedroom with attached bath\n• Bedroom with attached bath',
    '• Water only at night.\n• Water only at night.\n• Separate entrance.',
])
def test_different_or_contextual_text_is_not_silently_removed(source):
    result = with_listing_insights({'description': source})
    assert result['description'] == source
    assert 'description_original' not in result


def test_opposing_availability_statements_remain_quotes_not_corrected_facts():
    seed('Lift available. No lift available. No lift available. Water only at night.')
    result = TestClient(app).get('/api/listing-detail', params={'url': URL}).json()
    assert result['description_conflicts'] == [
        {'topic': 'Lift', 'statements': ['Lift available.', 'No lift available.']}
    ]
    assert result['description'] == 'Lift available. No lift available. Water only at night.'
    assert result['description_original'].count('No lift available.') == 2
    assert [h['text'] for h in result['description_highlights']] == ['Water only at night.']


@pytest.mark.parametrize('source', [
    'Lift available upstairs. No lift available downstairs.',
    'No lift available before repairs. Lift available now.',
    'Lift available? No lift available.',
    'Water available. No gas available.',
    'No parking restrictions. Parking available.',
    'No water shortage. Water available.',
    'Lift not available until Friday. Lift available.',
    'Water available. Water available.',
])
def test_qualifications_questions_and_different_subjects_are_not_conflicts(source):
    assert with_listing_insights({'description': source})['description_conflicts'] == []


@pytest.mark.parametrize(('source', 'topic'), [
    ('Parking is available. Parking is not available.', 'Parking'),
    ('Gas available. Gas unavailable.', 'Gas'),
    ('No water. Water available.', 'Water'),
    ('Electricity not available. Electricity available.', 'Electricity'),
    ('Elevator available. No lift.', 'Lift'),
])
def test_explicit_opposing_statements(source, topic):
    result = with_listing_insights({'description': source})
    assert result['description_conflicts'][0]['topic'] == topic
    assert len(result['description_conflicts'][0]['statements']) == 2


def test_multiple_conflicting_topics_and_more_than_two_quotes():
    result = with_listing_insights({'description':
        'Lift available. No lift. No lift available. Water available. No water.'})
    assert result['description_conflicts'] == [
        {'topic': 'Lift', 'statements': ['Lift available.', 'No lift.', 'No lift available.']},
        {'topic': 'Water', 'statements': ['Water available.', 'No water.']},
    ]
    assert result['description_highlights'] == []


@pytest.mark.parametrize('marker', ['-', '*', '•', '• ', '– ', '— ', '+ ', '1. ', '1) '])
def test_typed_list_rows_can_enumerate_separate_rooms(marker):
    row = marker + 'Bedroom with attached bath'
    result = with_listing_insights({'description': row + '\n' + row})
    assert result['description'] == row + '\n' + row
    assert 'description_original' not in result
