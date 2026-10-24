"""Android emulator smoke for synthetic ingredient review (app open at top)."""
import re,subprocess,time,xml.etree.ElementTree as ET
from pathlib import Path
ADB=r'C:\Users\rajes\AppData\Local\Android\Sdk\platform-tools\adb.exe'
def run(*a):return subprocess.check_output([ADB,'-s','emulator-5554',*a])
def nodes():
 run('shell','uiautomator','dump','/sdcard/kyp-window.xml')
 return list(ET.fromstring(run('shell','cat','/sdcard/kyp-window.xml')).iter('node'))
def bounds(n):return list(map(int,re.findall(r'\d+',n.get('bounds'))))
def find(label):
 for n in nodes():
  b=bounds(n)
  if (n.get('text')==label or n.get('content-desc')==label) and 80<b[1]<2280 and b[3]>b[1]:return n
 return None
def tap(n):
 x,y,r,b=bounds(n);run('shell','input','tap',str((x+r)//2),str((y+b)//2))
def seek(label):
 for _ in range(8):
  n=find(label)
  if n is not None:return n
  run('shell','input','swipe','550','2050','550','850','300')
 raise AssertionError('Missing '+label)
run('shell','input','swipe','550','2050','550','950','300')
editor=next(n for n in nodes() if n.get('class')=='android.widget.EditText');tap(editor)
run('shell','input','keycombination','113','29');run('shell','input','keyevent','67')
run('shell','input','text','Sodlum%schlorlde,%sSugar,%sMystery%sblend');run('shell','input','keyevent','4')
tap(seek('Review ingredient text'))
time.sleep(1)
# Confirm stays disabled even though the details disclosure was never opened.
button=seek('Confirm and look up');assert button.get('enabled')=='false'
for _ in range(4):run('shell','input','swipe','550','850','550','2050','300')
tap(seek('Confirm SODIUM CHLORIDE'))
button=seek('Confirm and look up');assert button.get('enabled')=='false'
unknowns=[n for n in nodes() if (n.get('content-desc')=='Keep unknown') and 80<bounds(n)[1]<2280]
if not unknowns:
 run('shell','input','swipe','550','850','550','1400','300')
 unknowns=[n for n in nodes() if n.get('content-desc')=='Keep unknown' and 80<bounds(n)[1]<2280]
assert unknowns;tap(unknowns[-1])
button=seek('Confirm and look up');assert button.get('enabled')=='true'
path=Path(__file__).resolve().parents[2]/'docs/screenshots/stage1-native-ingredient-confirmation.png'
path.write_bytes(run('exec-out','screencap','-p'))
tap(button);time.sleep(1)
labels=[n.get('text') or n.get('content-desc') for n in nodes()]
assert any('2 of 3' in label for label in labels),labels
print('PASS: Android blocks partial review, accepts candidate/unknown, completes 2 of 3 matches')
