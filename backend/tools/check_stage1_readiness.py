"""Local Stage 1 representative flow checks; synthetic fixtures, not a real-label pilot."""
import json
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright
from review_fixture import review_browser
BASE='http://127.0.0.1:8001';ROOT=Path(__file__).resolve().parents[2]
TEXT='Seasoning (Salt, Spices [Cumin, Turmeric], Onion powder), Whole milk powder, Palm oil, Mystery blend'
with httpx.Client(base_url=BASE) as client:
 scan=client.post('/scans',json={'text':TEXT,'product_context':'food'}).json();preview=scan['match_preview']
 assert [t['text'] for t in preview]==['Salt','Cumin','Turmeric','Onion powder','Whole milk powder','Palm oil','Mystery blend']
 assert preview[1]['parent_path']==['Seasoning','Spices']
 assert all(preview[i]['ingredient']['description'] for i in range(5))
 assert preview[5]['ingredient']['description'] is None
 assert preview[5]['ingredient']['description_status']=='unavailable'
 assert client.post('/scans/'+scan['id']+'/confirm',headers={'X-Scan-Token':scan['scan_token']},json={'text':TEXT,'product_context':'food'}).status_code==409
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
 page=browser.new_page(viewport={'width':390,'height':844});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(BASE);page.locator('#text').fill(TEXT);page.locator('#parse').click();page.locator('[data-review-row="6"]').wait_for()
 assert 'Seasoning / Spices' in page.locator('#tokens').inner_text()
 assert page.locator('#confirm').is_disabled();review_browser(page);page.locator('#confirm').click();page.locator('#results').wait_for(state='visible')
 assert '6 of 7 matched' in page.locator('#summary').inner_text()
 assert 'Description unavailable' in page.locator('#rows').inner_text()
 assert 'Seasoning / Spices' in page.locator('#rows').inner_text()
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 page.screenshot(path=str(ROOT/'docs/screenshots/stage1-nested-food.png'),full_page=True)
 page.locator('#text').fill('Onion powder, Garlic powder, Skimmed milk powder');assert not page.locator('#results').is_visible()
 page.route('**/scans',lambda route:route.abort())
 page.locator('#parse').click();page.wait_for_function("document.getElementById('status').classList.contains('error')")
 assert not page.locator('#results').is_visible()
 page.unroute('**/scans');page.locator('#parse').click();page.locator('#review').wait_for(state='visible')
 review_browser(page);page.locator('#confirm').click();page.locator('#results').wait_for(state='visible')
 assert '3 of 3 matched' in page.locator('#summary').inner_text()
 # Narrow view and keyboard access remain available after recovery.
 page.set_viewport_size({'width':320,'height':740});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 page.locator('#showDetails').focus();page.keyboard.press('Enter');assert page.locator('#matchingDetails').is_visible()
 assert not errors,errors
 browser.close()
report={'fixture':'synthetic representative ingredients; not a product pilot or real OCR benchmark','nested_leaves':7,'matched':6,'parent_paths_visible':True,'new_food_descriptions_available':True,'palm_description_rights_gate_preserved':True,'missing_confirmation_rejected':True,'network_failure_and_retry':True,'narrow_320px_no_overflow':True,'keyboard_details_access':True,'browser_errors':errors}
(ROOT/'backend/data/stage1-readiness-check.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
