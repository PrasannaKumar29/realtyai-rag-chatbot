"""Run from the repository root with python -m streamlit run app/streamlit_app.py."""
import sys
from uuid import uuid4
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import streamlit as st
from app.chatbot import Chatbot, SNAPSHOT, arabic
from app.presentation import captured_date, filter_question, property_card, property_summary

st.set_page_config(page_title='RealtyAI', page_icon='🏙️', layout='centered')

# Only application-owned, documented st.container key classes are styled.
# No widget internals, JavaScript, downloaded fonts or external assets.
st.html("""<style>
.st-key-realty_header { padding-block: 0.25rem 0.75rem; }
.st-key-realty_header h1 { letter-spacing: -0.045em; }
.st-key-realty_welcome {
    padding: 1.5rem; margin-block: 0.5rem 1rem;
    border: 1px solid #3d4d54; border-top: 2px solid #cbb58b;
    border-radius: 1rem; background: #19242b;
}
.st-key-realty_welcome button { text-align: start; height: auto; min-height: 3rem; }
.st-key-realty_welcome p { overflow-wrap: anywhere; }
@media (max-width: 600px) {
    .st-key-realty_welcome { padding: 1rem; }
    .st-key-realty_header h1 { font-size: 2rem; }
}
</style>""")



@st.cache_resource(show_spinner=False)
def runtime():
    return Chatbot()


def render(result):
    properties = result.get('properties')
    # Recompute even for pre-fix conversation entries retained in session state.
    st.markdown(property_summary(properties, arabic(result['answer'])) if properties is not None else result['answer'])
    if result.get('error'):
        st.warning(result['error'])
    if properties is not None:
        st.info(result.get('disclaimer', SNAPSHOT))
        if properties['unknown_count']:
            st.caption(f"{properties['unknown_count']} other records have unknown required attributes and no confirmed mismatch.")
        with st.expander('Applied exact filters'):
            st.json(properties['filters'])
        for record in properties['matches']:
            card = property_card(record)
            with st.container(border=True):
                st.markdown(f"**{card['heading']}**")
                if record.get('title'):
                    st.caption(record['title'])
                st.caption(card['location'])
                st.markdown(f"### {card['price']}")
                st.write(card['attributes'])
                st.caption(f"Captured: {captured_date(record.get('scraped_at'))}")
                st.link_button('Original Wasalt listing / المصدر', record['source_url'], use_container_width=True)
                if record.get('quality_flags'):
                    st.caption(f"Source quality: {len(record['quality_flags'])} recorded warnings")
                    with st.expander('Source quality notes'):
                        for flag in record['quality_flags']:
                            st.write('• ' + flag.replace('_', ' ').capitalize())
                with st.expander('Technical details', expanded=False):
                    st.json(record)
    if result.get('sources') and properties is None:
        st.divider()
        st.caption('Sources · Original public pages')
        for source in result['sources']:
            st.link_button(f"{source['source_id']} · {source['title']}", source['source_url'], use_container_width=True)


st.session_state.setdefault('conversation', [])
st.session_state.setdefault('pending_request', None)


def queue_question(question, filters=None):
    if not question or not question.strip() or st.session_state.pending_request is not None:
        return
    st.session_state.conversation = (st.session_state.conversation + [{'role': 'user', 'content': question}])[-19:]
    st.session_state.pending_request = {'id': uuid4().hex, 'question': question, 'filters': filters, 'started': False}


def submit_chat():
    queue_question(st.session_state.chat_question)


def clear_conversation():
    st.session_state.conversation = []
    st.session_state.pending_request = None


