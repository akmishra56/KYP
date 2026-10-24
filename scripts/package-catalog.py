"""Package only catalog tables and public-source caches for local Mac transfer."""
import argparse
from contextlib import closing
import hashlib
import json
import re
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, unquote

ROOT=Path(__file__).resolve().parents[1]
TABLES=('ingredients','aliases','sources','descriptions','schema_migrations','review_events','ingredient_contexts')

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--name',default='KYP-mac-catalog');args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+',args.name):raise ValueError('Invalid archive name')
    output=ROOT/'artifacts';output.mkdir(exist_ok=True)
    secrets=[]
    for path in [ROOT/'.env',ROOT/'mobile/.env',ROOT/'mobile/.env.local']:
        if not path.exists():continue
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if '=' not in line or line.lstrip().startswith('#'):continue
            key,value=line.split('=',1);value=value.strip().strip("\"'")
            if re.search(r'PASSWORD|SECRET|TOKEN|API_KEY|DATABASE_URL',key):
                if len(value)>=10:secrets.append(value.encode())
                password=urlparse(value).password if '://' in value else None
                if password and len(unquote(password))>=8:secrets.append(unquote(password).encode())
    def check(content,name):
        if any(secret in content for secret in secrets):raise ValueError('Local credential found in '+name)
        if re.search(rb'(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-proj-[A-Za-z0-9_-]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)',content):raise ValueError('Possible key/token in '+name)
    with tempfile.TemporaryDirectory(prefix='catalog-transfer-',dir=output) as folder:
        target=Path(folder)/'kyp.sqlite3'
        source=ROOT/'backend/data/kyp.sqlite3'
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as old,closing(sqlite3.connect(target)) as new:
            old.execute('BEGIN')
            counts={}
            for table in TABLES:
                schema=old.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
                if not schema:raise ValueError('Catalog table absent: '+table)
                new.execute(schema[0])
                rows=old.execute('SELECT * FROM '+table).fetchall()
                columns=[r[1] for r in old.execute('PRAGMA table_info('+table+')')]
                if rows:new.executemany('INSERT INTO '+table+' VALUES('+','.join('?' for _ in columns)+')',rows)
                counts[table]=len(rows)
            for name,sql in old.execute("SELECT name,sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"):
                new.execute(sql)
            new.commit()
            if new.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Database integrity failed')
            if new.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Database reference check failed')
            if {r[0] for r in new.execute("SELECT name FROM sqlite_master WHERE type='table'")}!=set(TABLES):raise ValueError('Unexpected table in export')
            descriptions=new.execute("SELECT ingredient_id,payload FROM descriptions WHERE review_state='approved'").fetchall()
            approved={r[0] for r in new.execute("SELECT id FROM sources WHERE review_state='approved'")}
            food={i for i,p in descriptions if (d:=json.loads(p)).get('provenance',{}).get('context')=='food' and all(c['source_id'] in approved for c in d['citations'])}
        payloads={'KYP-catalog/backend/data/kyp.sqlite3':target.read_bytes()}
        timestamps={}
        cache=ROOT/'backend/data/source-snapshots'
        for path in sorted(cache.iterdir()):
            if path.is_symlink() or not path.is_file() or path.suffix not in {'.json','.xml','.html'}:continue
            name='KYP-catalog/backend/data/source-snapshots/'+path.name
            payloads[name]=path.read_bytes();timestamps[name]=path.stat().st_mtime_ns
        readme="# KYP catalog transfer\n\nThis bundle contains catalog tables, citations, review history and cached source\nevidence. It contains no connection credentials, scan sessions, user uploads,\ninstalled dependencies or models. Source licences and attribution remain in the\ndatabase. Automated review is not independent release approval.\n\nInstall the matching source package first. Before the first API start, copy this\nbundle using: python3.14 scripts/restore-catalog.py ../KYP-catalog\nfrom the extracted KYP source folder. The helper validates checksums and restores\noriginal source-cache timestamps. Do not replace an existing Mac catalog: preserve\nit and merge/migrate separately if you already have Mac edits. Keep the source\ncaches with the database to retain original immutable retrieval timestamps.\nSee MACBOOK-SETUP.md in the source package for exact commands and validation.\n"
        payloads['KYP-catalog/README.md']=readme.encode()
        entries=[]
        for name,content in payloads.items():
            check(content,name);entry={'path':name,'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}
            if name in timestamps:entry['mtime_ns']=timestamps[name]
            entries.append(entry)
        manifest={'format':1,'created_utc':datetime.now(timezone.utc).isoformat(),'catalog_tables':counts,'food_descriptions':len(food),'source_cache_files':len(payloads)-2,'runtime_sessions_included':False,'credentials_included':False,'files':entries}
        archive=output/(args.name+'.zip')
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as package:
            for name,content in payloads.items():
                info=zipfile.ZipInfo(name);info.create_system=3;info.external_attr=(0o100644<<16);info.compress_type=zipfile.ZIP_DEFLATED;package.writestr(info,content)
            package.writestr('KYP-catalog/CATALOG-MANIFEST.json',json.dumps(manifest,indent=2))
        with zipfile.ZipFile(archive) as package:
            if package.testzip():raise ValueError('Archive integrity failed')
            for entry in entries:
                if hashlib.sha256(package.read(entry['path'])).hexdigest()!=entry['sha256']:raise ValueError('Archive hash mismatch')
        digest=hashlib.sha256(archive.read_bytes()).hexdigest()
        archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n',encoding='utf8')
        archive.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
        print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'sha256':digest,'catalog_tables':counts,'food_descriptions':len(food),'source_cache_files':manifest['source_cache_files'],'integrity':'pass','credential_scan':'pass'},indent=2))

if __name__=='__main__':main()
