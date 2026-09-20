"""Verify the telemetry fix changes observations/reporting, not flight or video.

Accept an optional local baseline path; CI obtains the real bench commit.
"""
from pathlib import Path
import re
import subprocess
import sys

root=Path(__file__).resolve().parents[2]
path='iphone-bridge/ios/GuardianAngel/DroneBridge.m'
baseline=Path(sys.argv[1]).read_text(encoding='utf-8') if len(sys.argv)>1 else subprocess.check_output(
    ['git','show',f'4ebcf22b1c09b9872ff9a4503dfccdfbbacacd99:{path}'],cwd=root).decode()
current=(root/path).read_text(encoding='utf-8')
current=re.sub(r'\n// Read-only presentation snapshot\..*?\n}\n\n','',current,count=1,flags=re.S)
current=current.replace('#import "TelemetryDisplay.h" // display-only observations\n','')
current=current.replace('    GATelemetrySample _displaySample; // display-only observations\n','')
for name in ('SDK observations','readout'):
    current,count=re.subn(r'^ *// BEGIN display-only '+name+r'.*?^ *// END display-only '+name+r'[^\n]*\n','',current,count=1,flags=re.S|re.M)
    assert count==1,name
old_report=re.search(r'    if\(now-_lastReport>1\) \{.*?(?=    if\(now-_lastFrame>=1)',baseline,re.S).group()
new_report=re.search(r'    // BEGIN display-only reporting\..*?    // END display-only reporting\.\n',current,re.S).group()
guard='if(_gps && _homeSet && GAValidPose(_pose) && now-_fcTime<1.5 && now-_batteryTime<5 && _battery>=0)'
assert guard in new_report,'Original full-navigation report guards must remain'
assert '"type":@"aircraft_status"' in new_report,'Partial observations need their own non-navigation message'
current=current.replace(new_report,old_report)
assert current.strip()==baseline.strip(),'Flight, command, connection or video code changed outside read-only observations/reporting'
print('Bench flight, command, connection and video code preserved; telemetry observations/reporting isolated.')
