"""Chroma persistence adapter. Imports are lazy; embeddings are always explicit."""

import hashlib
import json
import math

from .embeddings import validate_vectors


def metadata_for(row):
    values={key:value for key,value in row.items() if key not in ('chunk_id','text') and value is not None}
    if not all(isinstance(value,(str,int,float,bool)) and
               (not isinstance(value,float) or math.isfinite(value)) for value in values.values()):
        raise ValueError('Chroma metadata must contain finite scalar values')
    return values


def identity(config,checksum):
    return {'schema_version':1,'chunks_sha256':checksum,
            'embedding_model':config.corpus.embedding_model,
            'embedding_dimensions':config.corpus.embedding_dimensions,
            'collection_name':config.collection,'expected_chunk_count':config.expected_chunks,
            'distance':'cosine'}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def collection_metadata(build_identity):
    return {**build_identity,'hnsw:space':'cosine','index_fingerprint':fingerprint(build_identity)}


class ChromaStore:
    def __init__(self,config,build_identity,create=False):
        import chromadb
        from chromadb.config import Settings
        self.dimensions=config.corpus.embedding_dimensions
        self.client=chromadb.PersistentClient(path=str(config.storage_path/'store'),
            settings=Settings(anonymized_telemetry=False))
        expected=collection_metadata(build_identity)
        if create:
            self.collection=self.client.get_or_create_collection(name=config.collection,metadata=expected,embedding_function=None)
        else:
            self.collection=self.client.get_collection(name=config.collection,embedding_function=None)
        if self.collection.metadata!=expected:
            raise ValueError('Stored Chroma collection metadata is incompatible')

    def ids(self):
        return set(self.collection.get(include=[])['ids'])

    def count(self):
        return self.collection.count()

    def put(self,rows,vectors):
        validate_vectors(vectors,len(rows),self.dimensions)
        self.collection.upsert(ids=[row['chunk_id'] for row in rows],documents=[row['text'] for row in rows],
            metadatas=[metadata_for(row) for row in rows],embeddings=vectors)

    def verify(self,rows):
        if not rows:
            return
        result=self.collection.get(ids=[row['chunk_id'] for row in rows],include=['documents','metadatas','embeddings'])
        positions={key:index for index,key in enumerate(result['ids'])}
        if set(positions)!={row['chunk_id'] for row in rows}:
            raise ValueError('Stored chunk IDs differ from expected batch')
        for row in rows:
            index=positions[row['chunk_id']]
            if result['documents'][index]!=row['text'] or result['metadatas'][index]!=metadata_for(row):
                raise ValueError('Stored chunk text/metadata differs from source')
            validate_vectors([result['embeddings'][index]],1,self.dimensions)

    def query(self,vector,top_k,source=None):
        validate_vectors([vector],1,self.dimensions)
        return self.collection.query(query_embeddings=[vector],n_results=top_k,
            where={'source':source} if source else None,include=['documents','metadatas','distances'])
