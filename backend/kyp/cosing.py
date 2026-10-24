"""Exact-name, cached CosIng ingestion. New descriptions always enter as drafts."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import httpx
from .repository import Repository

POLICY = json.loads(Path(__file__).with_name('cosing-policy.json').read_text(encoding='utf-8'))
CONFIG_URL = 'https://ec.europa.eu/growth/tools-databases/cosing/assets/env-json-config.json'
BASE = 'https://ec.europa.eu/growth/tools-databases/cosing/'

def canonical_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)

def query_rows(client, config, query):
    url = config['euSearchApiUrl']
    if urlparse(url).hostname != 'webgate.ec.europa.eu' or not url.startswith('https://'):
        raise ValueError('Unexpected CosIng query service; refusing to send a query')
    rows = []
    for page in range(1, 5):
        response = client.post(url, params={'apiKey': config['euSearchApiKey'], 'text': '*', 'pageSize': 500, 'pageNumber': page}, files={'query': ('query.json', json.dumps(query), 'application/json')})
        if response.status_code != 200:
            raise ValueError('CosIng query failed with HTTP ' + str(response.status_code))
        if len(response.content) > 8 * 1024 * 1024:
            raise ValueError('CosIng response exceeds the import size bound')
        data = response.json()
        if not isinstance(data.get('results'), list):
            raise ValueError('Unexpected CosIng response schema')
        rows.extend(row['metadata'] for row in data['results'])
        if len(rows) >= int(data['totalResults']):
            return rows
        if not data['results']:
            raise ValueError('Incomplete CosIng pagination')
    raise ValueError('CosIng query exceeded the bounded four-page limit')

def fetch_catalog(folder, refresh=False):
    path = folder / 'cosing-catalog.json'
    previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    manifest_hash = hashlib.sha256(canonical_json(POLICY['candidates']).encode()).hexdigest()
    if previous and previous.get('manifest_hash') == manifest_hash and not refresh:
        return previous
    if len(POLICY['candidates']) > POLICY['max_candidates']:
        raise ValueError('Candidate list exceeds the policy bound')
    with httpx.Client(timeout=30, headers={'User-Agent': 'KYP-LocalDevelopment/0.2 (bounded public inventory queries)'}) as client:
        response = client.get(CONFIG_URL)
        response.raise_for_status()
        config = response.json()  # The public browser query key is never persisted or logged.
        ingredients = query_rows(client, config, {'bool': {'must': [{'term': {'itemType': 'ingredient'}}, {'term': {'status': 'Active'}}, {'terms': {'inciName': POLICY['candidates']}}]}})
        functions = query_rows(client, config, {'bool': {'must': [{'term': {'itemType': 'function'}}]}})
    result = {'manifest_hash': manifest_hash, 'retrieved_at': datetime.now(timezone.utc).isoformat(), 'ingredients': ingredients, 'functions': functions}
    if previous and previous.get('ingredients') == ingredients and previous.get('functions') == functions:
        result['retrieved_at'] = previous['retrieved_at']
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result

def one(record, key):
    values = record.get(key, [])
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], str) or not values[0].strip():
        raise ValueError('Expected one source value for ' + key)
    return values[0]

def valid_cas(value):
    if not re.fullmatch(r'\d{2,7}-\d{2}-\d', value):
        return False
    digits = value.replace('-', '')
    return sum((index + 1) * int(digit) for index, digit in enumerate(reversed(digits[:-1]))) % 10 == int(digits[-1])

def source_record(metadata, retrieved_at, function=False):
    identifier = one(metadata, 'functionId' if function else 'substanceId')
    if not identifier.isdigit():
        raise ValueError('Unexpected source identity')
    content = canonical_json(metadata)
    policy = POLICY['source']
    return {'id': ('cosing-function-' if function else 'cosing-') + identifier + '-' + hashlib.sha256(content.encode()).hexdigest()[:16], 'url': BASE + ('reference/functions' if function else 'details/' + identifier), 'licence': policy['licence'] + ' (' + policy['licence_url'] + ')', 'attribution': policy['attribution'], 'retrieved_at': retrieved_at, 'content': content}

def transform_record(metadata, references, retrieved_at):
    if metadata.get('itemType') != ['ingredient'] or metadata.get('status') != ['Active']:
        raise ValueError('Only active ingredient identities are accepted')
    name = one(metadata, 'inciName')
    if name not in POLICY['candidates']:
        raise ValueError('Source name is not an exact candidate match')
    identifier = one(metadata, 'substanceId')
    target = POLICY['crosswalk'].get(name)
    cas = {value for value in re.findall(r'\b\d{2,7}-\d{2}-\d\b', ' '.join(metadata.get('casNo', []))) if valid_cas(value)}
    if target and target['cas'] not in cas:
        raise ValueError('Curated identity crosswalk failed its CAS check')
    aliases = set()
    if target:
        aliases.update([name, target['cas']])
    elif len(cas) == 1:
        aliases.update(cas)
    for value in metadata.get('inciUsaName', []):
        if isinstance(value, str) and value.strip() and value.upper() not in {'N/A', 'NONE', 'NOT APPLICABLE'}:
            aliases.add(value.strip())
    ingredient = {'contexts': ['cosmetics'], 'id': target['id'] if target else 'cosing-' + identifier, 'name': target['name'] if target else name, 'aliases': sorted(aliases)}
    source = source_record(metadata, retrieved_at)
    sources = {source['id']: source}
    functions = metadata.get('functionName', [])
    selected, phrases = [], []
    priority = ['HUMECTANT', 'SKIN CONDITIONING - HUMECTANT', 'SKIN CONDITIONING - EMOLLIENT', 'EMOLLIENT', 'CLEANSING', 'SURFACTANT - CLEANSING', 'SURFACTANT - EMULSIFYING', 'EMULSIFYING', 'VISCOSITY CONTROLLING']
    ordered = priority + [role for role in POLICY['role_phrases'] if role not in priority]
    for role in ordered:
        if role not in functions or role not in references:
            continue
        phrase = POLICY['role_phrases'][role]
        if phrase in phrases:
            continue
        ref = references[role]
        one(ref, 'functionDescription')
        selected.append((role, ref));phrases.append(phrase)
        if len(phrases) >= POLICY['max_roles_per_description']:
            break
    if selected:
        citations = [{'source_id': source['id'], 'excerpt': '"functionName": ' + canonical_json(functions)}]
        for role, ref in selected:
            evidence = source_record(ref, retrieved_at, function=True)
            sources[evidence['id']] = evidence
            citations.append({'source_id': evidence['id'], 'excerpt': canonical_json(one(ref, 'functionDescription'))})
        ingredient['description'] = {'text': 'In cosmetics, this ingredient is listed for roles that ' + ' and '.join(phrases) + '.', 'citations': citations, 'provenance': {'context': 'cosmetics', 'method': 'structured_source_mapping', 'adapter_version': POLICY['version']}}
    return list(sources.values()), ingredient

def build_document(snapshot):
    references = {}
    for record in snapshot['functions']:
        if record.get('itemType') == ['function']:
            name = one(record, 'functionName')
            if name in references and references[name] != record:
                raise ValueError('Conflicting function definitions require review')
            references[name] = record
    grouped = {}
    for record in snapshot['ingredients']:
        grouped.setdefault(one(record, 'inciName'), {})[one(record, 'substanceId')] = record
    sources, ingredients = {}, []
    report = {'requested': len(POLICY['candidates']), 'matched': 0, 'descriptions': 0, 'missing': [], 'ambiguous': [], 'review_required': []}
    for name in POLICY['candidates']:
        records = list(grouped.get(name, {}).values())
        if not records:
            report['missing'].append(name);continue
        if len(records) != 1:
            report['ambiguous'].append(name);continue
        try:
            evidence, item = transform_record(records[0], references, snapshot['retrieved_at'])
        except ValueError as exc:
            report['review_required'].append({'name': name, 'reason': str(exc)});continue
        ingredients.append(item)
        sources.update({source['id']: source for source in evidence})
        report['matched'] += 1
        report['descriptions'] += int('description' in item)
    return {'sources': sorted(sources.values(), key=lambda source: source['id']), 'ingredients': ingredients}, report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', default='data/source-snapshots')
    parser.add_argument('--output', default='data/cosing-import.json')
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--db', help='Optional repository path or PostgreSQL URL; new content remains draft')
    args = parser.parse_args()
    document, report = build_document(fetch_catalog(Path(args.cache), args.refresh))
    output = Path(args.output);output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
    output.with_suffix('.report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    if args.db:
        Repository(args.db).import_document(document)
    print(json.dumps({key: len(value) if isinstance(value, list) else value for key, value in report.items()}, indent=2))
    print('New descriptions remain drafts. Source inventory membership does not establish safety or approval.')

if __name__ == '__main__':
    main()
