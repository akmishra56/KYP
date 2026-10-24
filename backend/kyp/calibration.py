"""Offline isotonic calibration experiment; never enables production probabilities."""
import argparse,hashlib,json,math
from collections import defaultdict
from pathlib import Path
from .matcher import match_many,MATCHER_VERSION
from .parser import Token
from .repository import Repository

def fit_isotonic(pairs):
    grouped=defaultdict(list)
    for score,label in pairs:
        if not 0<=score<=1 or label not in (0,1):raise ValueError('Invalid similarity or correctness label')
        grouped[score].append(label)
    blocks=[]
    for score,labels in sorted(grouped.items()):
        blocks.append([score,score,sum(labels),len(labels)])
        while len(blocks)>1 and blocks[-2][2]/blocks[-2][3]>blocks[-1][2]/blocks[-1][3]:
            b=blocks.pop();a=blocks.pop();blocks.append([a[0],b[1],a[2]+b[2],a[3]+b[3]])
    return [{'lower':a,'upper':b,'probability':s/n,'samples':n} for a,b,s,n in blocks]

def predict(blocks,score):
    if not blocks:raise ValueError('Calibration requires training samples')
    for block in blocks:
        if score<=block['upper']:return block['probability']
    return blocks[-1]['probability']

def metrics(blocks,pairs):
    values=[(predict(blocks,x),y) for x,y in pairs]
    if not values:raise ValueError('Held-out examples are required')
    bins=[];ece=0
    for index in range(10):
        rows=[(p,y) for p,y in values if min(9,int(p*10))==index]
        if not rows:continue
        n=len(rows);accuracy=sum(y for p,y in rows)/n;mean=sum(p for p,y in rows)/n
        z=1.96;den=1+z*z/n;center=(accuracy+z*z/(2*n))/den;half=z*math.sqrt(accuracy*(1-accuracy)/n+z*z/(4*n*n))/den
        bins.append({'bin':index,'samples':n,'mean_probability':mean,'observed_accuracy':accuracy,'wilson_95':[max(0,center-half),min(1,center+half)]})
        ece+=n/len(values)*abs(mean-accuracy)
    return {'samples':len(values),'brier':sum((p-y)**2 for p,y in values)/len(values),'expected_calibration_error':ece,'reliability_bins':bins}

def experiment(records,repository):
    if not isinstance(records,list) or not records:raise ValueError('Provide labelled, permitted real OCR phrases')
    products={};images={};seen=set();groups=defaultdict(lambda:defaultdict(list))
    for row in records:
        if not row.get('permission') or not row.get('reviewed_by') or row.get('is_real') is not True:raise ValueError('Real examples, permission and independent ground truth are required')
        context=row.get('context');split=row.get('split');product=row.get('product_id');image=row.get('image_id');position=row.get('position')
        if context not in {'food','cosmetics'} or split not in {'baseline','held_out'} or not product or not image or not isinstance(position,int) or position<0:raise ValueError('Invalid context, split or sample identity')
        if product in products and products[product]!=split:raise ValueError('Product leakage across calibration splits')
        products[product]=split
        if image in images and images[image]!=(product,split):raise ValueError('An image cannot change product or calibration split')
        images[image]=(product,split);key=(image,position)
        if key in seen:raise ValueError('Duplicate ingredient sample')
        seen.add(key)
        expected=row['expected_id']
        if expected is not None and expected not in {x['id'] for x in repository.index(context=context)}:raise ValueError('Ground truth ID not in the selected catalog')
        phrase=row.get('phrase','')
        if not isinstance(phrase,str) or not phrase.strip() or len(phrase)>512:raise ValueError('Provide a single OCR phrase')
        candidates=match_many([Token(phrase,phrase,0)],repository,context)[0]['closest_candidates']
        if not candidates:continue
        candidate=candidates[0];groups[context][split].append((candidate['similarity'],int(candidate['id']==expected)))
    reports={}
    for context,sets in groups.items():
        training=sets['baseline'];held=sets['held_out']
        if len(training)<100 or len(held)<30 or {y for x,y in training}!={0,1} or {y for x,y in held}!={0,1}:
            raise ValueError('Each context needs 100 baseline and 30 held-out candidates, with both correct and incorrect matches')
        blocks=fit_isotonic(training);reports[context]={'blocks':blocks,'held_out':metrics(blocks,held),'baseline_samples':len(training)}
    if set(reports)!={'food','cosmetics'}:raise ValueError('Both launch contexts need independent calibration evidence')
    catalog=hashlib.sha256(json.dumps(repository.index(),sort_keys=True).encode()).hexdigest()
    return {'matcher_version':MATCHER_VERSION,'catalog_sha256':catalog,'model':'isotonic cosine-only experiment','contexts':reports,'production_enabled':False,'review_required':'Independent evaluation of representativeness, errors and reliability; runtime probabilities remain null'}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('samples');parser.add_argument('--db',default='data/kyp.sqlite3');parser.add_argument('--output',default='data/calibration-experiment.json');args=parser.parse_args()
    result=experiment(json.loads(Path(args.samples).read_text(encoding='utf-8')),Repository(args.db));path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,indent=2))
    print('Offline model and aggregate reliability report written; production probabilities remain disabled.')
if __name__=='__main__':main()
