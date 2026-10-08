"""Adversarial checks added during the 2026-10-08 audit."""
import asyncio
import pytest
import httpx
from app.decisions import parse_decision, DecisionError, JevClient
from app.listing_tags import save_tags, listings_needing_tags, listing_state
from app.db_listings import upsert_listing, search_listings
from test_listing_tags import _listing, _decision, _row
from tools.eval_listing_tags import score_rows

@pytest.mark.parametrize('value', [-0.1, 1.1, float('inf'), float('nan')])
def test_reject_invalid_probability(value):
    with pytest.raises(DecisionError):
        parse_decision({'answers': {'backup_power': {'type':'noul','noul':value}}})

@pytest.mark.parametrize('payload', [{'answers':[]}, {'answers':{'x':None}}, {'answers':{},'usage':{'input_tokens':'bad'}}])
def test_malformed_response_is_typed_error(payload):
    with pytest.raises(DecisionError):
        parse_decision(payload)

def test_invalid_json_is_typed_error():
    async def run():
        client=JevClient('test',client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,text='not json'))))
        try:
            with pytest.raises(DecisionError):
                await client.decide('synthetic',{})
        finally: await client.aclose()
    asyncio.run(run())

def test_description_edits_require_rescore():
    row=_listing('800001',description='Bachelors welcome. Solar installed.')
    save_tags(row,_decision())
    upsert_listing(zameen_id='800001',url=row['url'],city='lahore',detail_data={'description':'Families only. No solar or generator.'})
    assert [r['zameen_id'] for r in listings_needing_tags(limit=10)] == ['800001']

def test_stale_tags_do_not_filter_updated_listing():
    row=_listing('800002',description='Bachelors welcome. Solar installed.')
    save_tags(row,_decision())
    _listing('800002',description='Families only. No backup.',price=71000)
    result=search_listings(city='lahore',tenant='bachelor')
    assert result['total'] == 0

def test_negative_amenity_value_preserved():
    row=_listing('800003',description='Apartment.',amenities=[{'name':'Electricity Backup','value':'None'}])
    state=listing_state(row)
    assert 'Electricity Backup: None' in state or 'Amenities: Electricity Backup' not in state

def test_partial_gold_does_not_count_blank_as_negative():
    row={'zameen_id':'1','stratum':'tenant','stratum_population':'1','tenant_fit':'bachelor','backup_power':'','separate_entrance':'','newly_built':'','title':'Solar installed','description':'Bachelors welcome','amenities_json':'[]'}
    table,_,_=score_rows([row],{})
    assert table['backup_power']['keywords']['precision'] is None
