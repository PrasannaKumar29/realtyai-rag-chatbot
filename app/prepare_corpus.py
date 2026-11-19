"""Reproducible offline chunk export and coverage audit. No embedding/index calls."""

import argparse
from collections import Counter,defaultdict
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import statistics
import tempfile

from .config import CorpusConfig,REPO_ROOT
from .documents import load_documents
from .chunking import OfflineTokenizer,chunk_document,merge_spans,render


def jsonl_text(records):
    return ''.join(json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n' for row in records)


def iter_chunks(path):
    """Checkpoint 19 input interface: stream one existing JSONL record at a time."""
    with Path(path).open(encoding='utf-8') as handle:
        for line in handle:
            if line.strip():yield json.loads(line)


def prepare(repo_root=REPO_ROOT,config=None):
    config=config or CorpusConfig.from_env()
    tokenizer=OfflineTokenizer(config)
    documents=load_documents(repo_root)
    chunks=[row for doc in documents for row in chunk_document(doc,tokenizer,config)]
    # A second independent preparation from unchanged source files must match exactly.
    repeated_documents=load_documents(repo_root)
    repeated=[row for doc in repeated_documents for row in chunk_document(doc,tokenizer,config)]
    if chunks!=repeated:raise ValueError('Repeated runs produced different chunk records')
    by_document=defaultdict(list)
    for row in chunks:
        by_document[row['document_id']].append(row)
        if not all(isinstance(value,(str,int,float,bool)) for value in row.values()):
            raise ValueError('Non-scalar chunk metadata')
        if not row['text'].strip() or row['token_count']!=tokenizer.count(row['text']) or row['token_count']>config.max_tokens:
            raise ValueError('Empty, incorrect or oversized chunk')
        if not all(row.get(k) for k in ('chunk_id','document_id','source','content_type','title','source_url')):
            raise ValueError('Required chunk identity/reference missing')
    if len({row['chunk_id'] for row in chunks})!=len(chunks):raise ValueError('Duplicate chunk ID')
    if set(by_document)!={doc.document_id for doc in documents}:raise ValueError('Document coverage mismatch')
    doc_rows=[]
    for doc in documents:
        rows=by_document[doc.document_id]
        if [r['chunk_index'] for r in rows]!=list(range(len(rows))):raise ValueError('Noncontiguous chunk indexes')
        spans=merge_spans([tuple(span) for row in rows for span in json.loads(row['source_spans_json'])])
        cursor=0
        for start,end in spans:
            if doc.body[cursor:start].strip():raise ValueError(f'Source text lost: {doc.document_id}')
            cursor=end
        if doc.body[cursor:].strip():raise ValueError(f'Source tail lost: {doc.document_id}')
        # Every covered slice must occur verbatim in a chunk: Arabic is never
        # reconstructed by slicing a token byte stream or lossy decoding.
        for row in rows:
            for a,b in json.loads(row['source_spans_json']):
                if doc.body[a:b].strip() not in row['text']:raise ValueError('Source slice altered')
            if row['source_url']!=doc.metadata['source_url']:raise ValueError('Source URL changed')
            if doc.metadata['content_type'].startswith('property_') and row.get('listing_id')!=doc.metadata['listing_id']:
                raise ValueError('Property identity lost')
        source=Path(repo_root)/doc.metadata['source_path']
        if hashlib.sha256(source.read_bytes()).hexdigest()!=doc.metadata['source_sha256']:
            raise ValueError('Source Markdown changed during preparation')
        doc_rows.append({**doc.metadata,'body_characters':len(doc.body),'body_token_count':tokenizer.count(render(doc,[(0,len(doc.body))],())),
                         'chunk_count':len(rows),'required_additional_splitting':len(rows)>1})
    tokens=[row['token_count'] for row in chunks]
    same_urls=defaultdict(list)
    same_bodies=defaultdict(list)
    for doc in documents:
        same_urls[(doc.metadata['source'],doc.metadata['source_url'])].append(doc.document_id)
        same_bodies[hashlib.sha256(doc.body.encode()).hexdigest()].append(doc.document_id)
    missing={key:sum(not doc.metadata.get(key) for doc in documents) for key in ('source','source_url','document_id','content_type','title','extracted_at')}
    missing['listing_id_on_property']=sum(not doc.metadata.get('listing_id') for doc in documents if doc.metadata['content_type'].startswith('property_'))
    warnings=[]
    duplicate_urls=[{'source':key[0],'source_url':key[1],'documents':ids} for key,ids in same_urls.items() if len(ids)>1]
    duplicate_bodies=[ids for ids in same_bodies.values() if len(ids)>1]
    if duplicate_urls:warnings.append('Different approved documents share a source URL; see duplicate_source_urls.')
    if duplicate_bodies:warnings.append('Approved source documents have identical bodies; no source was silently dropped.')
    short=sum(t<150 for t in tokens)
    if short:warnings.append(f'{short} chunks are below 150 tokens, retained for short documents or meaningful topic boundaries.')
    warnings.append('Source boilerplate, marketing claims and existing quality warnings are preserved; chunking is not a cleaning or fact-verification pass.')
    source_manifest=[{'source_path':d.metadata['source_path'],'sha256':d.metadata['source_sha256']} for d in documents]
    chunk_bytes=jsonl_text(chunks).encode('utf-8')
    summary={
        'schema_version':1,'config':config.policy(),'tokenizer':'cl100k_base','tiktoken_version':version('tiktoken'),
        'documents_loaded':len(documents),'documents_by_source':dict(Counter(d.metadata['source'] for d in documents)),
        'documents_by_category':dict(Counter(d.metadata['content_type'] for d in documents)),
        'total_chunks':len(chunks),'chunks_by_source':dict(Counter(r['source'] for r in chunks)),
        'chunks_by_category':dict(Counter(r['content_type'] for r in chunks)),
        'token_counts':{'minimum':min(tokens),'median':statistics.median(tokens),'average':round(statistics.mean(tokens),3),'maximum':max(tokens)},
        'documents_requiring_additional_splitting':sum(row['chunk_count']>1 for row in doc_rows),
        'split_documents_by_category':dict(Counter(row['content_type'] for row in doc_rows if row['chunk_count']>1)),
        'missing_metadata_counts':missing,'duplicate_document_ids':0,'duplicate_source_paths':0,'duplicate_chunk_ids':0,
        'duplicate_source_urls':duplicate_urls,'duplicate_body_groups':duplicate_bodies,
        'unique_property_listing_ids':len({r['listing_id'] for r in chunks if r['content_type'].startswith('property_')}),
        'source_markdown_sha256_verified':len(documents),'source_nonwhitespace_coverage_verified':True,
        'arabic_source_slices_preserved':True,'repeated_run_identical':True,
        'corpus_fingerprint':hashlib.sha256(jsonl_text(source_manifest).encode()).hexdigest(),
        'chunks_sha256':hashlib.sha256(chunk_bytes).hexdigest(),'warnings':warnings,'exceptions':[],
    }
    return chunks,doc_rows,summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=REPO_ROOT/'artifacts/chunks')
    parser.add_argument('--verify-existing',action='store_true',help='Read-only regeneration/comparison against existing artifacts')
    parser.add_argument('--replace-generated',action='store_true',help='Explicitly replace only the three generated chunk artifacts')
    args=parser.parse_args()
    targets=[args.output_dir/name for name in ('chunks.jsonl','documents.jsonl','summary.json')]
    if args.output_dir.resolve().is_relative_to((REPO_ROOT/'data').resolve()):
        raise ValueError('Chunk outputs must remain outside source datasets')
    if args.verify_existing and args.replace_generated:parser.error('Verification is read-only')
    if not args.verify_existing and not args.replace_generated and any(p.exists() for p in targets):
        raise FileExistsError('Chunk output exists; use --verify-existing or a fresh output directory')
    chunks,documents,summary=prepare()
    values=[jsonl_text(chunks),jsonl_text(documents),json.dumps(summary,ensure_ascii=False,sort_keys=True,indent=2)+'\n']
    if args.verify_existing:
        if any(path.read_text(encoding='utf-8')!=value for path,value in zip(targets,values)):
            raise ValueError('Existing artifacts do not match deterministic preparation')
    else:
        args.output_dir.mkdir(parents=True,exist_ok=True)
        for path,value in zip(targets,values):
            temporary=None
            try:
                with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=args.output_dir,prefix='.chunk-',suffix='.tmp',delete=False) as handle:
                    temporary=Path(handle.name);handle.write(value);handle.flush();os.fsync(handle.fileno())
                if args.replace_generated:os.replace(temporary,path)
                else:os.link(temporary,path)
            finally:
                if temporary is not None:temporary.unlink(missing_ok=True)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
