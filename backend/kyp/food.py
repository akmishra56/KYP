"""Bounded FDA food inventory adapter. Imports are always draft-only."""
import argparse
import csv
import hashlib
import html
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import httpx
from .repository import Repository
from .ingest import snapshot, POLICY as SOURCE_POLICY

POLICY=json.loads(Path(__file__).with_name('food-policy.json').read_text(encoding='utf-8'))

def clean(value):
    return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]*>',' ',value))).strip(' ,')

def decode_rows(raw):
    if len(raw)>POLICY['max_bytes']:raise ValueError('FDA download exceeds size bound')
    try:text=raw.decode('utf-8-sig')
    except UnicodeDecodeError:text=raw.decode('cp1252',errors='replace')
    marker='CAS Reg No (or other ID),'
    if marker not in text:raise ValueError('FDA CSV header missing')
    reader=csv.DictReader(io.StringIO(text[text.index(marker):],newline=''))
    if not {'Substance','Other Names','Used for (Technical Effect)'}<=set(reader.fieldnames or []):raise ValueError('Unexpected FDA schema')
    rows=list(reader)
    if len(rows)>10000 or any(None in row for row in rows):raise ValueError('Malformed or oversized FDA inventory')
    return rows

def fetch_catalog(folder,refresh=False):
    path=folder/'fda-food-catalog.json'
    previous=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    if previous and not refresh:return previous
    with httpx.Client(timeout=60,follow_redirects=True,headers={'User-Agent':'KYP-LocalDevelopment/0.3 (bounded public food inventory import)'}) as client:
        with client.stream('GET',POLICY['url']) as response:
            response.raise_for_status();parts=[];size=0
            for part in response.iter_bytes():
                size+=len(part)
                if size>POLICY['max_bytes']:raise ValueError('FDA download exceeds size bound')
                parts.append(part)
    raw=b''.join(parts);rows=decode_rows(raw)
    result={'url':POLICY['url'],'sha256':hashlib.sha256(raw).hexdigest(),'retrieved_at':datetime.now(timezone.utc).isoformat(),'rows':rows}
    if previous and previous['rows']==rows:result['retrieved_at']=previous['retrieved_at']
    folder.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

def transform(entry,row,retrieved_at):
    name=clean(row['Substance'])
    if name!=entry['source_name']:raise ValueError('FDA name does not match manifest exactly')
    if any('\ufffd' in value for value in row.values()):raise ValueError('Source encoding needs review')
    aliases={clean(value).lstrip('\u2666 ').strip() for value in re.split(r'<br\s*/?>',row['Other Names'],flags=re.I)}-{''}
    for alias,evidence in entry.get('curated_aliases',{}).items():
        if evidence not in aliases:raise ValueError('Curated alias evidence missing')
        aliases.add(alias)
    target=entry.get('crosswalk')
    if target and row['CAS Reg No (or other ID)'].strip()!=target['cas']:raise ValueError('FDA crosswalk CAS changed')
    # Use FDA identity, not a hash of mutable content; changed evidence receives new source/description IDs.
    identity='fda-food-'+hashlib.sha256(name.encode()).hexdigest()[:20]
    item={'contexts':['food'],'id':target['id'] if target else identity,'name':target['name'] if target else name,'aliases':sorted(aliases | ({name} if target else set()))}
    content=json.dumps(row,sort_keys=True,ensure_ascii=False)
    source={'id':identity+'-'+hashlib.sha256(content.encode()).hexdigest()[:16],'url':POLICY['url'],'retrieved_at':retrieved_at,'licence':POLICY['licence']+' ('+POLICY['terms_url']+')','attribution':POLICY['attribution'],'content':content}
    roles=[clean(part) for part in re.split(r'<br\s*/?>',row['Used for (Technical Effect)'],flags=re.I)]
    selected=[role for role in POLICY['role_priority'] if role in roles][:2]
    if selected:
        item['description']={'text':'In food, the FDA inventory lists this ingredient as '+ ' and '.join(role.lower() for role in selected)+'.','citations':[{'source_id':source['id'],'excerpt':'"Used for (Technical Effect)": '+json.dumps(row['Used for (Technical Effect)'],ensure_ascii=False)}],'provenance':{'context':'food','method':'structured_source_mapping','adapter_version':POLICY['version']}}
    return source,item

