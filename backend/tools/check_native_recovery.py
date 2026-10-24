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
run('shell','am','force-stop','com.kyp.ingredients')
run('shell','am','start','-W','-a','android.intent.action.VIEW','-d','exp+kyp://expo-development-client/?url=http%3A%2F%2F10.0.2.2%3A8081','com.kyp.ingredients');time.sleep(2)
editor=None
for _ in range(7):
 editor=next((n for n in nodes() if n.get('class')=='android.widget.EditText' and bounds(n)[3]>bounds(n)[1]+80),None)
 if editor is not None:break
 run('shell','input','swipe','550','2050','550','850','300')
assert editor is not None;tap(editor)
run('shell','input','text',r'Salt\),%sSugar');run('shell','input','keyevent','4')
tap(seek('Review ingredient text'));time.sleep(1)
tap(seek('Review comma-separated entries'));tap(seek('REVIEW ENTRIES'));time.sleep(1)
button=seek('Confirm and look up');assert button.get('enabled')=='false'
for _ in range(4):run('shell','input','swipe','550','850','550','2050','300')
tap(seek('Confirm SODIUM CHLORIDE'));tap(seek('Confirm SUCROSE'))
button=seek('Confirm and look up');assert button.get('enabled')=='true';tap(button);time.sleep(1)
assert any('2 of 2' in (n.get('text') or n.get('content-desc')) for n in nodes())
(Path(__file__).resolve().parents[2]/'docs/screenshots/native-ocr-recovery.png').write_bytes(run('exec-out','screencap','-p'))
print('PASS: native broken-bracket error -> explicit recovery -> individual confirmation -> lookup')
