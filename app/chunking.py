"""Heading-aware, word-safe token windows with exact source-span coverage."""

import base64
from dataclasses import dataclass,replace
from functools import lru_cache
import hashlib
import json
import re

import tiktoken

from .config import CorpusConfig,TOKENIZER_SHA256,TOKENIZER_URL


class OfflineTokenizer:
    """Construct cl100k_base from verified local bytes; no download code is used."""
    def __init__(self,config):
        name=tiktoken.encoding_name_for_model(config.embedding_model)
        if name!='cl100k_base':
            raise ValueError(f'Unsupported offline tokenizer: {name}')
        path=config.tokenizer_cache/hashlib.sha1(TOKENIZER_URL.encode()).hexdigest()
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=TOKENIZER_SHA256:
            raise RuntimeError('Verified cl100k_base cache is missing; no network fallback is permitted')
        ranks={base64.b64decode(token):int(rank) for token,rank in (line.split() for line in path.read_bytes().splitlines() if line)}
        # Same public cl100k_base pattern/special tokens as tiktoken 0.14.0.
        pattern=r"'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}++|\p{N}{1,3}+| ?[^\s\p{L}\p{N}]++[\r\n]*+|\s++$|\s*[\r\n]|\s+(?!\S)|\s"
        self.encoding=tiktoken.Encoding(name=name,pat_str=pattern,mergeable_ranks=ranks,
            special_tokens={'<|endoftext|>':100257,'<|fim_prefix|>':100258,'<|fim_middle|>':100259,'<|fim_suffix|>':100260,'<|endofprompt|>':100276})

    @lru_cache(maxsize=2048)
    def count(self,text):
        return len(self.encoding.encode(text,disallowed_special=()))


@dataclass(frozen=True)
class Section:
    start: int
    end: int
    heading: str
    path: tuple


def sections(body):
    found=[];stack=[];offset=0;fence=None
    for line in body.splitlines(keepends=True):
        fence_match=re.match(r'^\s*(`{3,}|~{3,})',line)
        if fence_match:
            marker=fence_match.group(1)
            if fence is None:fence=(marker[0],len(marker))
            elif marker[0]==fence[0] and len(marker)>=fence[1]:fence=None
        elif fence is None:
            heading=re.match(r'^(#{1,6})\s+(.+?)\s*$',line.rstrip('\r\n'))
            if heading:
                level=len(heading.group(1));label=line.rstrip('\r\n')
                while stack and stack[-1][0]>=level:stack.pop()
                stack.append((level,label));found.append((offset,label,tuple(h for _,h in stack)))
        offset+=len(line)
    if not found or found[0][0]>0:found.insert(0,(0,'',()))
    return [Section(start,found[i+1][0] if i+1<len(found) else len(body),heading,path)
            for i,(start,heading,path) in enumerate(found)]


def merge_spans(spans):
    result=[]
    for start,end in sorted(set(spans)):
        if end<=start:continue
        if result and start<=result[-1][1]:result[-1]=(result[-1][0],max(end,result[-1][1]))
        else:result.append((start,end))
    return result


def render(doc,spans,context):
    spans=merge_spans(spans)
    text='\n\n'.join(doc.body[a:b].strip() for a,b in spans if doc.body[a:b].strip())
    prefix=[]
    for heading in ('# '+doc.metadata['title'],*context):
        if heading and heading not in text and heading not in prefix:prefix.append(heading)
    if prefix and doc.metadata['content_type'].startswith('property_') and len(spans)>1 and spans[0][0]==0:
        # The repeated overview belongs before the continued description heading.
        first=doc.body[spans[0][0]:spans[0][1]].strip()
        rest='\n\n'.join(doc.body[a:b].strip() for a,b in spans[1:])
        return (first+'\n\n'+'\n\n'.join(prefix)+'\n\n'+rest).strip()
    return ('\n\n'.join(prefix)+('\n\n' if prefix else '')+text).strip()


def split_section(doc,section,essential,tokenizer,config):
    text=doc.body[section.start:section.end]
    # Markdown links with spaces in their title are atomic, like unbroken words.
    words=list(re.finditer(r'!?\[[^\]]*\]\((?:[^()\n]|\([^()\n]*\))*\)|\S+',text));start=0;drafts=[]
    context=section.path
    def candidate(a,b):
        span=(section.start+words[a].start(),section.start+words[b-1].end())
        spans=merge_spans([*essential,span])
        return spans,render(doc,spans,context)
    while start<len(words):
        full_spans,full=candidate(start,len(words))
        if tokenizer.count(full)<=config.max_tokens:
            drafts.append((full_spans,context));break
        lo,hi=start+1,len(words);best=start
        while lo<=hi:
            mid=(lo+hi)//2
            if tokenizer.count(candidate(start,mid)[1])<=config.target_tokens:best=mid;lo=mid+1
            else:hi=mid-1
        if best==start:
            if tokenizer.count(candidate(start,start+1)[1])>config.max_tokens:
                raise ValueError(f'One unbroken word/context exceeds token limit: {doc.document_id}')
            best=start+1
        # Prefer a paragraph or sentence end near the selected boundary.
        for end in range(best,start,-1):
            segment=words[end-1].group()
            gap=text[words[end-1].end():words[end].start()] if end<len(words) else ''
            if ('\n\n' in gap or re.search(r'[.!?؟][\]"\')]*$',segment)) and tokenizer.count(candidate(start,end)[1])>=config.target_tokens*0.8:
                best=end;break
        spans,rendered=candidate(start,best)
        if tokenizer.count(rendered)>config.max_tokens:raise ValueError('Token limit exceeded')
        drafts.append((spans,context))
        overlap_start=best
        for i in range(best-1,start,-1):
            if tokenizer.count(text[words[i].start():words[best-1].end()])<=config.overlap_tokens:overlap_start=i
            else:break
        start=max(start+1,overlap_start)
    return drafts


