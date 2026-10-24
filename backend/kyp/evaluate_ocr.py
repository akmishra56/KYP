"""Compare permitted real-label OCR without fabricating benchmark evidence."""
import argparse
import hashlib
import json
import time
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from .ocr import default_provider, TesseractOCR, TesseractJSOCR
from .parser import parse_label
from .ocr_experiments import RapidOCRExperiment
from .matcher import normalize

def validate_manifest(records, base):
    if not isinstance(records,list) or not records:raise ValueError('Provide a non-empty label corpus')
    seen=set();products={}
    for record in records:
        if not record.get('permission') or not record.get('reviewed_by') or not record.get('expected_tokens'):
            raise ValueError('Each image needs permission, a ground-truth reviewer and expected tokens')
        if record.get('context') not in {'food','cosmetics'}:raise ValueError('Set food or cosmetics context')
        if record.get('split') not in {'baseline','held_out'} or not record.get('product_id'):raise ValueError('Provide product ID and baseline/held_out split')
        if any(not isinstance(t,str) or not t.strip() for t in record['expected_tokens']):raise ValueError('Expected ingredient phrases must be non-empty strings')
        path=(base/record['image']).resolve()
        if not path.is_relative_to(base.resolve()):raise ValueError('Corpus images must stay inside the manifest folder')
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in seen:raise ValueError('Duplicate image cannot count as another sample')
        seen.add(digest)
        product=record['product_id'];split=record['split']
        if product in products and products[product]!=split:raise ValueError('A product cannot appear in baseline and held-out sets')
        products[product]=split
    return records

def evaluate(records, base, provider, engine):
    totals=defaultdict(lambda:{'images':0,'correct':0,'detected':0,'expected':0,'errors':0,'seconds':0.0})
    for record in records:
        expected=[normalize(t) for t in record['expected_tokens']]
        tags={'overall','context:'+record['context'],'split:'+record['split']}|{'condition:'+str(t) for t in record.get('tags',[])}
        started=time.monotonic()
        try:
            if engine=='native-recorded':
                text=record['recorded_ocr']['native']
            else:text=provider.read((base/record['image']).read_bytes())['text']
            actual=[normalize(t.text) for t in parse_label(text,context=record['context'])]
            correct=sum(block.size for block in SequenceMatcher(None,expected,actual,autojunk=False).get_matching_blocks());error=0
        except (ValueError,RuntimeError,KeyError,OSError):actual=[];correct=0;error=1
        elapsed=time.monotonic()-started
        for tag in tags:
            total=totals[tag];total['images']+=1;total['correct']+=correct;total['detected']+=len(actual);total['expected']+=len(expected);total['errors']+=error;total['seconds']+=elapsed
    for total in totals.values():
        total['precision']=total['correct']/total['detected'] if total['detected'] else 0
        total['recall']=total['correct']/total['expected'] if total['expected'] else 0
        total['mean_seconds']=total.pop('seconds')/total['images']
    return dict(totals)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('manifest');parser.add_argument('--output',default='data/ocr-evaluation.json');parser.add_argument('--engines',default='tesseractjs');args=parser.parse_args()
    path=Path(args.manifest).resolve();records=validate_manifest(json.loads(path.read_text(encoding='utf-8')),path.parent)
    providers={'default':default_provider,'tesseractjs':TesseractJSOCR,'tesseract':TesseractOCR,'native-recorded':lambda:None,'rapidocr':RapidOCRExperiment}
    names=args.engines.split(',')
    if any(name not in providers for name in names):parser.error('Engines: '+', '.join(providers))
    metrics={name:evaluate(records,path.parent,providers[name](),name) for name in names}
    real=[r for r in records if r.get('is_real') is True]
    report={'corpus_size':len(records),'real_images':len(real),'minimum_30_real_images_met':len(real)>=30,'held_out_images':sum(r['split']=='held_out' for r in real),'engines':metrics,'release_status':'Not automatically signed off; agree targets before held-out evaluation','native_recording_latency':'Unavailable; timings for native-recorded measure only parsing'}
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Aggregate metrics written. Source images and OCR text are not copied into the report.')

if __name__=='__main__':main()
