"""Diagnostic comparison on two user-supplied photos; no benchmark accuracy claim."""
import io,json,subprocess,tempfile
from pathlib import Path
import httpx
from PIL import Image,ImageOps
ROOT=Path(__file__).resolve().parents[2]
PYTHON=ROOT/'backend/data/ocr-evaluation-env/Scripts/python.exe'
report=[]
with tempfile.TemporaryDirectory(prefix='kyp-compare-') as folder, httpx.Client(base_url='http://127.0.0.1:8001',timeout=60) as client:
 cases=[]
 for index,name in enumerate(['maggi masala.jpeg','maggi masala 2.jpeg']):
  source=ROOT/'docs/images'/name
  with Image.open(source) as im:
   im=ImageOps.exif_transpose(im).convert('RGB');w,h=im.size
   # Diagnostic crop coordinates are specific to these supplied photos.
   x,y,cw,ch=(.11,.07,.31,.33) if index==0 else (.18,.03,.27,.23)
   crop=im.crop((round(x*w),round(y*h),round((x+cw)*w),round((y+ch)*h)))
   crop=crop.resize((crop.width*3,crop.height*3))
   path=Path(folder)/(str(index)+'.png');crop.save(path)
  for kind,file in [('full',source),('ingredient-crop-3x',path)]:cases.append({'case':name+':'+kind,'path':str(file)})
 inputs=Path(folder)/'inputs.json';output=Path(folder)/'rapid.json';inputs.write_text(json.dumps(cases),encoding='utf-8')
 subprocess.run([str(PYTHON),'-X','utf8',str(ROOT/'backend/tools/rapidocr_worker.py'),str(inputs),str(output)],check=True,timeout=120)
 report+=json.loads(output.read_text(encoding='utf-8'))
 for row in cases:
  file=Path(row['path']);response=client.post('/scans/image',content=file.read_bytes(),headers={'Content-Type':'image/png' if file.suffix=='.png' else 'image/jpeg','X-Image-Processing-Consent':'yes','X-Product-Context':'food'})
  response.raise_for_status();data=response.json();report.append({'case':row['case'],'provider':data['ocr']['provider'],'text':data['text'],'parse_warning':data['parse_warning']})
summary={'scope':'Two supplied photos of one product; diagnostic only. Not the 30-image benchmark or calibrated accuracy.','results':report,'production_engine_changed':False}
(ROOT/'backend/data/maggi-engine-comparison.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
for row in report:
 print(row['case'],row.get('provider'),row.get('error',''),len(row.get('text','')),'characters',row.get('parse_warning'))
 if 'ingredient-crop' in row['case']:print(row.get('text','')[:900])
