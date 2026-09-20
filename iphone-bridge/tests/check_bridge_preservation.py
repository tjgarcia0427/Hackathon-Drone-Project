"""Check the hardware-tested bridge remains identical except read-only UI state.

The optional argument is a local copy of the reference source. CI reads the
actual bench-tested Git commit, avoiding a second copy of flight code in tests.
"""
from pathlib import Path
import re
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
path = "iphone-bridge/ios/GuardianAngel/DroneBridge.m"
baseline = Path(sys.argv[1]).read_text(encoding="utf-8") if len(sys.argv)>1 else subprocess.check_output(
    ["git", "show", f"4ebcf22b1c09b9872ff9a4503dfccdfbbacacd99:{path}"], cwd=root).decode()
current = (root/path).read_text(encoding="utf-8")
current, count = re.subn(r"\n// Read-only presentation snapshot\..*?\n}\n\n", "", current, count=1, flags=re.S)
assert count == 1, "Read-only telemetry method not found"
current = current.replace("        if(self.stateUpdated) self.stateUpdated([self telemetry]);\n", "")
assert current.strip() == baseline.strip(), "Hardware-tested flight/video logic changed outside the UI snapshot"
assert "void (^updated)(NSString *status)" in (root/"iphone-bridge/ios/GuardianAngel/DroneBridge.h").read_text()
print("Bench-tested flight, command, video and original status callback preserved.")