def build_document(snapshot):
    grouped={}
    for row in snapshot['rows']:grouped.setdefault(clean(row['Substance']),[]).append(row)
    sources=[];ingredients=[]
    report={'requested':len(POLICY['candidates']),'matched':0,'descriptions':0,'missing':[],'ambiguous':[],'review_required':[]}
    for entry in POLICY['candidates']:
        name=entry['source_name'];rows=grouped.get(name,[])
        if not rows:report['missing'].append(name);continue
        if len(rows)!=1:report['ambiguous'].append(name);continue
        try:source,item=transform(entry,rows[0],snapshot['retrieved_at'])
        except ValueError as exc:report['review_required'].append({'name':name,'reason':str(exc)});continue
        sources.append(source);ingredients.append(item);report['matched']+=1;report['descriptions']+=int('description' in item)
    return {'sources':sources,'ingredients':ingredients},report

def add_code_aliases(document,cache,refresh=False):
    for entry in POLICY.get('code_sources',[]):
        item=next((item for item in document['ingredients'] if item['name'].upper()==entry['source_name'] or item['id']==('chebi-'+str(entry['chebi']))),None)
        if item is None:continue
        record=snapshot('https://www.ebi.ac.uk/chebi/backend/api/public/compound/'+str(entry['chebi'])+'/',cache,refresh)
        data=json.loads(record['content'])
        cas={row['accession_number'] for row in data.get('database_accessions',{}).get('CAS',[])}
        names={row['name'].casefold() for group in data.get('names',{}).values() for row in group}
        if data.get('id')!=entry['chebi'] or data.get('stars')!=3 or data.get('ascii_name','').casefold()!=entry['name'] or entry['cas'] not in cas or any(alias.casefold() not in names for alias in entry['aliases']):
            raise ValueError('Food code identity/alias verification failed')
        source_policy=SOURCE_POLICY['sources']['chebi']
        source={'id':'food-codes-'+hashlib.sha256(record['content'].encode()).hexdigest()[:20],**record,'licence':source_policy['licence']+' ('+source_policy['licence_url']+')','attribution':source_policy['attribution']}
        document['sources'].append(source)
        item['aliases']=sorted(set(item['aliases'])|set(entry['aliases']))
        if 'description' in item:
            item['description']['citations'].append({'source_id':source['id'],'excerpt':json.dumps(entry['aliases'][0],ensure_ascii=False)})
    return document

def add_staples(document,cache,refresh=False):
    import xml.etree.ElementTree as ET
    for entry in POLICY.get('staples',[]):
        url='https://www.govinfo.gov/content/pkg/CFR-2025-title21-vol2/xml/CFR-2025-title21-vol2-sec'+entry['section']+'.xml'
        path=cache/('cfr-'+entry['section']+'.xml')
        if refresh or not path.exists():
            with httpx.Client(timeout=30) as client:
                response=client.get(url);response.raise_for_status()
                if len(response.content)>1000000:raise ValueError('Standard definition exceeds size bound')
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(response.content)
        raw=path.read_bytes();root=ET.fromstring(raw)
        subject=root.findtext('.//SUBJECT')
        content=re.sub(r'\s+',' ',''.join(root.itertext())).strip()
        if subject!=entry['expected_subject'] or entry['evidence'] not in content:raise ValueError('Staple source identity/support changed')
        source={'id':entry['id']+'-'+hashlib.sha256(raw).hexdigest()[:16],'url':url,'retrieved_at':datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat(),'licence':'U.S. federal government text, public domain; 2025 CFR edition','attribution':'U.S. Food and Drug Administration; 2025 Code of Federal Regulations, via GovInfo. Identity definition only, not a current legal-use assessment.','content':content}
        document['sources'].append(source)
        document['ingredients'].append({'contexts':['food'],'id':entry['id'],'name':entry['name'],'aliases':entry['aliases'],'description':{'text':entry['description'],'citations':[{'source_id':source['id'],'excerpt':entry['evidence']}],'provenance':{'context':'food','method':'curated_source_summary','adapter_version':POLICY['version']}}})
    return document


