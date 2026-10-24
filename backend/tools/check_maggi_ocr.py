from review_fixture import review_browser
"""Local browser/API regression check using the supplied real Maggi photo."""
import json
from pathlib import Path
import urllib.request
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
BASE='http://127.0.0.1:8001'
PHOTO=ROOT/'docs/images/maggi masala.jpeg'

def main():
    request=urllib.request.Request(BASE+'/scans/image',data=PHOTO.read_bytes(),headers={'Content-Type':'image/jpeg','X-Image-Processing-Consent':'yes'})
    with urllib.request.urlopen(request,timeout=60) as response:
        original=json.load(response)
    assert original['text'].strip(), 'OCR text was lost'
    assert original['review_required'] is True
    assert original['parse_warning'], 'Expected the supplied image to require punctuation correction'
    report={'original_image_returns_reviewable_text':True,'original_parse_warning':original['parse_warning']}
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
        page=browser.new_page(viewport={'width':1280,'height':1000})
        errors=[];uploads=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('request',lambda request:uploads.append(request.post_data_buffer) if request.url.endswith('/scans/image') else None)
        page.goto(BASE)
        page.locator('#photo').set_input_files(str(PHOTO))
        page.locator('#cropPanel').wait_for(state='visible')
        dimensions=page.evaluate('({width:selectedImage.naturalWidth,height:selectedImage.naturalHeight})')
        assert dimensions=={'width':1280,'height':960}, 'EXIF orientation was not respected'
        page.locator('#read').click()
        page.wait_for_function("document.getElementById('status').textContent.includes('Consent')")
        assert len(uploads)==0, 'An image was uploaded before consent'
        page.locator('#consent').check()
        with page.expect_response(lambda response:response.url.endswith('/scans/image'),timeout=60000) as pending:
            page.locator('#read').click()
        assert pending.value.status==201
        page.wait_for_function("document.getElementById('text').value.length>0")
        assert page.locator('#text').input_value().strip()
        report['browser_full_image_text_visible']=True
        # Keyboard-operable percentage controls select only the ingredient column.
        for field,value in [('cropLeft','11'),('cropTop','7'),('cropWidth','31'),('cropHeight','33')]:
            page.locator('#'+field).fill(value)
            page.locator('#'+field).press('Tab')
        crop_pixels=page.evaluate('async()=>{const blob=await croppedPhoto();const bitmap=await createImageBitmap(blob);const size=[bitmap.width,bitmap.height];bitmap.close();return size;}')
        with page.expect_response(lambda response:response.url.endswith('/scans/image'),timeout=60000) as pending:
            page.locator('#read').click()
        assert pending.value.status==201
        cropped=pending.value.json()
        page.wait_for_function("document.getElementById('text').value.length>0")
        report['exported_crop_pixels']=crop_pixels
        assert crop_pixels==[397,317], 'The crop preview was not applied to the exported JPEG'
        assert not errors, errors
        screenshots=ROOT/'docs/screenshots';screenshots.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(screenshots/'maggi-ocr-review.png'),full_page=True)
        report['crop_ocr_requires_manual_review']=True
        report['crop_parse_warning']=cropped['parse_warning']
        # A user correction is validated independently; it never forces repo matches.
        page.locator('#productContext').select_option('food')
        page.locator('#text').fill('Salt, Sugar, Mystery blend')
        page.locator('#parse').click()
        page.locator('[data-review-row="2"]').wait_for()
        review_browser(page)
        page.wait_for_function("!document.getElementById('confirm').disabled")
        page.locator('#confirm').click()
        page.locator('#results').wait_for(state='visible')
        assert '2 of 3 matched' in page.locator('#summary').inner_text()
        report['corrected_text_lookup_works_without_forced_matches']=True
        report['browser_errors']=errors
        browser.close()
    output=ROOT/'backend/data/maggi-ocr-report.json'
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
