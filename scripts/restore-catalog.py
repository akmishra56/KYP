"""Restore a catalog-only transfer with hashes and exact evidence timestamps."""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path, PurePosixPath

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('bundle',type=Path);args=parser.parse_args()
    bundle=args.bundle.resolve();manifest=json.loads((bundle/'CATALOG-MANIFEST.json').read_text(encoding='utf8'))
    data=ROOT/'backend/data'
    if (data/'kyp.sqlite3').exists() or (data/'source-snapshots').exists():
        raise ValueError('Existing catalog/cache detected. Preserve it and merge separately; nothing was overwritten.')
    planned=[]
    for entry in manifest['files']:
        name=PurePosixPath(entry['path'])
        if name.is_absolute() or '..' in name.parts or name.parts[0]!='KYP-catalog':raise ValueError('Invalid bundle path')
        relative=Path(*name.parts[1:]);source=bundle/relative
        if source.is_symlink() or not source.resolve().is_relative_to(bundle) or not source.is_file():raise ValueError('Invalid bundle file')
        content=source.read_bytes()
        if len(content)!=entry['bytes'] or hashlib.sha256(content).hexdigest()!=entry['sha256']:raise ValueError('Bundle checksum mismatch: '+str(relative))
        if relative==Path('README.md'):continue
        if relative!=Path('backend/data/kyp.sqlite3'):
            if relative.parent!=Path('backend/data/source-snapshots') or relative.suffix not in {'.json','.xml','.html'}:raise ValueError('Unexpected catalog content')
            if not isinstance(entry.get('mtime_ns'),int) or entry['mtime_ns']<=0:raise ValueError('Source timestamp absent')
        planned.append((source,ROOT/relative,entry.get('mtime_ns')))
    if not any(target==data/'kyp.sqlite3' for _,target,_ in planned):raise ValueError('Catalog database absent')
    # Verify every file before creating destination files. Preserve timestamps used
    # by the existing CFR adapter to identify immutable retrieval records.
    for source,target,timestamp in planned:
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        if timestamp is not None:os.utime(target,ns=(timestamp,timestamp))
    print('Restored catalog and '+str(len(planned)-1)+' source snapshots. Existing review history and source timestamps preserved.')

if __name__=='__main__':main()
