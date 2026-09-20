#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if ! xcodebuild -version >/dev/null 2>&1 || ! xcrun --sdk iphoneos --show-sdk-path >/dev/null 2>&1; then
  echo "Install and open full Xcode, then select its command-line tools in Xcode Settings > Locations."; exit 1
fi
if ! command -v bundle >/dev/null 2>&1; then
  echo "Install Ruby and Bundler (gem install bundler), then run this script again."; exit 1
fi
if [ ! -f Config/Secrets.xcconfig ]; then
  cp Config/Secrets.example.xcconfig Config/Secrets.xcconfig
fi
bundle config set --local path vendor/bundle
bundle install
bundle exec pod install
echo "Set bundle ID and DJI app key in Config/Secrets.xcconfig. Select your Apple team in Xcode."
open GuardianAngel.xcworkspace
