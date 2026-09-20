#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
out="${RUNNER_TEMP:-/tmp}/guardian-ui-smoke"
mkdir -p "$out/GuardianUISmoke.app" "$out/screenshots"
app="$out/GuardianUISmoke.app"
sdk="$(xcrun --sdk iphonesimulator --show-sdk-path)"
arch="$(uname -m)"
xcrun --sdk iphonesimulator clang -fobjc-arc -fmodules -isysroot "$sdk" \
  -target "$arch-apple-ios15.0-simulator" -Iios/GuardianAngel \
  -framework UIKit -framework Foundation -framework QuartzCore \
  ios/GuardianAngel/AppDelegate.m ios/GuardianAngel/Navigation.c \
  tests/ui/MockBridge.m tests/ui/UIHarness.m -o "$app/GuardianUISmoke"
python3 - "$app/Info.plist" <<'PY'
import plistlib,sys
with open(sys.argv[1],'wb') as f:
    plistlib.dump({'CFBundleIdentifier':'com.guardianangel.ui-smoke','CFBundleName':'Guardian UI smoke',
        'CFBundleExecutable':'GuardianUISmoke','CFBundlePackageType':'APPL','CFBundleVersion':'1',
        'CFBundleShortVersionString':'1.0','MinimumOSVersion':'15.0','UIDeviceFamily':[1],
        'CFBundleSupportedPlatforms':['iPhoneSimulator'],'UILaunchScreen':{},
        'UISupportedInterfaceOrientations':['UIInterfaceOrientationPortrait']},f)
PY
codesign --force --sign - "$app"
device="$(xcrun simctl list devices available -j | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next(x["udid"] for xs in d["devices"].values() for x in xs if "iPhone" in x["name"]))')"
xcrun simctl boot "$device" || true
xcrun simctl bootstatus "$device" -b
xcrun simctl install "$device" "$app"
for scenario in takeoff-ready takeoff-confirm takeoff-pending flow not-started offline camera procedure flight pending release-failed returning low-battery stale gps-waiting modal log; do
  xcrun simctl terminate "$device" com.guardianangel.ui-smoke >/dev/null 2>&1 || true
  data="$(xcrun simctl get_app_container "$device" com.guardianangel.ui-smoke data)"
  rm -f "$data/Documents/ui-result.json"
  SIMCTL_CHILD_GA_UI_SCENARIO="$scenario" xcrun simctl launch "$device" com.guardianangel.ui-smoke
  for attempt in {1..30}; do
    test -f "$data/Documents/ui-result.json" && break
    sleep 1
  done
  python3 - "$data/Documents/ui-result.json" "$scenario" <<'PY'
import json,sys
with open(sys.argv[1]) as f: r=json.load(f)
print(sys.argv[2]+': '+r['message'])
assert r['ok'], r
PY
  xcrun simctl io "$device" screenshot "$out/screenshots/$scenario.png"
done
xcrun simctl spawn "$device" log show --last 10m --style compact --predicate 'process == "GuardianUISmoke"' > "$out/simulator.log" 2>&1 || true
printf 'UI screenshots: %s\n' "$out/screenshots"
