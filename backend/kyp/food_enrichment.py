"""Accumulate pinned, cited food identities from explicitly allowlisted sources.

The manifest records the evidence for identities, forms, aliases and additive
codes. Retrieval never approves content. Reimport preserves existing decisions.
"""
import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
import httpx

POLICY = json.loads(Path(__file__).with_name('food-enrichment-policy.json').read_text(encoding='utf-8'))
ALLOWED_HOSTS = {'www.fda.gov', 'www.govinfo.gov', 'data.food.gov.uk', 'www.ebi.ac.uk'}
MAX_BYTES = 2 * 1024 * 1024

class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style'}: self.skip += 1
    def handle_endtag(self, tag):
        if tag in {'script', 'style'}: self.skip = max(0, self.skip - 1)
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)

def normalized_content(raw, kind):
    if kind == 'xml':
        text = ' '.join(ET.fromstring(raw).itertext())
    elif kind == 'chebi':
        record = json.loads(raw)
        if record.get('id') != 32588 or record.get('stars') != 3 or record.get('ascii_name', '').casefold() != 'potassium chloride':
            raise ValueError('ChEBI potassium chloride identity changed')
        cas = {r['accession_number'] for r in record.get('database_accessions', {}).get('CAS', [])}
        names = {r['name'] for group in record.get('names', {}).values() for r in group}
        if '7447-40-7' not in cas or not {'E508', 'E-508', 'INS-508'} <= names:
            raise ValueError('ChEBI code/CAS evidence changed')
        text = json.dumps(record, ensure_ascii=False, sort_keys=True)
    else:
        parser = TextParser(); parser.feed(raw.decode('utf-8', errors='strict'))
        text = ' '.join(parser.parts)
    return re.sub(r'\s+', ' ', html.unescape(text)).strip()

def validate_record(record, spec):
    if record.get('url') != spec['url'] or not isinstance(record.get('content'), str):
        raise ValueError('Cached evidence URL/content differs from manifest')
    if hashlib.sha256(record['content'].encode()).hexdigest() != record.get('sha256'):
        raise ValueError('Evidence snapshot hash differs')
    datetime.fromisoformat(record['retrieved_at'])
    if any(excerpt not in record['content'] for excerpt in spec['required']):
        raise ValueError('Source identity or reuse evidence changed: ' + spec['url'])
    return record

def fetch_record(spec, cache, refresh=False):
    parsed = urlparse(spec['url'])
    if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.port not in (None, 443):
        raise ValueError('Source must use an allowlisted HTTPS origin')
    cache = Path(cache)
    path = cache / ('food-evidence-' + hashlib.sha256(spec['url'].encode()).hexdigest()[:20] + '.json')
    previous = validate_record(json.loads(path.read_text(encoding='utf-8')), spec) if path.exists() else None
    if previous and not refresh: return previous
    with httpx.Client(timeout=30, follow_redirects=False, headers={'User-Agent': 'KYP-LocalDevelopment/0.4 (bounded ingredient evidence retrieval)'}) as client:
        with client.stream('GET', spec['url']) as response:
            response.raise_for_status()
            if response.status_code != 200: raise ValueError('Source did not return complete content')
            parts = []; size = 0
            for part in response.iter_bytes():
                size += len(part)
                if size > MAX_BYTES: raise ValueError('Evidence exceeds 2 MB')
                parts.append(part)
    content = normalized_content(b''.join(parts), spec['format'])
    record = {'url': spec['url'], 'content': content, 'sha256': hashlib.sha256(content.encode()).hexdigest(), 'retrieved_at': datetime.now(timezone.utc).isoformat()}
    validate_record(record, spec)
    if previous and previous['sha256'] == record['sha256']: return previous
    cache.mkdir(parents=True, exist_ok=True)
    # Retain old evidence as well as the latest pointer; repository sources are immutable.
    archive = cache / ('food-evidence-content-' + record['sha256'] + '.json')
    archive.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record

def add_enrichment(document, cache, refresh=False, records=None):
    records = records if records is not None else {key: fetch_record(spec, cache, refresh) for key, spec in POLICY['sources'].items()}
    sources = {}
    for key, spec in POLICY['sources'].items():
        record = validate_record(records[key], spec)
        source = {'id': 'food-evidence-' + key + '-' + record['sha256'][:20], 'url': record['url'], 'retrieved_at': record['retrieved_at'], 'content': record['content'], 'licence': spec['licence'], 'attribution': spec['attribution']}
        sources[key] = source
        document['sources'].append(source)
    for entry in POLICY['entries']:
        item = next((i for i in document['ingredients'] if i['id'] == entry['id']), None)
        if item is not None and item['name'] != entry['name']: raise ValueError('Enrichment identity conflict')
        if item is None:
            if entry['description'] is None: raise ValueError('Required base ingredient absent: ' + entry['id'])
            item = {'id': entry['id'], 'name': entry['name'], 'contexts': ['food'], 'aliases': []}
            document['ingredients'].append(item)
        citations = []
        for evidence in entry['evidence']:
            source = sources[evidence['source']]
            if evidence['excerpt'] not in source['content']: raise ValueError('Ingredient support changed: ' + entry['name'])
            citations.append({'source_id': source['id'], 'excerpt': evidence['excerpt']})
        if entry.get('existing_code_evidence'):
            if entry['existing_code_evidence'] not in item['aliases'] or not item.get('description', {}).get('citations'):
                raise ValueError('Base additive-code evidence missing')
        aliases = list(entry['aliases'])
        for label in entry.get('functional_labels', []):
            for code in [entry['code'], 'E'+entry['code'], 'E '+entry['code'], 'INS '+entry['code'], 'INS-'+entry['code']]:
                aliases.extend([label + ' (' + code + ')', label + ' ' + code])
        item['aliases'] = sorted(set(item['aliases']) | set(aliases))
        if entry['description'] is not None:
            item['description'] = {'text': entry['description'], 'citations': citations, 'provenance': {'context': 'food', 'method': 'curated_source_summary', 'adapter_version': POLICY['version']}}
        elif citations:
            item['description']['citations'].extend(citations)
        provenance = item['description'].setdefault('provenance', {})
        provenance['label_evidence_version'] = POLICY['version']
        provenance['label_alias_evidence'] = json.dumps({'aliases': aliases, 'citations': citations or item['description']['citations'], 'basis': 'Pinned identity/form/code evidence; spelling variants only. No OCR typo aliases.'}, sort_keys=True)
    return document
