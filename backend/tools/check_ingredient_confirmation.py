"""Synthetic per-ingredient review UI integration; no calibration claims."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
 page=browser.new_page(viewport={'width':1280,'height':1000});errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8001');page.locator('#text').fill('Sodlum chlorlde, Sugar, Mystery blend');page.locator('#parse').click()
 page.locator('[data-review-row="0"]').wait_for()
 assert not page.locator('#matchingDetails').is_visible()
 assert page.locator('#confirm').is_disabled()
 row=page.locator('[data-review-row="0"]');row.get_by_role('button',name='Confirm SODIUM CHLORIDE',exact=True).click()
 assert page.locator('#confirm').is_disabled()
 page.locator('[data-review-row="2"] [data-unknown="true"]').click()
 assert page.locator('#confirm').is_enabled()
 folder=ROOT/'docs/screenshots';folder.mkdir(exist_ok=True)
 page.screenshot(path=str(folder/'stage1-ingredient-confirmation.png'),full_page=True)
 with page.expect_response(lambda r:r.url.endswith('/confirm')) as pending:page.locator('#confirm').click()
 data=pending.value.json();assert data['matched_count']==2 and data['tokens'][0]['match_method']=='user_confirmed'
 assert data['tokens'][2]['confirmation_status']=='kept_unknown'
 page.locator('#results').wait_for(state='visible')
 page.locator('#showDetails').click();assert 'Not calibrated' in page.locator('#matchingDetails').inner_text()
 page.locator('#text').fill('Sodlum chlorlde, Mystery blend');assert not page.locator('#review').is_visible()
 page.locator('#parse').click();page.locator('[data-review-row="0"]').wait_for()
 assert page.locator('#confirm').is_disabled()
 assert page.locator('[aria-pressed="true"]').count()==0
 page.set_viewport_size({'width':390,'height':844})
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 page.screenshot(path=str(folder/'stage1-ingredient-confirmation-mobile.png'),full_page=True)
 page.locator('#productContext').select_option('cosmetics');assert not page.locator('#review').is_visible()
 assert not errors,errors
 browser.close()
 print('PASS: mandatory individual review, explicit candidate/unknown, details optional, edit/type invalidation, phone layout, no browser errors')
