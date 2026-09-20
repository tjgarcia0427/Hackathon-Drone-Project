#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if ! xcrun --sdk watchos --show-sdk-path >/dev/null 2>&1; then
  echo "Install/select full Xcode and its watchOS platform in Xcode Settings > Components."
  exit 1
fi
if [ ! -f Config/Local.xcconfig ]; then
  cp Config/Local.example.xcconfig Config/Local.xcconfig
fi
echo "Edit Config/Local.xcconfig: set a unique bundle ID and your Apple Development Team."
echo "Choose your paired Watch in Xcode, enable Developer Mode when prompted, then Run."
echo "Watch SE (2nd generation), watchOS 26.5: Xcode must support that device OS."
open GuardianWatch.xcodeproj
