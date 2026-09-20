import Foundation

/// Deliberate help gesture, not a fall classifier. Acceleration excludes gravity.
struct ShakeDetector {
    private var peaks: [TimeInterval] = []
    private var armed = true
    private var lastPeak = -Double.infinity
    private var lastTrigger = -Double.infinity

    mutating func reset() {
        peaks.removeAll()
        armed = true
        lastPeak = -Double.infinity
    }

    // Only the alert flow may release this cooldown after cancellation before
    // any POST. Ordinary motion restarts still preserve the cooldown.
    mutating func cancelBeforeSending() {
        lastTrigger = -Double.infinity
        reset()
    }

    mutating func sample(magnitude: Double, time: TimeInterval) -> Bool {
        guard magnitude.isFinite, time.isFinite else { return false }
        if magnitude < 0.45 { armed = true }
        peaks.removeAll { time - $0 > 2.0 }
        guard time - lastTrigger >= 30, armed, magnitude >= 1.5,
              time - lastPeak >= 0.25 else { return false }
        armed = false
        lastPeak = time
        peaks.append(time)
        guard peaks.count >= 3 else { return false }
        lastTrigger = time
        reset()
        return true
    }
}

struct HelpCooldown {
    private var lastTrigger = Date.distantPast
    func ready(now: Date = Date()) -> Bool { now.timeIntervalSince(lastTrigger) >= 30 }
    mutating func begin(now: Date = Date()) -> Bool {
        guard ready(now: now) else { return false }
        lastTrigger = now
        return true
    }
    mutating func cancelBeforeSending() { lastTrigger = .distantPast }
}

enum LocationPolicy {
    static func usable(latitude: Double, longitude: Double, accuracy: Double,
                       timestamp: Date, now: Date = Date()) -> Bool {
        let age = now.timeIntervalSince(timestamp)
        return latitude.isFinite && longitude.isFinite && accuracy.isFinite
            && latitude > -85 && latitude < 85 && longitude >= -180 && longitude <= 180
            && accuracy >= 0 && accuracy <= 20 && age >= -5 && age <= 15
    }
}
