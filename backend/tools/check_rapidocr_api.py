"""Local candidate OCR -> parser -> confirmation API check on the supplied crop."""
import io,json
from pathlib import Path
from PIL import Image,ImageOps
from fastapi.testclient import TestClient
from kyp.api import create_app
from kyp.ocr_experiments import RapidOCRExperiment
ROOT=Path(__file__).resolve().parents[2]
with Image.open(ROOT/'docs/images/maggi masala 2.jpeg') as image:
 image=ImageOps.exif_transpose(image).convert('RGB');w,h=image.size
 crop=image.crop((round(.18*w),round(.03*h),round(.45*w),round(.26*h)));crop=crop.resize((crop.width*3,crop.height*3));buffer=io.BytesIO();crop.save(buffer,format='PNG')
with TestClient(create_app(ROOT/'backend/data/kyp.sqlite3',RapidOCRExperiment())) as client:
 response=client.post('/scans/image',content=buffer.getvalue(),headers={'Content-Type':'image/png','X-Image-Processing-Consent':'yes','X-Product-Context':'food'})
 assert response.status_code==201,response.text
 scan=response.json();assert scan['text'] and not scan['parse_warning'],scan.get('parse_warning')
 assert len(scan['tokens'])>15
 assert any(token['parent_path'] for token in scan['tokens'])
 assert all(token['match_probability'] is None for token in scan['match_preview'])
 url='/scans/'+scan['id']+'/confirm';headers={'X-Scan-Token':scan['scan_token']}
 assert client.post(url,headers=headers,json={'text':scan['text'],'product_context':'food'}).status_code==409
 # Simulate explicitly keeping uncertain identities unknown; do not force guesses.
 choices=[{'position':t['position'],'confirmation_key':t['confirmation_key'],'ingredient_id':None} for t in scan['match_preview'] if t['confirmation_required']]
 result=client.post(url,headers=headers,json={'text':scan['text'],'product_context':'food','confirmations':choices});assert result.status_code==200,result.text
 report={'fixture':'one supplied crop; diagnostic, not accuracy benchmark','provider':scan['ocr']['provider'],'parsed_leaf_count':len(scan['tokens']),'uncertain_rows':len(choices),'missing_confirmations_blocked':True,'explicit_unknown_lookup_passed':True,'probabilities_remain_uncalibrated':True}
 (ROOT/'backend/data/rapidocr-api-check.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
