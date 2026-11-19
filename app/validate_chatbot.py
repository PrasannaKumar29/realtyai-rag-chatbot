"""Checkpoint 20 only: at most five new ERNIE requests; refuses repeated runs."""
import argparse
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import threading
import time


def memory():
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2 if sys.platform == 'darwin' else 1024)
    try:
        rss = int(subprocess.check_output(['ps', '-o', 'rss=', '-p', str(os.getpid())], text=True).strip()) / 1024
    except (OSError, ValueError, subprocess.SubprocessError):
        rss = None
    return {'rss_mib': rss, 'peak_rss_mib': peak}


QUESTIONS = ('What amenities does Trump Dubai offer?', 'What developments does DarGlobal have in Spain?',
             'How can I list my property on Wasalt?', 'Villas for rent in Riyadh under SAR 100,000/year',
             'أخبرني عن فيلا وصلت رقم 5891036 في حي النرجس بالرياض بمساحة 250 متر و6 دورات مياه')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'questions': QUESTIONS, 'maximum_new_generations': 5, 'retries': 0}, ensure_ascii=False))
        return
    startup = memory()
    import streamlit
    from .chatbot import Chatbot, Generator, Retrieval
    from .config import REPO_ROOT
    from .evaluate_openrouter import OpenRouterAPI, save_new
    from .property_search import classify
    output = REPO_ROOT / 'artifacts/checkpoint_20'
    output.mkdir(exist_ok=False)
    save_new(output / 'started.json', {'maximum_new_generations': 5, 'retries': 0, 'questions': QUESTIONS})
    imported = memory()
    started = time.perf_counter()
    retrieval = Retrieval()
    api = OpenRouterAPI(os.environ.get('OPENROUTER_API_KEY', ''), attempt_limit=5)
    bot = Chatbot(retrieval=retrieval, generator=Generator(api))
    loaded = memory()
    init_seconds = time.perf_counter() - started
    samples = []
    stop = threading.Event()

    def sample():
        while not stop.wait(.25):
            samples.append(memory())

    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    results = []
    try:
        for index, question in enumerate(QUESTIONS, 1):
            save_new(output / f'q{index:02}_started.json', {'question': question, 'generation_attempts_before': api.generation_attempts})
            result = bot.answer(question)
            result['question'] = question
            result['memory_after'] = memory()
            if result.get('properties'):
                result['all_displayed_properties_satisfy_filters'] = all(classify(r, result['filters'])['status'] == 'exact' for r in result['properties']['matches'])
            save_new(output / f'q{index:02}.json', result)
            results.append(result)
            print(json.dumps({'query': index, 'route': result['route'], 'latency_seconds': result.get('latency_seconds'),
                              'error': result['error'], 'cited_urls': [s['source_url'] for s in result['sources']],
                              'property_matches': (result.get('properties') or {}).get('total_matches')}, ensure_ascii=False), flush=True)
    finally:
        stop.set(); thread.join(timeout=2)
        api.session.close()
        save_new(output / 'resources.json', {'startup': startup, 'after_streamlit_and_application_import': imported,
                  'after_chroma_validation': loaded, 'runtime_initialization_seconds': round(init_seconds, 3),
                  'after_queries': memory(), 'query_samples': samples, 'generation_attempts': api.generation_attempts,
                  'query_latencies_seconds': [r.get('latency_seconds') for r in results], 'streamlit_version': streamlit.__version__})


if __name__ == '__main__':
    main()