def add_oils(document, cache, refresh=False):
    # Store only a short supporting excerpt; commercial rights remain pending.
    url='https://www.fao.org/4/y2774e/y2774e04.htm'
    path=cache/'palm-oil-evidence.json'
    evidence='Palm oil is derived from the fleshy mesocarp of the fruit of the oil palm'
    if refresh or not path.exists():
        with httpx.Client(timeout=30,follow_redirects=True) as client:
            with client.stream('GET',url) as response:
                response.raise_for_status();raw=b''
                for part in response.iter_bytes():
                    raw+=part
                    if len(raw)>1000000:raise ValueError('Oil source exceeds size bound')
        text=clean(raw.decode('utf-8',errors='replace'))
        if evidence not in text:raise ValueError('Palm identity evidence changed')
        record={'content':evidence,'sha256':hashlib.sha256(raw).hexdigest(),'retrieved_at':datetime.now(timezone.utc).isoformat()}
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(record),encoding='utf-8')
    record=json.loads(path.read_text(encoding='utf-8'))
    if record['content']!=evidence:raise ValueError('Palm evidence cache differs from policy')
    source={'id':'food-palm-evidence-'+record['sha256'][:16],'url':url,'content':record['content'],'retrieved_at':record['retrieved_at'],'licence':'Commercial reuse review pending; https://www.fao.org/contact-us/terms/en/','attribution':'FAO/WHO Codex Alimentarius, archived named vegetable oil definitions; identity only, no endorsement.'}
    document['sources'].append(source)
    document['ingredients'].append({'id':'food-palm-oil','name':'palm oil','contexts':['food'],'aliases':[],'description':{'text':'Palm oil comes from the fleshy part of oil-palm fruit. It is a distinct ingredient from palm kernel oil.','citations':[{'source_id':source['id'],'excerpt':evidence}],'provenance':{'context':'food','method':'curated_source_summary','adapter_version':POLICY['version']}}})
    return document


def review_development(repository, document):
    """Explicit local-development review of generated, allowlisted source content.

    Never overturn a rejection or publish pending commercial-rights material.
    This records automated source comparison, not independent editorial review.
    """
    from .food_enrichment import POLICY as ENRICHMENT_POLICY
    reviewer = 'Codex automated food evidence comparison; not independent human/scientific review'
    allowed = {POLICY['url']} | {s['url'] for s in ENRICHMENT_POLICY['sources'].values()}
    allowed |= {'https://www.ebi.ac.uk/chebi/backend/api/public/compound/'+str(e['chebi'])+'/' for e in POLICY['code_sources']}
    allowed |= {'https://www.govinfo.gov/content/pkg/CFR-2025-title21-vol2/xml/CFR-2025-title21-vol2-sec'+e['section']+'.xml' for e in POLICY['staples']}
    pending = repository.pending()
    source_ids = {s['id'] for s in document['sources'] if s['url'] in allowed and 'pending' not in s['licence'].lower()}
    reviewed_sources = reviewed_descriptions = 0
    for source in pending['sources']:
        if source['id'] in source_ids:
            repository.approve_source(source['id'], reviewer); reviewed_sources += 1
    approved = {s['id'] for s in repository.pending('approved')['sources']}
    expected = {hashlib.sha256((item['id']+json.dumps(item['description'],sort_keys=True)).encode()).hexdigest() for item in document['ingredients'] if 'description' in item}
    for description in pending['descriptions']:
        payload = json.loads(description['payload'])
        if description['id'] in expected and all(c['source_id'] in approved for c in payload['citations']):
            repository.approve_description(description['id'], reviewer); reviewed_descriptions += 1
    return {'automated_source_reviews_added': reviewed_sources, 'automated_description_reviews_added': reviewed_descriptions, 'independent_release_review': 'still required'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--cache',default='data/source-snapshots');parser.add_argument('--output',default='data/food-import.json');parser.add_argument('--db');parser.add_argument('--refresh',action='store_true');parser.add_argument('--review-development',action='store_true',help='Explicit automated source comparison for local development; preserves rejections and rights gates');args=parser.parse_args()
    if args.review_development and not args.db:parser.error('--review-development requires --db')
    document,report=build_document(fetch_catalog(Path(args.cache),args.refresh))
    add_code_aliases(document,Path(args.cache),args.refresh)
    add_staples(document,Path(args.cache),args.refresh)
    add_oils(document,Path(args.cache),args.refresh)
    from .food_enrichment import add_enrichment
    add_enrichment(document,Path(args.cache),args.refresh)
    report['staple_definitions']=len(POLICY.get('staples',[]))
    report['total_food_records']=len(document['ingredients'])
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding='utf-8');output.with_suffix('.report.json').write_text(json.dumps(report,indent=2))
    if args.db:
        repository=Repository(args.db);repository.import_document(document)
        if args.review_development:report['development_review']=review_development(repository,document)
    output.with_suffix('.report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2));print('Import complete. Automated development review only when explicitly requested; independent release review remains required. Inventory membership is not approval or a safety finding.')

if __name__=='__main__':main()
