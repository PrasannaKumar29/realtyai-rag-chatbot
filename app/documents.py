"""Load only finalized Markdown; retain frontmatter as metadata, not prose."""

from dataclasses import dataclass
import csv
import hashlib
import json
from pathlib import Path
import re

import yaml

from .config import REPO_ROOT


@dataclass(frozen=True)
class Document:
    document_id: str
    body: str
    metadata: dict


def parse_markdown(text):
    match=re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)",text,re.S)
    if not match:
        raise ValueError("Missing YAML frontmatter")
    metadata=yaml.safe_load(match.group(1))
    if not isinstance(metadata,dict):
        raise ValueError("Frontmatter must be an object")
    body=text[match.end():]
    if not body.strip():
        raise ValueError("Empty document body")
    return metadata,body


def flat_metadata(metadata):
    """Lists/maps are JSON strings; omit nulls for scalar-only Chroma metadata."""
    result={}
    for key,value in metadata.items():
        if value is None:
            continue
        if isinstance(value,(str,int,float,bool)):
            result[key]=value
        else:
            result[key+"_json"]=json.dumps(value,ensure_ascii=False,sort_keys=True,default=str)
    return result


def load_documents(repo_root=REPO_ROOT):
    root=Path(repo_root)
    dg=root/"data/darglobal/final/markdown"
    documents=[]
    for path in sorted(dg.rglob("*.md")):
        relative=path.relative_to(dg)
        document_id="darglobal:"+relative.with_suffix("").as_posix()
        documents.append(_load(path,root,document_id,"darglobal",relative.parts[0]))
    base=root/"data/wasalt"
    with (base/"corpus_manifest.csv").open(encoding="utf-8",newline="") as handle:
        entries=list(csv.DictReader(handle))
    for entry in sorted(entries,key=lambda row:row["document_id"]):
        relative=Path(entry["local_output_path"])
        if relative.is_absolute() or ".." in relative.parts or relative.suffix!=".md":
            raise ValueError("Unexpected corpus-manifest path")
        path=base/relative
        if not path.resolve().is_relative_to(base.resolve()):
            raise ValueError("Corpus path escapes the dataset")
        category=entry["content_category"]
        is_property=category in {"property_sale","property_rent"}
        if not is_property and not category.startswith("informational_"):
            raise ValueError("Unexpected Wasalt category")
        if relative.parts[0] != ("properties" if is_property else "informational"):
            raise ValueError("Category/path mismatch")
        identity="wasalt:property:"+entry["document_id"] if is_property else "wasalt:"+entry["document_id"]
        doc=_load(path,root,identity,"wasalt",category)
        if doc.metadata["source_url"]!=entry["source_url"] or doc.metadata.get("extracted_at")!=entry["extracted_at"]:
            raise ValueError("Document/manifest source metadata mismatch")
        if is_property and (doc.metadata.get("listing_id")!=entry["document_id"] or doc.metadata.get("purpose")!=category.removeprefix("property_")):
            raise ValueError("Listing identity/purpose mismatch")
        documents.append(doc)
    if len(documents)!=685 or len({d.document_id for d in documents})!=685:
        raise ValueError("Expected exactly 685 uniquely identified documents")
    counts={"darglobal":sum(d.metadata['source']=='darglobal' for d in documents),
            "wasalt_property":sum(d.metadata['content_type'].startswith('property_') for d in documents),
            "wasalt_informational":sum(d.metadata['content_type'].startswith('informational_') for d in documents)}
    if counts!={"darglobal":419,"wasalt_property":261,"wasalt_informational":5}:
        raise ValueError(f"Unexpected corpus coverage: {counts}")
    paths=[d.metadata['source_path'] for d in documents]
    if len(set(paths))!=len(paths):
        raise ValueError("A source file was loaded twice")
    return documents


def _load(path,root,identity,source,category):
    raw=path.read_bytes()
    metadata,body=parse_markdown(raw.decode('utf-8',errors='strict'))
    heading=re.search(r'^#\s+(.+)$',body,re.M)
    title=metadata.get('title') or (heading.group(1).strip() if heading else None)
    if not title or not metadata.get('source_url'):
        raise ValueError(f"Missing title/source URL: {path}")
    flat=flat_metadata(metadata)
    flat.update(document_id=identity,source=source,content_type=category,title=title,
                source_path=path.relative_to(root).as_posix(),source_sha256=hashlib.sha256(raw).hexdigest(),
                title_source='frontmatter' if metadata.get('title') else 'heading')
    timestamp=metadata.get('scraped_at') or metadata.get('extracted_at')
    if timestamp:
        flat['extracted_at']=str(timestamp)
    if category.startswith('property_'):
        flat['listing_id']=str(metadata['listing_id'])
    return Document(identity,body,flat)
