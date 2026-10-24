"""Check scan/review/results using the populated local catalogs; no OCR claim."""
import argparse
import json
import sys
from pathlib import Path
from fastapi.testclient import TestClient
BACKEND=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BACKEND))
from kyp.api import create_app
from kyp.repository import Repository
from update_food_catalog import configured_postgres

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--postgres',action='store_true');args=parser.parse_args()
    fixture=json.loads((BACKEND/'validation/maggi-catalog-diagnostic.json').read_text(encoding='utf8'))
    report={'scope':fixture['scope'],'databases':{}}
    for name,target in [('sqlite',BACKEND/'data/kyp.sqlite3')]+([('postgresql',configured_postgres())] if args.postgres else []):
        with TestClient(create_app(target)) as client:
            text=fixture['text'];response=client.post('/scans',json={'text':text,'product_context':'food'});response.raise_for_status();scan=response.json()
            preview=scan['match_preview'];assert len(preview)==fixture['expected_total']
            headers={'X-Scan-Token':scan['scan_token']};url='/scans/'+scan['id']+'/confirm'
            assert client.post(url,headers=headers,json={'text':text,'product_context':'food'}).status_code==409
            choices=[{'position':r['position'],'confirmation_key':r['confirmation_key'],'ingredient_id':r['ingredient']['id'] if r['ingredient'] else None} for r in preview if r['confirmation_required']]
            result=client.post(url,headers=headers,json={'text':text,'product_context':'food','confirmations':choices});result.raise_for_status();data=result.json()
            assert data['matched_count']==fixture['expected_matched'],data['matched_count']
            unknown=[r['text'] for r in data['tokens'] if r['match_status']!='matched'];assert unknown==fixture['expected_unspecified'],unknown
            described=[r for r in data['tokens'] if r['ingredient'] and r['ingredient']['description']]
            assert len(described)==fixture['expected_food_descriptions']
            assert all(r['ingredient']['description']['sources'] for r in described)
            assert all(r['ingredient']['description']['provenance']['context']=='food' for r in described)
            assert next(r for r in data['tokens'] if r['text']=='Palm oil')['ingredient']['description'] is None
            # Uncertain OCR still requires review even when a code/name is recognized.
            report['databases'][name]={'total':len(preview),'matched':data['matched_count'],'food_descriptions':len(described),'unspecified':unknown,'citations_present':True,'confirmation_guard_passed':True,'palm_rights_gate_preserved':True,'catalog':Repository(target).stats()}
    (BACKEND/'data/maggi-catalog-verification.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
