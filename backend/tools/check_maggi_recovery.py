"""Actual supplied third-photo OCR -> explicit comma recovery -> lookup regression."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
 page=browser.new_page(viewport={'width':390,'height':844});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8001');page.locator('#photo').set_input_files(str(ROOT/'docs/images/maggi masala 3.jpeg'));page.locator('#consent').check()
 with page.expect_response(lambda r:r.url.endswith('/scans/image'),timeout=60000) as pending:page.locator('#read').click()
 original=pending.value.json();assert original['parse_warning']
 page.locator('#review').wait_for(state='visible');assert page.locator('#confirm').is_disabled()
 assert 'Lookup is blocked' in page.locator('#confirmationSummary').inner_text()
 assert 'All flagged' not in page.locator('#confirmationSummary').inner_text()
 text=page.locator('#text').input_value()
 page.once('dialog',lambda d:d.accept())
 with page.expect_response(lambda r:r.url.endswith('/review')) as pending:page.locator('#recover').click()
 recovered=pending.value.json();assert recovered['parsing_mode']=='comma_review'
 assert recovered['text']==text and recovered['tokens'] and not recovered['parse_warning']
 assert all(t['confirmation_required'] for t in recovered['match_preview'])
 assert page.locator('#text').input_value()==text
 first=True
 for token in recovered['match_preview']:
  row=page.locator('[data-review-row="'+str(token['position'])+'"]')
  selected=next((o for o in token['confirmation_options'] if token['text'].casefold()=='sugar' and o['name']=='SUCROSE'),None)
  if selected:row.locator('[data-candidate-id="'+selected['id']+'"]').click()
  else:row.locator('[data-unknown="true"]').click()
  if first and len(recovered['tokens'])>1:assert page.locator('#confirm').is_disabled()
  first=False
 assert page.locator('#confirm').is_enabled()
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 page.screenshot(path=str(ROOT/'docs/screenshots/maggi3-recovery-review.png'),full_page=True)
 with page.expect_response(lambda r:r.url.endswith('/confirm')) as pending:page.locator('#confirm').click()
 assert pending.value.status==200,pending.value.text()
 page.locator('#results').wait_for(state='visible')
 assert not errors,errors
 print('PASS: actual Maggi 3 OCR recovered into',len(recovered['tokens']),'entries; original text retained, each entry reviewed, lookup completes')
 browser.close()
