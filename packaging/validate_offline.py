"""Container-only offline acceptance: no embedding/generation/network fallback."""
import hashlib
import json
from pathlib import Path
import time
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch


def phase(label):
    memory=Path('/sys/fs/cgroup/memory.current')
    peak=Path('/sys/fs/cgroup/memory.peak')
    row={'phase':label,'memory_mib':int(memory.read_text())/1024**2 if memory.exists() else None,
         'peak_mib':int(peak.read_text())/1024**2 if peak.exists() else None}
    print(json.dumps(row),flush=True)
    time.sleep(5)


base=Path('/opt/realtyai/runtime_assets')
manifest=json.loads((base/'manifest.json').read_text())
def verify():
    for name,entry in manifest.items():
        assert hashlib.sha256((base/name).read_bytes()).hexdigest()==entry['sha256'],name
verify()
phase('validation_start')
with patch('socket.socket.connect',side_effect=AssertionError('No external network allowed')), \
     patch('requests.Session.send',side_effect=AssertionError('No HTTP API allowed')), \
     patch('app.chatbot.EmbeddingClient') as embed, \
     patch('app.chatbot.Generator.generate',side_effect=AssertionError('No generation allowed')) as generate:
    from app.chatbot import Chatbot,Retrieval
    from app.property_search import load_properties
    retrieval=Retrieval()
    assert retrieval.store.count()==1709
    assert len(retrieval.store.ids())==1709
    phase('chroma_loaded_verified')
    records=load_properties(base/'listings.jsonl');assert len(records)==261
    bot=Chatbot(retrieval=retrieval,records=records)
    known=bot.answer('Show listing 5891036');row=known['properties']['matches'][0]
    assert (row['price_sar'],row['area_sqm'],row['bedrooms'],row['bathrooms'])==(120000,250,9,6)
    assert row['source_url'].startswith('https://wasalt.sa/en/property/')
    missing=bot.answer('Show listing 99999999')
    assert not missing['sources'] and missing['properties']['total_matches']==0
    assert 'live Wasalt website' in missing['answer']
    villas=bot.answer('Villas for rent in Riyadh under SAR 100000/year')
    assert villas['properties']['total_matches']==8
    generate.assert_not_called();embed.return_value.embed_query.assert_not_called()
    phase('wasalt_queries_complete')
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app/streamlit_app.py')).run(timeout=60)
    assert not app.exception and app.title[0].value=='RealtyAI'
    app.chat_input[0].set_value('Show listing 5891036').run(timeout=60)
    assert not app.exception
    assert any('Listing 5891036' in item.value for item in app.markdown)
    generate.assert_not_called();embed.return_value.embed_query.assert_not_called()
    verify()
    phase('ui_card_complete_assets_unchanged')
print(json.dumps({'status':'passed','chroma_records':1709,'wasalt_records':261,'external_api_calls':0}),flush=True)
