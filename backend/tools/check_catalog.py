from review_fixture import decisions, review_browser
"""Local Stage 1 browser integration check; requires the reviewed development catalog."""
import json
import time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
BASE='http://127.0.0.1:8001'
TEXT='Ingredients: Water (Aqua/Eau), Glycerin, Niacinamide, Cocamidopropyl Betaine, Retinol, Mystery blend'

def main():
 with httpx.Client(base_url=BASE,timeout=30) as client:
  scan=client.post('/scans',json={'text':TEXT,'product_context':'cosmetics'});scan.raise_for_status();session=scan.json()
  start=time.perf_counter()
  response=client.post('/scans/'+session['id']+'/confirm',json={'text':TEXT,'product_context':'cosmetics','confirmations':decisions(session)},headers={'X-Scan-Token':session['scan_token']});response.raise_for_status()
  data=response.json();duration=round(time.perf_counter()-start,3)
  assert data['matched_count']==5 and data['total_count']==6
  tokens=data['tokens']
  assert tokens[0]['match_method']=='user_confirmed' and tokens[0]['confirmation_status']=='confirmed'
  assert all(t['ingredient']['description']['sources'] for t in tokens[:4])
  assert tokens[4]['ingredient']['description_status']=='unavailable'
  assert tokens[5]['match_status']=='unmatched' and tokens[5]['ingredient'] is None
  for token in tokens[:4]:
   desc=token['ingredient']['description']
   assert desc['provenance']['context']=='cosmetics'
   assert 'not human or scientific review' in desc['reviewed_by']
  cas=client.post('/scans',json={'text':'98-92-0'}).json()
  result=client.post('/scans/'+cas['id']+'/confirm',json={'text':'98-92-0'},headers={'X-Scan-Token':cas['scan_token']}).json()
  assert result['tokens'][0]['ingredient']['name']=='NIACINAMIDE'
 with sync_playwright() as playwright:
  browser=playwright.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
  page=browser.new_page(viewport={'width':1280,'height':1000});errors=[]
  page.on('pageerror',lambda error:errors.append(str(error)))
  page.goto(BASE);page.locator('#productContext').select_option('cosmetics');page.locator('#text').fill(TEXT);page.locator('#parse').click()
  page.locator('#confirm').wait_for(state='visible');review_browser(page);page.locator('#confirm').click()
  page.wait_for_function("document.getElementById('summary').textContent.includes('5 of 6')")
  assert page.locator('#rows .row').count()==6
  assert 'In cosmetics' in page.locator('#rows').inner_text()
  assert page.locator('#rows a').count()>0
  assert not errors,errors
  folder=ROOT/'docs/screenshots';folder.mkdir(parents=True,exist_ok=True)
  page.screenshot(path=str(folder/'stage1-expanded-catalog.png'),full_page=True)
  page.locator('#text').fill('Ingredients: Mystery blend')
  assert not page.locator('#results').is_visible(), 'Editing must invalidate previous results'
  browser.close()
 report={'matched':5,'total':6,'missing_description_visible':True,'unknown_preserved':True,'cas_alias_verified':True,'browser_errors':errors,'confirmation_seconds_local':duration}
 (ROOT/'backend/data/catalog-browser-check.json').write_text(json.dumps(report,indent=2))
 print(json.dumps(report,indent=2))

if __name__=='__main__':main()
