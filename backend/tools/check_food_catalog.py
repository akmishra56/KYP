from review_fixture import decisions, review_browser
"""Local Chrome/API food catalog check with synthetic representative label text."""
import json
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
BASE='http://127.0.0.1:8001'
TEXT='Ingredients: Refined wheat flour, Salt, Sugar, Maltodextrin, Cumin, Turmeric, MSG, INS 330, Mystery blend. Contains: Wheat. May contain milk.'

def main():
 with httpx.Client(base_url=BASE,timeout=30) as client:
  scan=client.post('/scans',json={'text':TEXT,'product_context':'food'});scan.raise_for_status();session=scan.json()
  assert len(session['tokens'])==9
  response=client.post('/scans/'+session['id']+'/confirm',json={'text':TEXT,'product_context':'food','confirmations':decisions(session)},headers={'X-Scan-Token':session['scan_token']});response.raise_for_status();data=response.json()
  assert data['matched_count']==8 and data['total_count']==9,data
  for token in data['tokens'][:8]:
   desc=token['ingredient']['description'];assert desc and desc['sources']
   assert desc['provenance']['context']=='food'
  assert data['tokens'][-1]['match_status']=='unmatched'
  salt=data['tokens'][1]['ingredient']['id']
  food=client.get('/ingredients/'+salt,params={'product_context':'food'}).json()
  cosmetic=client.get('/ingredients/'+salt,params={'product_context':'cosmetics'}).json()
  neutral=client.get('/ingredients/'+salt).json()
  assert food['description']['provenance']['context']=='food'
  assert cosmetic['description']['provenance']['context']=='cosmetics'
  assert neutral['description'] is None
 with sync_playwright() as playwright:
  browser=playwright.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
  page=browser.new_page(viewport={'width':1280,'height':1000});errors=[]
  page.on('pageerror',lambda error:errors.append(str(error)))
  page.goto(BASE);assert page.locator('#productContext').input_value()=='food'
  page.locator('#text').fill(TEXT);page.locator('#parse').click();page.locator('#confirm').wait_for(state='visible');review_browser(page);page.locator('#confirm').click()
  page.wait_for_function("document.getElementById('summary').textContent.includes('8 of 9')")
  page.locator('#results').wait_for(state='visible')
  assert page.locator('#rows .row').count()==9
  assert 'In cosmetics' not in page.locator('#rows').inner_text()
  assert 'In food' in page.locator('#rows').inner_text()
  assert not errors,errors
  folder=ROOT/'docs/screenshots';folder.mkdir(parents=True,exist_ok=True)
  page.screenshot(path=str(folder/'stage1-food-catalog.png'),full_page=True)
  page.locator('#productContext').select_option('cosmetics')
  assert not page.locator('#results').is_visible()
  assert not page.locator('#review').is_visible()
  page.set_viewport_size({'width':390,'height':844});page.locator('#productContext').select_option('food')
  page.locator('#parse').click();page.locator('#confirm').wait_for(state='visible');review_browser(page);page.locator('#confirm').click()
  page.wait_for_function("document.getElementById('summary').textContent.includes('8 of 9')")
  page.locator('#results').wait_for(state='visible')
  assert page.locator('#rows .row').count()==9
  assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
  page.screenshot(path=str(folder/'stage1-food-mobile-browser.png'),full_page=True)
  browser.close()
 report={'label_type':'synthetic representative text; not a Maggi OCR benchmark','matched':8,'total':9,'unresolved':'Mystery blend','category_isolation':True,'category_changes_invalidate_results':True,'food_advisories_excluded':True,'browser_errors':errors,'mobile_browser_no_horizontal_overflow':True}
 (ROOT/'backend/data/food-browser-check.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':main()
