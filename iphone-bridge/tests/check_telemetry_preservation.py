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
# The user requested removal of these two diagnostic lines only. Keep the
# decoder input, timing and OcuSync assist code in the byte-for-byte comparison.
diagnostic = '    static NSUInteger feedBytes=0; static double feedLogged=0; feedBytes+=videoData.length;\n    if(_videoTime-feedLogged>5) { feedLogged=_videoTime; [self note:[NSString stringWithFormat:@"Video feed: %lu bytes so far, previewer status %d",(unsigned long)feedBytes,(int)[DJIVideoPreviewer instance].status.isRunning]]; }\n'
assert diagnostic in baseline
baseline=baseline.replace(diagnostic,'')
assert 'Video feed:' not in current

# Explicitly authorized one-use launch and 1 m floor. Native/SDK-seam tests cover these.
current=re.sub(r'// BEGIN autonomy methods\..*?// END autonomy methods\.\n\n','',current,count=1,flags=re.S)
current=re.sub(r'^.*// autonomy integration\n','',current,flags=re.M)
current=current.replace(',DJIBaseProductDelegate>','>')
current=current.replace('Aircraft must take off before enabling flight (1–30 m above takeoff)','Pilot must use Take off or the RC, then climb to 5–30 m')
current=current.replace('1–30 m relative altitude','5–30 m relative altitude').replace('1..30 m','5..30 m')
current=current.replace('Number(cmd,@"alt",GA_MIN_ALTITUDE_M,GA_MAX_ALTITUDE_M,&c)','Number(cmd,@"alt",5,30,&c)')

# App-switch recovery is explicitly authorized and has native policy tests.
current=re.sub(r'^ *// BEGIN airborne anchor recovery\..*?^ *// END airborne anchor recovery\.\n','',current,count=1,flags=re.S|re.M)
current=current.replace('#import "GroundAnchor.h" // airborne anchor recovery\n','')
current=current.replace('Need strong GPS and a ground anchor or live DJI home point within 40 m','Need strong GPS and a ground anchor recorded before takeoff')

# The agent may REQUEST local takeoff confirmation, with no raw launch/arm API.
current=re.sub(r'// BEGIN agent takeoff request methods\..*?// END agent takeoff request methods\.\n\n','',current,count=1,flags=re.S)
current=re.sub(r'^.*// agent takeoff integration\n','',current,flags=re.M)

# Explicitly authorized local pilot-takeoff additions. The policy has native behavior tests.
current=re.sub(r'// BEGIN pilot takeoff methods\..*?// END pilot takeoff methods\.\n\n','',current,count=1,flags=re.S)
current=re.sub(r'^.*// pilot takeoff integration\n','',current,flags=re.M)
current=current.replace('GATakeoffBusy(_pilotTakeoff)?[self takeoffStatus]:','')
current=current.replace('Pilot must use Take off or the RC, then climb to 5–30 m','Pilot must take off manually first, then climb to 5–30 m')

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
print('Bench flight, command, connection and video code preserved; telemetry and authorized pilot-takeoff additions isolated.')
