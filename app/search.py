"""Semantic retrieval only. Running this CLI makes one paid query embedding call."""

import argparse
import json
import math

from .chunking import OfflineTokenizer
from .config import IndexConfig
from .embeddings import EmbeddingClient
from .index_embeddings import load_chunks,read_manifest
from .vector_store import ChromaStore,identity


def format_results(result):
    rows=[]
    for rank,(key,text,meta,distance) in enumerate(zip(result['ids'][0],result['documents'][0],
            result['metadatas'][0],result['distances'][0]),1):
        if not math.isfinite(distance):
            raise ValueError('Invalid search distance')
        rows.append({'rank':rank,'chunk_id':key,'title':meta['title'],'source':meta['source'],
                     'excerpt':text[:700]+('…' if len(text)>700 else ''),
                     'source_url':meta['source_url'],'cosine_distance':distance})
    return rows


def search(config,query,top_k=5,source=None,store_factory=ChromaStore,client_factory=EmbeddingClient):
    if not query.strip() or not 1<=top_k<=50 or source not in (None,'darglobal','wasalt'):
        raise ValueError('Require nonempty query, top-k 1–50 and supported source')
    if not config.manifest_path.is_file():
        raise ValueError('Index has not been built; approved indexing with --execute is required')
    if (config.storage_path/'.index.lock').exists():
        raise ValueError('Index is currently locked; retrieval is unavailable during a build')
    rows,sha=load_chunks(config)
    build_identity=identity(config,sha)
    manifest=read_manifest(config,build_identity)
    if manifest['indexing_status']!='complete' or config.pending_path.exists():
        raise ValueError('Index is incomplete; resume approved indexing before retrieval')
    store=store_factory(config,build_identity,create=False)
    if store.ids()!={row['chunk_id'] for row in rows} or store.count()!=len(rows):
        raise ValueError('Index IDs/count no longer match the validated corpus')
    # Verify stored dimensions and source attribution before sending a paid query.
    from .index_embeddings import batches
    for batch in batches(rows,config):
        store.verify(batch)
    vector=client_factory(config).embed_query(query,OfflineTokenizer(config.corpus))
    return format_results(store.query(vector,min(top_k,len(rows)),source))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--query',required=True)
    parser.add_argument('--top-k',type=int,default=5)
    parser.add_argument('--source',choices=['darglobal','wasalt'])
    args=parser.parse_args(argv)
    results=search(IndexConfig.from_env(),args.query,args.top_k,args.source)
    print(json.dumps(results,ensure_ascii=False,indent=2))


if __name__=='__main__':
    try:
        main()
    except (ValueError,RuntimeError,FileNotFoundError) as error:
        raise SystemExit(str(error)) from None
    except Exception as error:
        raise SystemExit(f'Retrieval failed ({type(error).__name__}); no source text or credentials logged') from None
