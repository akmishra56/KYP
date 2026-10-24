from review_fixture import decisions, review_browser
"""Real engine smoke test on a generated label, not a real-label accuracy benchmark."""
import io
import json
import os
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from fastapi.testclient import TestClient
from kyp.api import create_app
from kyp.ocr import default_provider

def main():
    font_path=Path('C:/Windows/Fonts/arial.ttf')
    if not font_path.exists():
        raise SystemExit('Set up a suitable test font for this platform before running the smoke test.')
    image=Image.new('RGB',(2000,400),'white')
    draw=ImageDraw.Draw(image);font=ImageFont.truetype(str(font_path),44)
    draw.multiline_text((45,45),'Ingredients: Water, Glycerin, Citric Acid,\nEthanol, Mystery blend.',fill='black',font=font,spacing=20)
    content=io.BytesIO();image.save(content,format='PNG')
    db=os.getenv('KYP_DATABASE_URL') or 'data/kyp.sqlite3'
    with TestClient(create_app(db,default_provider())) as client:
        response=client.post('/scans/image',content=content.getvalue(),headers={'Content-Type':'image/png','X-Image-Processing-Consent':'yes'})
        if response.status_code!=201:
            raise SystemExit('OCR smoke failed: '+str(response.json()))
        scan=response.json()
        result=client.post('/scans/'+scan['id']+'/confirm',json={'text':scan['text'],'confirmations':decisions(scan)},headers={'X-Scan-Token':scan['scan_token']}).json()
        expected=['water','glycerin','citric acid','ethanol','mystery blend']
        recognized=[t['text'].casefold() for t in result['tokens']]
        if recognized!=expected:raise SystemExit('OCR output differs from generated label: '+str(recognized))
        if result['matched_count']!=4:raise SystemExit('Expected four matches in the seeded repository')
        report={'fixture':'synthetic high-contrast generated label; not a real-world benchmark','ocr_provider':scan['ocr']['provider'],'expected_tokens':5,'correct_tokens':5,'matched_tokens':result['matched_count'],'description_count':sum(bool(t['ingredient'] and t['ingredient']['description']) for t in result['tokens']),'unknown_tokens':1,'database':client.get('/health').json()['repository']}
        Path('data').mkdir(exist_ok=True)
        Path('data/ocr-smoke-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))

if __name__=='__main__':main()