def chunk_document(doc,tokenizer,config):
    whole=render(doc,[(0,len(doc.body))],())
    if tokenizer.count(whole)<=config.max_tokens:
        drafts=[([(0,len(doc.body))],())]
    else:
        parts=sections(doc.body)
        is_property=doc.metadata['content_type'].startswith('property_')
        essential=[]
        if is_property:
            essential=[(s.start,s.end) for s in parts if s.heading.startswith('# ') or s.heading=='## Property Overview' or not s.heading]
            if tokenizer.count(render(doc,essential,()))>config.max_tokens-50:
                raise ValueError('Essential property context is too large to repeat safely')
        remainder=[s for s in parts if (s.start,s.end) not in essential and doc.body[s.start:s.end].strip()]
        drafts=[];pending=[];context=()
        def flush():
            nonlocal pending,context
            if pending:drafts.append((merge_spans([*essential,*pending]),context));pending=[];context=()
        for section in remainder:
            span=(section.start,section.end)
            one=render(doc,[*essential,span],section.path)
            if tokenizer.count(one)>config.max_tokens:
                flush()
                if doc.metadata['content_type']=='informational_faq' and section.heading.startswith('## '):
                    raise ValueError('FAQ pair exceeds maximum; refusing to separate question and answer')
                drafts.extend(split_section(doc,section,essential,tokenizer,config));continue
            combined=render(doc,[*essential,*pending,span],context or section.path)
            previous=render(doc,[*essential,*pending],context) if pending else ''
            if pending and (tokenizer.count(combined)>config.max_tokens or (tokenizer.count(previous)>=350 and tokenizer.count(combined)>config.target_tokens)):
                flush()
            if not pending:context=section.path
            pending.append(span)
        flush()
        # Merge small adjacent tails only when the complete result still fits.
        merged=[]
        for spans,path in drafts:
            if merged:
                old_spans,old_path=merged[-1]
                combined=merge_spans([*old_spans,*spans])
                threshold=250 if is_property else 150
                if min(tokenizer.count(render(doc,spans,path)),tokenizer.count(render(doc,old_spans,old_path)))<threshold and tokenizer.count(render(doc,combined,old_path))<=config.max_tokens:
                    merged[-1]=(combined,old_path);continue
            merged.append((spans,path))
        drafts=merged
        # Rebalance a tiny tail with its preceding text instead of emitting an
        # isolated form/social-link fragment. Preserve every source character.
        balanced=[]
        for spans,path in drafts:
            if balanced and not is_property and doc.metadata['content_type']!='informational_faq' and tokenizer.count(render(doc,spans,path))<120:
                previous,previous_path=balanced[-1]
                joined=merge_spans([*previous,*spans])
                if len(joined)==1:
                    total=tokenizer.count(render(doc,joined,previous_path))
                    if total>config.max_tokens and tokenizer.count(render(doc,previous,previous_path))>=350:
                        middle=max(200,min(config.target_tokens,total//2))
                        replacement=split_section(doc,Section(joined[0][0],joined[0][1],'',previous_path),[],tokenizer,replace(config,target_tokens=middle))
                        if all(tokenizer.count(render(doc,a,b))>=120 for a,b in replacement):
                            balanced.pop();balanced.extend(replacement);continue
            balanced.append((spans,path))
        drafts=balanced
    result=[]
    for index,(spans,path) in enumerate(drafts):
        text=render(doc,spans,path)
        identity=json.dumps({'document_id':doc.document_id,'index':index,'text':text,'policy':config.policy()},ensure_ascii=False,sort_keys=True,separators=(',',':'))
        row={**doc.metadata,'chunk_id':'chunk_'+hashlib.sha256(identity.encode()).hexdigest(),
             'chunk_index':index,'text':text,'token_count':tokenizer.count(text),'section_path':' > '.join(path),
             'source_spans_json':json.dumps(spans,separators=(',',':')),'chunker_version':config.version}
        if not text or row['token_count']>config.max_tokens:raise ValueError('Invalid chunk')
        result.append(row)
    return result
