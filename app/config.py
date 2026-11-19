"""Central configuration shared with the next embedding checkpoint."""

from dataclasses import asdict, dataclass
from pathlib import Path
import os

REPO_ROOT = Path(__file__).resolve().parents[1]
TOKENIZER_URL = "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"
TOKENIZER_SHA256 = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"


@dataclass(frozen=True)
class CorpusConfig:
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    target_tokens: int = 450
    max_tokens: int = 500
    overlap_tokens: int = 50
    tokenizer_cache: Path = REPO_ROOT / ".cache/tiktoken"
    version: str = "heading-aware-v1"

    def __post_init__(self):
        if not (0 <= self.overlap_tokens < self.target_tokens <= self.max_tokens):
            raise ValueError("Require 0 <= overlap < target <= maximum")
        if self.embedding_dimensions <= 0 or not self.embedding_model.strip():
            raise ValueError("Embedding model/dimensions must be configured")

    @classmethod
    def from_env(cls):
        return cls(embedding_model=os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"),
                   embedding_dimensions=int(os.environ.get("EMBEDDING_DIMENSIONS", "1536")))

    def policy(self):
        values=asdict(self)
        values.pop("tokenizer_cache")
        return values


@dataclass(frozen=True)
class IndexConfig:
    """Index settings beside corpus policy; never changes prepared chunk IDs."""

    corpus: CorpusConfig = CorpusConfig()
    chunks_path: Path = REPO_ROOT / 'artifacts/chunks/chunks.jsonl'
    storage_path: Path = REPO_ROOT / 'artifacts/chroma'
    collection: str = 'real_estate_knowledge'
    expected_chunks: int = 1709
    batch_size: int = 75
    batch_token_limit: int = 250000
    input_token_limit: int = 8191
    max_retries: int = 3
    retry_initial_seconds: float = 1.0
    retry_max_seconds: float = 16.0
    request_timeout_seconds: float = 60.0
    usd_per_million_tokens: float = 0.02
    cost_ceiling_usd: float = 0.25

    def __post_init__(self):
        import math
        import ipaddress
        import re
        if not 1 <= self.batch_size <= 100 or not 1 <= self.batch_token_limit <= 300000:
            raise ValueError('Require batch size 1–100 and batch token limit <= 300000')
        if not 1 <= self.input_token_limit <= 8191 or self.expected_chunks < 1:
            raise ValueError('Invalid token limit or expected chunk count')
        if not 0 <= self.max_retries <= 8:
            raise ValueError('Retries must be bounded between 0 and 8')
        for value in (self.usd_per_million_tokens,self.cost_ceiling_usd,
                      self.retry_initial_seconds,self.retry_max_seconds,self.request_timeout_seconds):
            if not math.isfinite(value) or value < 0:
                raise ValueError('Costs and timeout/delay settings must be finite and nonnegative')
        if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{1,510}[A-Za-z0-9]',self.collection)
                or '..' in self.collection):
            raise ValueError('Collection must use 3–512 safe name characters')
        try:
            ipaddress.ip_address(self.collection)
        except ValueError:
            pass
        else:
            raise ValueError('Collection name cannot be an IP address')
        if self.storage_path.resolve().is_relative_to((REPO_ROOT/'data').resolve()):
            raise ValueError('Index must remain outside authoritative data directories')
        if self.chunks_path.resolve().is_relative_to(self.storage_path.resolve()):
            raise ValueError('Index storage must not contain its input chunk dataset')

    @classmethod
    def from_env(cls):
        """Explicit .env load; process environment wins; never returns credentials."""
        load_environment()
        corpus=CorpusConfig(
            embedding_model=os.environ.get('OPENAI_EMBEDDING_MODEL','text-embedding-3-small'),
            embedding_dimensions=int(os.environ.get('OPENAI_EMBEDDING_DIMENSIONS','1536')))
        return cls(corpus=corpus,
                   storage_path=Path(os.environ.get('CHROMA_PATH',str(REPO_ROOT/'artifacts/chroma'))),
                   collection=os.environ.get('CHROMA_COLLECTION','real_estate_knowledge'),
                   batch_size=int(os.environ.get('EMBEDDING_BATCH_SIZE','75')),
                   usd_per_million_tokens=float(os.environ.get('EMBEDDING_USD_PER_MILLION_TOKENS','0.02')),
                   cost_ceiling_usd=float(os.environ.get('EMBEDDING_COST_CEILING_USD','0.25')))

    @property
    def manifest_path(self):
        return self.storage_path/'index_manifest.json'

    @property
    def pending_path(self):
        return self.storage_path/'pending_batch.json'


def load_environment(root=REPO_ROOT):
    from dotenv import load_dotenv
    path=Path(root)/'.env'
    return {'env_file_present':path.is_file(),
            'env_values_loaded':bool(load_dotenv(path,override=False)),
            'api_key_configured':bool(os.environ.get('OPENAI_API_KEY','').strip())}
