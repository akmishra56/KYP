"""Build and validate a Git-ignore-aware source transfer ZIP; requires Git."""
import argparse,hashlib,json,os,re,subprocess,tempfile,zipfile
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse,unquote

ROOT=Path(__file__).resolve().parents[1]

def git(args,*,data=None):
    result=subprocess.run(['git','-c','core.autocrlf=false','-c','core.excludesFile='+str(ROOT/'artifacts'/'.empty-global-excludes'),*args],input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if result.returncode not in (0,1):raise RuntimeError('Git validation failed: '+result.stderr.decode(errors='replace'))
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--name',default='KYP-mac-source');args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+',args.name):raise ValueError('Archive name must use letters, numbers, dash or underscore')
    output=ROOT/'artifacts';output.mkdir(exist_ok=True)
    (output/'.empty-global-excludes').write_text('',encoding='utf-8')
    secrets=[]
    for environment in [ROOT/'.env',ROOT/'mobile/.env',ROOT/'mobile/.env.local']:
        if not environment.is_file():continue
        for line in environment.read_text(encoding='utf-8-sig').splitlines():
            if '=' not in line or line.lstrip().startswith('#'):continue
            key,value=line.split('=',1);value=value.strip().strip('\"\'')
            if re.search(r'PASSWORD|SECRET|TOKEN|API_KEY|DATABASE_URL',key):
                if len(value)>=10:secrets.append(value.encode())
                if '://' in value:
                    password=urlparse(value).password
                    if password and len(unquote(password))>=8:secrets.append(unquote(password).encode())
    skipped_dirs={'.git','node_modules','__pycache__','.venv','.expo','.claude','.codex','dist','artifacts'}
    candidates=[]
    for folder,dirs,files in os.walk(ROOT,followlinks=False):
        base=Path(folder)
        dirs[:]=[name for name in dirs if name not in skipped_dirs and not (base/name).is_symlink() and (base/name).relative_to(ROOT).as_posix() not in {'backend/data','mobile/android','mobile/ios','backend/ocr-runtime/models'}]
        for name in files:
            path=base/name
            if path.is_symlink():continue
            relative=path.relative_to(ROOT).as_posix()
            if name.startswith('.env') and name!='.env.example':continue
            if path.suffix.lower() in {'.pem','.key','.p12','.p8','.jks','.mobileprovision'}:continue
            candidates.append(relative)
    # Windows indexers can briefly retain the emptied extraction directory.
    # Cleanup is best-effort; all integrity, content and credential checks remain fatal.
    with tempfile.TemporaryDirectory(prefix='package-check-',dir=output,ignore_cleanup_errors=True) as temporary:
        scratch=Path(temporary).resolve()
        if not scratch.is_relative_to(output.resolve()):raise ValueError('Temporary validation directory must stay inside artifacts')
        git(['init','--bare',str(scratch/'ignore.git')])
        ignored=git(['--git-dir='+str(scratch/'ignore.git'),'--work-tree='+str(ROOT),'check-ignore','--no-index','-z','--stdin'],data=('\0'.join(candidates)+'\0').encode()).stdout.decode().split('\0')
        files=sorted(set(candidates)-set(ignored))
        entries=[]
        for name in files:
            content=(ROOT/name).read_bytes()
            if any(secret in content for secret in secrets):raise ValueError('Local environment credential found in source file: '+name)
            if (ROOT/name).suffix.lower() in {'.py','.json','.md','.sh','.ps1','.ts','.tsx','.yaml','.yml','.html','.js','.cjs','.mjs'}:
                text=content.decode('utf-8',errors='ignore')
                if re.search(r'(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-proj-[A-Za-z0-9_-]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)',text):
                    raise ValueError('Possible private key/token in source file: '+name)
            entries.append({'path':name,'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()})
        for required in ['.gitignore','.env.example','mobile/.env.example','MACBOOK-SETUP.md','scripts/setup-mac.sh','backend/requirements.txt','mobile/package-lock.json']:
            if required not in files:raise ValueError('Required source/template missing: '+required)
        manifest={'format':1,'created_utc':datetime.now(timezone.utc).isoformat(),'source_files':len(entries),'source_bytes':sum(e['bytes'] for e in entries),'excludes':'Gitignored data, installed dependencies, models, private env/key files, Git metadata and machine-specific agent settings','database_included':False,'setup':'MACBOOK-SETUP.md','files':entries}
        archive=output/(args.name+'.zip')
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as package:
            for entry in entries:
                name=entry['path'];info=zipfile.ZipInfo.from_file(ROOT/name,'KYP/'+name);info.create_system=3;info.external_attr=((0o100755 if name.endswith('.sh') else 0o100644)<<16);info.compress_type=zipfile.ZIP_DEFLATED
                package.writestr(info,(ROOT/name).read_bytes())
            package.writestr('KYP/PACKAGE-MANIFEST.json',json.dumps(manifest,indent=2))
        with zipfile.ZipFile(archive) as package:
            if package.testzip():raise ValueError('Archive integrity failure')
            package.extractall(scratch/'extract')
        tree=scratch/'extract'/'KYP'
        git(['-C',str(tree),'init','-b','main'])
        added=git(['-C',str(tree),'add','.'])
        if added.returncode:raise ValueError('Extracted source could not be staged')
        staged=git(['-C',str(tree),'ls-files','-z']).stdout.decode().split('\0')
        if set(filter(None,staged))!=set(files)|{'PACKAGE-MANIFEST.json'}:raise ValueError('Git staged files differ from validated archive contents')
        for entry in entries:
            if hashlib.sha256((tree/entry['path']).read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('Extracted content mismatch')
        examples=['.env','mobile/.env.local','backend/data/kyp.sqlite3','mobile/node_modules/test.js','backend/.venv/bin/python','backend/ocr-runtime/models/eng.traineddata','artifacts/transfer.zip']
        excluded=git(['-C',str(tree),'check-ignore','--no-index','-z','--stdin'],data=('\0'.join(examples)+'\0').encode()).stdout.decode().split('\0')
        if not set(examples)<=set(excluded):raise ValueError('An expected private/generated path is not ignored')
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n',encoding='utf-8')
    archive.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'source_files':len(entries),'sha256':digest,'archive_integrity':'pass','extraction_hashes':'pass','git_stage_validation':'pass','private_generated_ignore_checks':'pass','local_credential_scan':'pass'},indent=2))

if __name__=='__main__':main()
