"""Checkpoint 19D: four saved questions, eight requests, no retrieval or retries."""

import argparse
from datetime import datetime,timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path

from .config import REPO_ROOT,load_environment
from .evaluate_openrouter import MODELS,OpenRouterAPI,digest,messages_for,save_new,validate_model
from .index_embeddings import atomic_json

QUESTION_IDS=('q01','q03','q04','q05')
OUTPUT=REPO_ROOT/'artifacts/checkpoint_19d'


def prepare_matched(repo_root=REPO_ROOT):
    """Only saved 19C files; no Chroma client, retrieval or embedding invocation."""
    root=Path(repo_root);previous=root/'artifacts/checkpoint_19c'
    evidence=json.loads((previous/'evidence.json').read_text(encoding='utf-8'))
    prompts={row['query_id']:row for row in json.loads((previous/'prompts.json').read_text(encoding='utf-8'))}
    availability=json.loads((previous/'availability.json').read_text(encoding='utf-8'))
    if not availability['authenticated'] or {r['model_id'] for r in availability['models']}!=set(MODELS):
        raise ValueError('Missing original authenticated free-model metadata')
    if not all(validate_model(row) for row in availability['models']):
        raise ValueError('Only previously verified free models with these parameters are allowed')
    questions=[]
    for question in evidence['questions']:
        prompt=prompts[question['query_id']]
        if digest(question['sources'])!=question['evidence_sha256'] or prompt['messages']!=messages_for(question):
            raise ValueError('Saved evidence/template changed')
        if digest(prompt['messages'])!=prompt['messages_sha256']:
            raise ValueError('Saved prompt checksum mismatch')
        if question['query_id'] in QUESTION_IDS:
            questions.append({**question,**prompt})
    if tuple(q['query_id'] for q in questions)!=QUESTION_IDS:
        raise ValueError('Must evaluate exactly the four remaining questions, never Spain')
    reused=[]
    for model,tag in zip(MODELS,('ernie','nemotron')):
        source=previous/'adjustment_responses'/('q02_'+tag+'.json')
        raw=json.loads(source.read_text(encoding='utf-8'))
        parameters=raw['request_parameters']
        if (raw['query_id']!='q02' or raw['model_requested']!=model or raw['model_returned']!=model
                or raw['status']!='success' or raw['http_status']!=200
                or parameters['temperature']!=0 or parameters['max_tokens']!=4000
                or parameters['reasoning']!={'enabled':True} or raw['usage']['cost']!=0
                or raw['messages_sha256']!=prompts['q02']['messages_sha256']):
            raise ValueError('Spain pair is not the successful common-setting pair')
        reused.append({'source_path':str(source.relative_to(root)),
                       'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'raw_response':raw})
    return {'questions':questions,'reused_spain':reused,'models':list(MODELS),'maximum_new_attempts':8,
            'temperature':0,'reasoning_enabled':True,'max_completion_tokens':4000}


def run_matched(prepared,api,output):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    (output/'responses').mkdir()
    save_new(output/'inputs.json',prepared)
    state={'checkpoint':'19D','started_at':datetime.now(timezone.utc).isoformat(),'status':'running',
           'maximum_new_attempts':8,'generation_attempts':0,'prepared_sha256':digest(prepared),'results':[]}
    atomic_json(output/'run_manifest.json',state)
    results=[]
    for index,question in enumerate(prepared['questions']):
        order=MODELS if index%2==0 else tuple(reversed(MODELS))
        for model in order:
            if api.generation_attempts>=8:
                raise ValueError('Eight new attempts exhausted')
            state.update(in_flight={'query_id':question['query_id'],'model':model},
                         generation_attempts=api.generation_attempts+1)
            atomic_json(output/'run_manifest.json',state)
            result=api.generate(model,question['messages'],reasoning_enabled=True,max_tokens=4000)
            if result['messages_sha256']!=question['messages_sha256']:
                raise ValueError('Prompt changed before request')
            result.update(query_id=question['query_id'],question=question['question'],
                          evidence_sha256=question['evidence_sha256'],origin_checkpoint='19D',reused=False)
            tag='ernie' if model==MODELS[0] else 'nemotron'
            path='responses/'+question['query_id']+'_'+tag+'.json'
            save_new(output/path,result)
            results.append(result)
            state.pop('in_flight',None)
            state.update(generation_attempts=api.generation_attempts)
            state['results'].append({'query_id':question['query_id'],'model':model,'status':result['status'],'path':path})
            cost=(result.get('usage') or {}).get('cost')
            if result['status']!='success' or (cost is not None and Decimal(str(cost))!=0):
                state.update(status='stopped_for_review',stop_reason='Request failed or cost was not zero; no retry or parameter adjustment')
                atomic_json(output/'run_manifest.json',state)
                print(json.dumps({key:result.get(key) for key in ('query_id','model_requested','status','http_status','error')},ensure_ascii=False),flush=True)
                return results
            atomic_json(output/'run_manifest.json',state)
            print(json.dumps({key:result.get(key) for key in ('query_id','model_requested','model_returned','status','http_status','latency_seconds','usage')},ensure_ascii=False),flush=True)
    state.update(status='complete',completed_at=datetime.now(timezone.utc).isoformat())
    atomic_json(output/'run_manifest.json',state)
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    load_environment()
    prepared=prepare_matched()
    if not args.execute:
        print(json.dumps({'mode':'offline','questions':[q['query_id'] for q in prepared['questions']],
                          'new_attempts':8,'spain_responses_reused':2,'prepared_sha256':digest(prepared)},indent=2))
        return
    if OUTPUT.exists():
        raise FileExistsError('19D output exists; do not repeat requests or overwrite results')
    api=OpenRouterAPI(os.environ.get('OPENROUTER_API_KEY',''),attempt_limit=8)
    try:run_matched(prepared,api,OUTPUT)
    finally:api.session.close()


if __name__=='__main__':
    main()
