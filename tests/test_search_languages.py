"""English and Urdu search acceptance checks, including the no-key fallback."""
import asyncio

import pytest

from app import parsing
from app.data import URDU_AREAS_BY_CITY, get_areas
from app.routes import _build_parse_query_response


@pytest.mark.parametrize('city,english,urdu,expected', [
    ('karachi','2 bed flat in Clifton under 50k','کلفٹن میں ۲ کمروں کا فلیٹ ۵۰ ہزار تک',
     {'area':'Clifton','bedrooms':2,'property_type':'apartment','price_max':50000}),
    ('lahore','2 bed flat in Gulberg under 50k','گلبرگ میں دو کمروں کا فلیٹ پچاس ہزار تک',
     {'area':'Gulberg','bedrooms':2,'property_type':'apartment','price_max':50000}),
    ('islamabad','2 bed flat in F-10 under 50k','ایف ۱۰ میں ۲ کمروں کا فلیٹ ۵۰ ہزار تک',
     {'area':'F 10','bedrooms':2,'property_type':'apartment','price_max':50000}),
    ('lahore','5 marla house in Johar Town under 1 lakh','جوہر ٹاؤن میں پانچ مرلہ گھر ایک لاکھ تک',
     {'area':'Johar Town','size_marla_min':5,'property_type':'house','price_max':100000}),
    ('karachi','120 gaz house in Clifton','کلفٹن میں ۱۲۰ گز گھر',
     {'area':'Clifton','size_marla_min':4.8,'property_type':'house'}),
    ('lahore','2-3 bed flat in Gulberg','گلبرگ میں ۲ سے ۳ کمروں کا فلیٹ',
     {'area':'Gulberg','bedrooms':2,'bedrooms_max':3,'property_type':'apartment'}),
])
def test_english_urdu_equivalence_without_claude(monkeypatch,city,english,urdu,expected):
    monkeypatch.setattr(parsing,'_get_instructor_client',lambda:None)
    for query in (english,urdu):
        result=asyncio.run(parsing.parse_query_with_claude(query,city))
        assert {key:result.get(key) for key in expected} == expected
        response=_build_parse_query_response(query,city,result)
        assert not response['filters'].get('area_approximate')


def test_urdu_aliases_target_real_city_areas():
    for city,aliases in URDU_AREAS_BY_CITY.items():
        assert set(aliases.values()) <= set(get_areas(city))


@pytest.mark.parametrize('query',['کلفٹن','بنی گالا','ایف ۱۰'])
def test_other_city_urdu_names_do_not_match_lahore(query):
    assert parsing.match_area(query,'lahore') is None
