"""Update the accumulating local catalog; never replace identities or review history."""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from kyp.food import build_document, fetch_catalog, add_code_aliases, add_staples, add_oils, review_development
from kyp.food_enrichment import add_enrichment
from kyp.repository import Repository

def configured_postgres():
    url = os.getenv('KYP_DATABASE_URL')
    if not url:
        path=BACKEND.parent/'.env'
        if path.exists():
            url=next((line.split('=',1)[1] for line in path.read_text(encoding='utf8').splitlines() if line.startswith('KYP_DATABASE_URL=')),None)
    if not url: raise ValueError('No PostgreSQL connection configured')
    parsed=urlparse(url)
    if parsed.scheme not in {'postgresql','postgres'} or parsed.hostname not in {'127.0.0.1','localhost','::1'}:
        raise ValueError('This updater only syncs a configured local PostgreSQL database')
    return url

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh',action='store_true',help='Retrieve current allowlisted sources; evidence drift stops import')
    parser.add_argument('--review-development',action='store_true',help='Record explicit automated development comparison; never independent release approval')
    parser.add_argument('--sync-postgres',action='store_true',help='Also add records to the configured local PostgreSQL catalog')
    args=parser.parse_args()
    postgres=configured_postgres() if args.sync_postgres else None
    cache=BACKEND/'data/source-snapshots'
    document,report=build_document(fetch_catalog(cache,args.refresh))
    add_code_aliases(document,cache,args.refresh);add_staples(document,cache,args.refresh);add_oils(document,cache,args.refresh)
    add_enrichment(document,cache,args.refresh)
    report['total_food_records']=len(document['ingredients'])
    db_path=BACKEND/'data/kyp.sqlite3'
    if db_path.exists():
        backup=BACKEND/'data/backups'/('before-food-update-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.sqlite3')
        backup.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(db_path.as_uri()+'?mode=ro',uri=True) as old,sqlite3.connect(backup) as new:old.backup(new)
        report['sqlite_backup']=str(backup.relative_to(BACKEND))
    report['databases']={}
    for name,target in [('sqlite',db_path)]+([('postgresql',postgres)] if postgres else []):
        repository=Repository(target);before=repository.stats()
        repository.import_document(document)
        review=review_development(repository,document) if args.review_development else {'review':'draft-only'}
        report['databases'][name]={'before':before,'after':repository.stats(),'review':review}
    # Keep the import and aggregate report; no connection URL or secret is exported.
    output=BACKEND/'data/food-import.json'
    output.write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding='utf8')
    (BACKEND/'data/food-update-report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
