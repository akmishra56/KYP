"""Real local OCR and Chrome orientation regression using synthetic images."""
import io
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import httpx
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
BASE='http://127.0.0.1:8001'

def png(image):
 stream=io.BytesIO();image.save(stream,format='PNG');return stream.getvalue()

def main():
 image=Image.new('RGB',(1600,380),'white');draw=ImageDraw.Draw(image);font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',44)
 draw.multiline_text((40,40),'Ingredients: water, salt, sugar, wheat flour,\ncitric acid, vegetable oil, milk powder.',font=font,fill='black',spacing=20)
 report={'fixture':'synthetic; not a real-label OCR benchmark','angles':[]}
 with httpx.Client(base_url=BASE,timeout=55) as client:
  for angle in (0,90,180,270):
   response=client.post('/images/orient',content=png(image.rotate(-angle,expand=True)),headers={'Content-Type':'image/png','X-Image-Processing-Consent':'yes'});response.raise_for_status();result=response.json()
   assert result['status']=='confident' and result['rotation']==(360-angle)%360,(angle,result)
   report['angles'].append({'input_clockwise':angle,'correction_clockwise':result['rotation']})
  blank=client.post('/images/orient',content=png(Image.new('RGB',(120,80),'white')),headers={'Content-Type':'image/png','X-Image-Processing-Consent':'yes'}).json()
  assert blank['status']=='uncertain' and blank['rotation']==0
 with sync_playwright() as playwright:
  browser=playwright.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
  page=browser.new_page(viewport={'width':1280,'height':1000});errors=[];uploads=[]
  page.on('pageerror',lambda error:errors.append(str(error)))
  page.on('request',lambda request:uploads.append(request.url) if request.url.endswith('/images/orient') else None)
  page.goto(BASE)
  colors=Image.new('RGB',(120,80));d=ImageDraw.Draw(colors)
  for box,color in [((0,0,59,39),'red'),((60,0,119,39),'green'),((0,40,59,79),'blue'),((60,40,119,79),'yellow')]:d.rectangle(box,fill=color)
  page.locator('#photo').set_input_files({'name':'corners.png','mimeType':'image/png','buffer':png(colors)})
  page.locator('#cropPanel').wait_for(state='visible')
  page.locator('#rotateRight').click();page.wait_for_function('imageRotation===90 && !rotationBusy')
  sample=page.evaluate("async()=>{const blob=await croppedPhoto(),bitmap=await createImageBitmap(blob),c=document.createElement('canvas');c.width=bitmap.width;c.height=bitmap.height;const ctx=c.getContext('2d');ctx.drawImage(bitmap,0,0);return {width:c.width,height:c.height,pixel:[...ctx.getImageData(10,10,1,1).data]};}")
  assert (sample['width'],sample['height'])==(80,120)
  assert sample['pixel'][2]>200 and sample['pixel'][0]<40,sample
  page.locator('#resetRotation').click();page.wait_for_function('imageRotation===0 && !rotationBusy')
  for field,value in [('cropLeft','20'),('cropTop','10'),('cropWidth','40'),('cropHeight','50')]:page.locator('#'+field).fill(value);page.locator('#'+field).press('Tab')
  page.locator('#rotateRight').click();page.wait_for_function('imageRotation===90 && !rotationBusy')
  crop=page.evaluate('({...crop})');assert all(abs(crop[key]-value)<0.00001 for key,value in {'x':.4,'y':.2,'width':.5,'height':.4}.items()),crop
  page.locator('#autoOrient').click();page.wait_for_function("document.getElementById('status').textContent.includes('Consent')")
  assert not uploads,'Auto orientation uploaded without consent'
  # Actual browser-to-API auto orientation updates both preview and exported pixels.
  page.locator('#photo').set_input_files({'name':'sideways-label.png','mimeType':'image/png','buffer':png(image.rotate(-90,expand=True))})
  page.wait_for_function('selectedImage && selectedImage.naturalWidth===380 && imageRotation===0')
  page.locator('#consent').check()
  page.locator('#autoOrient').click();page.wait_for_function("document.getElementById('status').textContent.startsWith('Auto oriented')",timeout=55000)
  assert page.evaluate('imageRotation')==270
  assert page.evaluate('[selectedImage.naturalWidth,selectedImage.naturalHeight]')==[1600,380]
  assert not errors,errors
  folder=ROOT/'docs/screenshots';folder.mkdir(parents=True,exist_ok=True)
  page.screenshot(path=str(folder/'stage1-image-orientation.png'),full_page=True)
  browser.close()
 report.update(blank_requires_manual=True,manual_rotation_changes_exported_pixels=True,crop_preserved=True,consent_enforced=True,browser_auto_updates_preview=True,browser_errors=errors)
 (ROOT/'backend/data/orientation-check.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':main()
