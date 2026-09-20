# Guardian Angel Watch app

Start with **[the complete Watch setup and first-test guide](../docs/WATCH_SETUP.md)**. Target device: Apple Watch SE (2nd generation), watchOS 26.5; source supports watchOS 9+.

On Mac: `bash setup-mac.sh`, edit ignored `Config/Local.xcconfig`, select your physical Watch in Xcode and Run. No App Store upload or DJI dependencies are needed for this app. It has a Send Help button and a foreground-only deliberate shake gesture, a cancel countdown, location capture, receipt/retry handling and default-on Test mode.

Keep Test mode on for the first dashboard test. It never creates a drone mission. The iPhone controller bridge remains a separate app.

The Watch app compiles and links in Xcode CI and its Swift core tests pass. See [validation and remaining device checks](VALIDATION.md).
