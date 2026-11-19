"""Explicit OpenAI SDK embedding calls, validated alignment, bounded retries."""

from dataclasses import dataclass
import math
from numbers import Real
import os
import time


def validate_vectors(vectors, count, dimensions):
    if len(vectors)!=count:
        raise ValueError('Embedding response count does not match inputs')
    for vector in vectors:
        if len(vector)!=dimensions or any(isinstance(x,bool) or not isinstance(x,Real)
                                         or not math.isfinite(x) for x in vector):
            raise ValueError('Embedding has invalid dimensions or non-finite values')
        if not any(x!=0 for x in vector):
            raise ValueError('Zero embedding is invalid for cosine search')


@dataclass
class EmbeddingResult:
    vectors: list
    input_tokens: int | None


class EmbeddingClient:
    def __init__(self,config,client=None,sleep=time.sleep):
        self.config=config
        self.sleep=sleep
        if client is None:
            key=os.environ.get('OPENAI_API_KEY','').strip()
            if not key:
                raise ValueError('OPENAI_API_KEY is not configured')
            from openai import OpenAI
            # Disable SDK retries: there is one bounded retry policy in this module.
            client=OpenAI(api_key=key,max_retries=0,timeout=config.request_timeout_seconds)
        self.client=client

    def embed(self,texts,token_counts):
        if not texts or len(texts)!=len(token_counts) or len(texts)>self.config.batch_size:
            raise ValueError('Invalid embedding batch alignment or size')
        if any(not isinstance(text,str) or not text.strip() for text in texts):
            raise ValueError('Empty embedding input')
        if any(not isinstance(n,int) or n<1 or n>self.config.input_token_limit for n in token_counts):
            raise ValueError('Invalid embedding input token count')
        if sum(token_counts)>self.config.batch_token_limit:
            raise ValueError('Embedding batch exceeds token limit')
        for attempt in range(self.config.max_retries+1):
            try:
                response=self.client.embeddings.create(model=self.config.corpus.embedding_model,
                    dimensions=self.config.corpus.embedding_dimensions,input=texts,encoding_format='float')
                break
            except Exception as error:
                status=getattr(error,'status_code',None)
                code=getattr(error,'code',None)
                transient=(status in (408,409,429) or (isinstance(status,int) and status>=500)
                           or type(error).__name__ in ('APIConnectionError','APITimeoutError'))
                if code in ('insufficient_quota','billing_hard_limit_reached','billing_not_active'):
                    transient=False
                if not transient or attempt==self.config.max_retries:
                    # SDK messages/bodies may contain request details; never echo them.
                    label=str(status) if isinstance(status,int) else 'connection or request failure'
                    reason={400:'invalid input',401:'authentication',403:'permission',429:'rate limit'}.get(status,'service or connection')
                    if code in ('insufficient_quota','billing_hard_limit_reached','billing_not_active'):
                        reason='billing or quota; no retry'
                    raise RuntimeError(f'Embedding request failed ({label}: {reason}); no source text or credentials logged') from None
                self.sleep(min(self.config.retry_initial_seconds*2**attempt,self.config.retry_max_seconds))
        if getattr(response,'model',self.config.corpus.embedding_model)!=self.config.corpus.embedding_model:
            raise ValueError('Embedding response model differs from configured model')
        items=list(response.data)
        indices=[item.index for item in items]
        if any(type(index) is not int for index in indices) or sorted(indices)!=list(range(len(texts))):
            raise ValueError('Embedding response indices do not align with inputs')
        vectors=[list(item.embedding) for item in sorted(items,key=lambda item:item.index)]
        validate_vectors(vectors,len(texts),self.config.corpus.embedding_dimensions)
        usage=getattr(response,'usage',None)
        tokens=getattr(usage,'prompt_tokens',None)
        if tokens is not None and (type(tokens) is not int or tokens<0):
            raise ValueError('Invalid API usage count')
        return EmbeddingResult(vectors,tokens)

    def embed_query(self,text,tokenizer):
        return self.embed([text],[tokenizer.count(text)]).vectors[0]