question, filters = None, None
with st.sidebar:
    st.subheader('Property tools')
    st.caption('Explore the collected Wasalt listings with exact filters.')
    st.caption(SNAPSHOT)
    st.divider()
    with st.expander('Advanced property search'):
        with st.form('property_filters'):
            # JSONL only, no Chroma load until a query is submitted.
            from app.config import REPO_ROOT
            from app.property_search import load_properties
            import os
            try:
                records = load_properties(os.environ.get('WASALT_LISTINGS_PATH', str(REPO_ROOT / 'data/wasalt/listings.jsonl')))
            except (OSError, ValueError):
                st.error('The historical property dataset is missing or invalid. Restore the approved application artifacts before starting.')
                st.stop()
            purpose = st.selectbox('Purpose', ['', 'rent', 'sale'])
            city = st.selectbox('City', [''] + sorted({r['city'] for r in records if r['city']}))
            district = st.selectbox('District', [''] + sorted({r['district'] for r in records if r['district']}))
            kind = st.selectbox('Property type', [''] + sorted({r['property_type'] for r in records}))
            budget = st.number_input('Maximum price (SAR; inclusive; 0 = no limit)', min_value=0, step=1000)
            period = st.selectbox('Price period', ['', 'year', 'month', 'day'])
            beds = st.number_input('Minimum bedrooms (0 = no minimum)', min_value=0, step=1)
            area = st.number_input('Minimum area (sqm; 0 = no minimum)', min_value=0, step=10)
            submitted = st.form_submit_button('Search historical listings', disabled=st.session_state.pending_request is not None)
        if submitted:
            if budget and purpose == 'rent' and not period:
                st.warning('Select the rental budget period.')
            else:
                filters = {k: v for k, v in dict(purpose=purpose, city=city, district=district, property_type=kind,
                           max_price=budget, price_period=period, min_bedrooms=beds, min_area_sqm=area).items() if v}
                question = filter_question(filters)

welcome = not st.session_state.conversation
with st.container(key='realty_header'):
    heading, action = st.columns([4, 1], vertical_alignment='center')
    with heading:
        st.title('RealtyAI')
    with action:
        st.button('New chat', on_click=clear_conversation, use_container_width=True)
    st.caption('Your AI-powered guide to DarGlobal developments and Wasalt properties.')
if welcome:
    with st.container(key='realty_welcome'):
        st.caption('EXPLORE · DISCOVER · ASK')
        st.chat_input('Ask about developments or find a property...', max_chars=1500,
                      key='chat_question', on_submit=submit_chat,
                      disabled=st.session_state.pending_request is not None)
        st.caption('Try asking...')
        suggestions = ('Explore DarGlobal developments', 'What is the AIDA project?',
                       'Find villas for rent in Riyadh', 'How does Wasalt work?')
        for column, example in zip(st.columns(2) * 2, suggestions):
            with column:
                if st.button(example, use_container_width=True, disabled=st.session_state.pending_request is not None):
                    question = example
    st.caption('Grounded in publicly available real-estate information. Independent demonstration; no official affiliation.')

if question:
    queue_question(question, filters)

for turn in st.session_state.conversation:
    with st.chat_message(turn['role']):
        if turn['role'] == 'assistant':
            render(turn['result'])
        else:
            st.write(turn['content'])
if not welcome:
    st.chat_input('Ask RealtyAI / اسأل RealtyAI', max_chars=1500,
                  key='chat_question', on_submit=submit_chat, disabled=st.session_state.pending_request is not None)
pending = st.session_state.pending_request
if pending:
    with st.chat_message('assistant'):
        if pending['started']:
            # A rerun interrupted this request. Do not automatically repeat a
            # possibly already submitted API call or leave input disabled forever.
            result = {'answer': 'The previous request was interrupted. Please submit it again when ready.',
                      'error': '', 'sources': [], 'properties': None}
        else:
            pending['started'] = True
            with st.status('Preparing your answer...', expanded=False) as status:
                try:
                    result = runtime().answer(pending['question'], st.session_state.conversation[:-1],
                                              explicit_filters=pending['filters'],
                                              on_status=lambda label: status.update(label=label))
                except Exception:
                    # SDK exceptions may contain request details; never expose them.
                    result = {'answer': 'The knowledge service is unavailable. Check the local artifacts and configured credentials.',
                              'error': 'The request could not be completed.', 'sources': [], 'properties': None}
                failed = bool(result.get('error'))
                status.update(label='Completed with a service error.' if failed else 'Answer ready.', state='error' if failed else 'complete')
        current = st.session_state.pending_request
        if current and current['id'] == pending['id']:
            render(result)
            st.session_state.conversation.append({'role': 'assistant', 'content': result['answer'], 'result': result})
            st.session_state.conversation = st.session_state.conversation[-20:]
            st.session_state.pending_request = None
            # Re-enable inputs immediately; cached history redraw makes no API call.
            st.rerun()
