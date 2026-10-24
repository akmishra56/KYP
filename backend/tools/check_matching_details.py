from review_fixture import review_browser
"""Local vector-matching and disclosure integration check with synthetic inputs."""
import io
import json
from pathlib import Path
import httpx
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
BASE='http://127.0.0.1:8001'
TEXT='Ingredients: Sodlum chlorlde, Sugar, Niacinamide'

def main():
 with httpx.Client(base_url=BASE,timeout=55) as client:
  scan=client.post('/scans',json={'text':TEXT,'product_context':'food'});scan.raise_for_status();food=scan.json()['match_preview']
  assert len(food)==3 and food[0]['words']==['sodlum','chlorlde']
  assert food[0]['closest_candidates'][0]['name']=='SODIUM CHLORIDE'
  assert food[0]['match_status']=='unmatched' and food[1]['match_status']=='matched'
  assert food[2]['match_status']=='unmatched'
  assert all(c['name']!='NIACINAMIDE' for c in food[2]['closest_candidates'])
  assert all(t['match_probability'] is None for t in food)
  image=Image.new('RGB',(1800,300),'white');draw=ImageDraw.Draw(image);font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',44)
  draw.text((40,50),'Ingredients: Sodium chloride, Sugar, Citric acid',font=font,fill='black');buffer=io.BytesIO();image.save(buffer,format='PNG')
  result=client.post('/scans/image',content=buffer.getvalue(),headers={'Content-Type':'image/png','X-Image-Processing-Consent':'yes','X-Product-Context':'food'});result.raise_for_status();ocr=result.json()
  assert len(ocr['match_preview'])==3
  assert ocr['match_preview'][0]['words']==['sodium','chloride']
  assert all(t['match_status']=='matched' for t in ocr['match_preview'])
 with sync_playwright() as playwright:
  browser=playwright.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
  page=browser.new_page(viewport={'width':1280,'height':1000});errors=[]
  page.on('pageerror',lambda error:errors.append(str(error)))
  page.goto(BASE);page.locator('#text').fill(TEXT)
  assert not page.locator('#matchingDetails').is_visible()
  assert page.locator('#showDetails').inner_text()=='Show Details'
  page.locator('#showDetails').click();page.locator('#matchingDetails .row').first.wait_for(state='visible')
  details=page.locator('#matchingDetails').inner_text()
  assert 'SODIUM CHLORIDE' in details and 'cosine similarity' in details
  assert 'Match probability: Not calibrated' in details
  assert page.locator('#matchingDetails .row').count()==3
  review_browser(page);page.locator('#confirm').click();page.locator('#results').wait_for(state='visible')
  assert '1 of 3 matched' in page.locator('#summary').inner_text()
  assert page.locator('#showDetails').is_visible()
  folder=ROOT/'docs/screenshots';folder.mkdir(parents=True,exist_ok=True)
  page.screenshot(path=str(folder/'stage1-cosine-details.png'),full_page=True)
  page.locator('#showDetails').click();assert not page.locator('#matchingDetails').is_visible()
  page.locator('#productContext').select_option('cosmetics')
  assert not page.locator('#matchingDetails').is_visible() and not page.locator('#results').is_visible()
  page.locator('#showDetails').click();page.locator('#matchingDetails .row').first.wait_for(state='visible')
  assert 'Identified: NIACINAMIDE' in page.locator('#matchingDetails').inner_text()
  page.set_viewport_size({'width':390,'height':844})
  assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
  page.screenshot(path=str(folder/'stage1-cosine-details-mobile.png'),full_page=True)
  page.locator('#text').fill('Salt')
  assert not page.locator('#matchingDetails').is_visible()
  assert page.locator('#showDetails').get_attribute('aria-expanded')=='false'
  assert not errors,errors
  browser.close()
 report={'fixture':'synthetic; not probability calibration data','comma_phrases':3,'word_sets_preserved':True,'category_filter_verified':True,'cosine_candidate_verified':True,'uncertain_candidate_not_auto_confirmed':True,'probabilities_not_fabricated':True,'details_hidden_until_clicked':True,'details_available_after_lookup':True,'edits_and_type_changes_clear_details':True,'ocr_to_phrase_to_vector_verified':True,'mobile_browser_no_overflow':True,'browser_errors':errors}
 (ROOT/'backend/data/matching-details-check.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':main()
