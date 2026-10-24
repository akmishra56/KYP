"""Bounded, cached ingestion of allowlisted sources. Imports are always drafts."""
import argparse
import hashlib
import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from .repository import Repository

POLICY = json.loads(Path(__file__).with_name('source-policy.json').read_text(encoding='utf-8'))
USER_AGENT = 'KYP-LocalDevelopment/0.1 (ingredient identity; bounded public API requests)'

def snapshot(url, folder, refresh=False):
    identity = hashlib.sha256(url.encode()).hexdigest()
    path = folder / (identity + '.json')
    previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    if previous and not refresh:
        return previous
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError('Source response exceeds 4 MB')
    data = json.loads(raw)
    content = json.dumps(data, sort_keys=True, ensure_ascii=False)
    if previous and previous['content'] == content:
        return previous
    result = {'url': url, 'retrieved_at': datetime.now(timezone.utc).isoformat(), 'content': content}
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result

def transform(seed, chebi_snapshot, wikidata_snapshot):
    chebi = json.loads(chebi_snapshot['content'])
    entity = json.loads(wikidata_snapshot['content'])['entities'].get(seed['wikidata'])
    if not entity or chebi.get('id') != seed['chebi'] or chebi.get('stars') != 3 or chebi.get('ascii_name', '').casefold() != seed['name'].casefold():
        raise ValueError('ChEBI identity does not match the reviewed seed manifest')
    crossrefs = [item['mainsnak'].get('datavalue', {}).get('value') for item in entity.get('claims', {}).get('P683', []) if item.get('rank') != 'deprecated']
    if str(seed['chebi']) not in crossrefs:
        raise ValueError('Wikidata/ChEBI identity cross-check failed')
    definition = chebi.get('definition')
    if not isinstance(definition, str) or not definition.strip():
        raise ValueError('No source definition available')
    aliases = {item['name'].casefold() for group in chebi.get('names', {}).values() for item in group if '<' not in item.get('name', '')}
    for alias in seed['aliases']:
        if alias.casefold() not in aliases:
            raise ValueError('Requested alias is not supported by this source snapshot: ' + alias)
    sources = []
    for key, source_snapshot in [('chebi', chebi_snapshot), ('wikidata', wikidata_snapshot)]:
        policy = POLICY['sources'][key]
        identifier = key + '-' + hashlib.sha256(source_snapshot['content'].encode()).hexdigest()[:20]
        sources.append({'id': identifier, **source_snapshot, 'licence': policy['licence'] + ' (' + policy['licence_url'] + ')', 'attribution': policy['attribution']})
    # JSON escaping is preserved in the snapshot, so use that exact representation as the support excerpt.
    excerpt = json.dumps(definition, ensure_ascii=False)
    ingredient = {'id': 'chebi-' + str(seed['chebi']), 'name': seed['name'], 'aliases': seed['aliases'], 'description': {'text': seed['description'], 'citations': [{'source_id': sources[0]['id'], 'excerpt': excerpt}]}}
    return sources, ingredient

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='data/seed-import.json')
    parser.add_argument('--cache', default='data/source-snapshots')
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--db', help='Optional database path/URL; import all records as drafts')
    args = parser.parse_args()
    document = {'sources': [], 'ingredients': []}
    cache = Path(args.cache)
    for seed in POLICY['seeds']:
        chebi = snapshot(f'https://www.ebi.ac.uk/chebi/backend/api/public/compound/{seed["chebi"]}/', cache, args.refresh)
        wikidata = snapshot(f'https://www.wikidata.org/wiki/Special:EntityData/{seed["wikidata"]}.json', cache, args.refresh)
        sources, ingredient = transform(seed, chebi, wikidata)
        document['sources'].extend(sources)
        document['ingredients'].append(ingredient)
        print('Fetched and cross-checked:', ingredient['name'])
        time.sleep(0.25)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding='utf-8')
    if args.db:
        Repository(args.db).import_document(document)
    print('Wrote four sourced identity records and draft descriptions. No automatic approval occurred.')

if __name__ == '__main__':
    main()
