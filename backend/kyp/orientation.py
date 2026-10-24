"""Conservative English label orientation, independent of ingredient matching."""
import json
import re
from pathlib import Path

POLICY=json.loads(Path(__file__).with_name('orientation-policy.json').read_text())

def evidence(text):
    words=set(re.findall(r'[a-z]+',text.casefold()))
    hits=len(words & set(POLICY['words']))
    return {'hits':hits,'score':min(hits,12)+(POLICY['heading_bonus'] if words & {'ingredients','ingredient'} else 0)}

def choose_orientation(candidates):
    if len(candidates)!=4 or {item['rotation'] for item in candidates}!=set(POLICY['rotations']):
        raise ValueError('All four orientations are required')
    ranked=sorted([dict(rotation=item['rotation'],**evidence(item['text'])) for item in candidates],key=lambda item:(-item['score'],item['rotation']))
    best=ranked[0]
    confident=best['hits']>=POLICY['minimum_word_hits'] and best['score']>=POLICY['minimum_score'] and best['score']-ranked[1]['score']>=POLICY['minimum_margin']
    return {'rotation':best['rotation'] if confident else 0,'status':'confident' if confident else 'uncertain','policy_version':POLICY['version']}
