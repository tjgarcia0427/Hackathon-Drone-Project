import Foundation

func require(_ condition: @autoclosure () -> Bool, _ label: String) {
    guard condition() else { fatalError(label) }
}

var detector = ShakeDetector()
for i in 0..<100 { require(!detector.sample(magnitude: 0.3, time: Double(i) / 25), "Walking noise triggered") }
for i in 0..<50 { require(!detector.sample(magnitude: 2, time: 5 + Double(i) / 25), "Sustained acceleration triggered") }
detector.reset()
func peak(_ time: Double) -> Bool {
    _ = detector.sample(magnitude: 0, time: time - 0.05)
    return detector.sample(magnitude: 2, time: time)
}
require(!peak(10), "One shake triggered")
require(!peak(10.4), "Two shakes triggered")
require(peak(10.8), "Three deliberate shakes did not trigger")
require(!peak(11.2) && !peak(11.6) && !peak(12), "Cooldown failed")
detector.reset()
require(!peak(14) && !peak(14.4) && !peak(14.8), "Reset bypassed cooldown")
require(!peak(41) && !peak(41.4) && peak(41.8), "Cooldown did not expire")
var spaced = ShakeDetector()
for t in [100.0, 103.0, 106.0] {
    _ = spaced.sample(magnitude: 0, time: t - 0.05)
    require(!spaced.sample(magnitude: 2, time: t), "Widely separated movements triggered")
}
require(!spaced.sample(magnitude: .nan, time: 107), "NaN triggered")
let now = Date()
require(LocationPolicy.usable(latitude: 25, longitude: -80, accuracy: 10, timestamp: now), "Good GPS rejected")
require(!LocationPolicy.usable(latitude: 25, longitude: -80, accuracy: 21, timestamp: now), "Poor GPS accepted")
require(!LocationPolicy.usable(latitude: 25, longitude: -80, accuracy: -1, timestamp: now), "Invalid GPS accepted")
require(!LocationPolicy.usable(latitude: 25, longitude: -80, accuracy: 10, timestamp: now.addingTimeInterval(-16)), "Stale GPS accepted")
require(!LocationPolicy.usable(latitude: 25, longitude: -80, accuracy: 10, timestamp: now.addingTimeInterval(10)), "Future GPS accepted")
for text in ["http://192.168.1.4:8000", "http://10.0.0.4:8000", "http://172.16.4.3:8000", "http://demo.local:8000", "https://demo.example"] {
    require((try? ServerAddress.parse(text)) != nil, "Valid URL rejected: \(text)")
}
for text in ["http://localhost:8000", "http://127.0.0.1:8000", "file:///tmp/a", "http://8.8.8.8:8000", "http://user:pass@192.168.1.4:8000", "http://192.168.1.4/path", "http://192.168.1.4?x=1"] {
    require((try? ServerAddress.parse(text)) == nil, "Unsafe/malformed URL accepted: \(text)")
}
let payload = HelpAlert(event_id: "one", server_session: "session", source: "watch_button", timestamp: "date", test_mode: true,
                        latitude: nil, longitude: nil, accuracy: nil, location_timestamp: nil)
let encoded = try JSONEncoder().encode(PendingAlert(baseURL: "http://10.0.0.1:8000", alert: payload))
let restored = try JSONDecoder().decode(PendingAlert.self, from: encoded)
require(restored.alert.event_id == payload.event_id && restored.alert.test_mode, "Pending retry identity lost")
print("Watch core tests passed: gesture, cooldown, location, server URL and retry serialization")
