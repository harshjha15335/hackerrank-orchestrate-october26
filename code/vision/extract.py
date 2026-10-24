"""Screenshot extraction with providers, one retry and a content-addressed cache.

A provider turns image bytes into an extraction document. Two kinds exist:

* ``FixtureProvider`` returns the manual transcription committed under
  ``fixtures/``. It makes no model call; its ledger rows say so.
* A model provider (``ModelProvider`` subclass) calls a vision model and must
  report the provider's own token counts. No live model provider ships in M8:
  this environment has no vision API key, so every M8 extraction is a manual
  fixture. Tests drive the model path with an offline fake.

Every response is validated against ``schema.py``. An invalid response is
retried once; a second failure is recorded and yields no observations. Valid
results are cached under sha256(image bytes) + prompt version + model, so a
warm run makes no provider calls at all.
"""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from .schema import SCHEMA_VERSION, SchemaError, validate

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / 'fixtures'
PROMPT_VERSION = SCHEMA_VERSION + '+' + hashlib.sha256((HERE / 'prompt.md').read_bytes()).hexdigest()[:12]


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class Response:
    document: dict
    input_tokens: int | None = None    # provider-reported; None when no model ran
    output_tokens: int | None = None


class FixtureProvider:
    name, model, makes_model_calls = 'manual_fixture', 'manual-fixture', False

    def __init__(self, directory: Path = FIXTURES):
        self.directory = Path(directory)
        # A corrected fixture must not be shadowed by a cached older transcription.
        self.fingerprint = hashlib.sha256(b''.join(
            p.name.encode() + b'\0' + p.read_bytes() for p in sorted(self.directory.glob('*.json')))).hexdigest()[:16]

    def extract(self, image: bytes, meta: dict) -> Response:
        path = self.directory / (Path(meta['file_path']).stem + '.json')
        if not path.is_file():
            raise ProviderError(f'{meta["file_id"]}: no manual fixture at {path.name}')
        return Response(json.loads(path.read_text(encoding='utf-8')))


class ModelProvider:
    """Base for a vision-model provider. ``extract`` must return provider-reported usage."""
    name = model = 'unset'
    makes_model_calls = True

    def extract(self, image: bytes, meta: dict) -> Response:
        raise NotImplementedError


@dataclass
class Extraction:
    meta: dict
    sha256: str
    document: dict | None
    status: str          # extracted / cached / invalid
    error: str | None = None


@dataclass
class Extractor:
    provider: object
    cache: Path | None = None
    prompt_version: str = PROMPT_VERSION
    ledger: list = field(default_factory=list)
    counters: dict = field(default_factory=lambda: {'provider_calls': 0, 'model_calls': 0, 'cache_hits': 0,
                                                    'retries': 0, 'invalid': 0})

    def key(self, digest: str) -> str:
        material = f'{digest}\n{self.prompt_version}\n{self.provider.name}:{self.provider.model}'
        if getattr(self.provider, 'fingerprint', None): material += f'\n{self.provider.fingerprint}'
        return hashlib.sha256(material.encode()).hexdigest()

    def one(self, image: bytes, meta: dict) -> Extraction:
        digest = hashlib.sha256(image).hexdigest()
        expect = dict(file_id=meta['file_id'], file_path=meta['file_path'], image_sha256=digest)
        cached = self.cache / (self.key(digest) + '.json') if self.cache else None
        if cached and cached.is_file():
            try:
                doc = validate(json.loads(cached.read_text(encoding='utf-8')), **expect)
            except (SchemaError, ValueError):
                doc = None   # a damaged cache entry is ignored, never trusted
            if doc is not None:
                self.counters['cache_hits'] += 1
                self._log(meta, digest, 'cache', 0, None)
                return Extraction(meta, digest, doc, 'cached')
        error = None
        for attempt in (1, 2):
            self.counters['provider_calls'] += 1
            if self.provider.makes_model_calls: self.counters['model_calls'] += 1
            response = self.provider.extract(image, meta)
            self._log(meta, digest, 'call', attempt, response)
            try:
                doc = validate(response.document, **expect)
            except SchemaError as exc:
                error = str(exc)
                if attempt == 1: self.counters['retries'] += 1
                continue
            if cached:
                cached.parent.mkdir(parents=True, exist_ok=True)
                temp = cached.with_suffix('.tmp')
                temp.write_text(json.dumps(doc, sort_keys=True, ensure_ascii=False), encoding='utf-8')
                temp.replace(cached)
            return Extraction(meta, digest, doc, 'extracted')
        self.counters['invalid'] += 1
        return Extraction(meta, digest, None, 'invalid', error)

    def _log(self, meta, digest, kind, attempt, response):
        model_call = kind == 'call' and self.provider.makes_model_calls
        self.ledger.append({'file_id': meta['file_id'], 'image_sha256': digest, 'kind': kind, 'attempt': attempt,
                            'provider': self.provider.name, 'model': self.provider.model,
                            'model_call': model_call,
                            'input_tokens': response.input_tokens if response and model_call else None,
                            'output_tokens': response.output_tokens if response and model_call else None})

    def run(self, dataset: Path) -> list[Extraction]:
        dataset = Path(dataset).resolve()
        with (dataset / 'evidence_files.csv').open(encoding='utf-8', newline='') as stream:
            manifest = [m for m in csv.DictReader(stream) if m['file_path'].lower().endswith('.png')]
        out = []
        for meta in sorted(manifest, key=lambda m: m['file_id']):
            path = (dataset / meta['file_path']).resolve()
            if not path.is_relative_to(dataset / 'evidence') or not path.is_file():
                raise ProviderError(f'unsafe or missing image path: {meta["file_id"]}')
            out.append(self.one(path.read_bytes(), meta))
        return out
