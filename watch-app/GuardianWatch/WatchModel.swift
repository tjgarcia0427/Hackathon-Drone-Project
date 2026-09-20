import SwiftUI
import CoreLocation
import CoreMotion
import WatchKit

@MainActor
final class WatchModel: NSObject, ObservableObject, CLLocationManagerDelegate {
    @Published var serverURL: String {
        didSet { UserDefaults.standard.set(serverURL, forKey: "serverURL") }
    }
    @Published var testMode = true // Each launch starts with flight disabled by test mode.
    @Published var shakeEnabled = false { didSet { updateMotion() } }
    @Published var status = "Test mode: alerts only. Keep this app open for shake detection."
    @Published var busy = false
    @Published var countdown: Int? = nil
    @Published private(set) var pending: PendingAlert?
    @Published private(set) var lastReceipt: AlertReceipt?
    @Published private(set) var sending = false
    private var lastReceiptBase: URL?
    private var active = false
    private var lastTrigger = Date.distantPast
    private var flowTask: Task<Void, Never>?
    private let motion = CMMotionManager()
    private var detector = ShakeDetector()
    private let location = CLLocationManager()
    private var locationWaiter: CheckedContinuation<CLLocation?, Never>?
    private var locationTimer: Task<Void, Never>?

    override init() {
        serverURL = UserDefaults.standard.string(forKey: "serverURL") ?? "http://192.168.1.50:8000"
        if let data = UserDefaults.standard.data(forKey: "pendingAlert") {
            pending = try? JSONDecoder().decode(PendingAlert.self, from: data)
        }
        super.init()
        location.delegate = self
        location.desiredAccuracy = kCLLocationAccuracyBest
        if pending != nil { status = "An earlier delivery is unconfirmed. Retry its same ID or discard it." }
    }

    func setActive(_ value: Bool) {
        active = value
        if !value {
            shakeEnabled = false
            if busy && !sending { flowTask?.cancel(); finishLocation(nil) }
        }
        updateMotion()
    }

    func checkConnection() {
        guard !busy else { return }
        busy = true
        flowTask = Task {
            defer { busy = false }
            do {
                let base = try ServerAddress.parse(serverURL)
                let info: ServerStatus = try await WatchHTTP.request(base, path: "watch/status")
                try Task.checkCancellation()
                guard info.protocol == 1 else { throw WatchError(message: "Unsupported server version") }
                status = "Connected. Server auto-dispatch is \(info.auto_dispatch ? "ON" : "OFF")."
                WKInterfaceDevice.current().play(.success)
            } catch is CancellationError { status = "Connection check cancelled." }
            catch { status = "Connection failed: \(error.localizedDescription)" }
        }
    }

    func enableLocation() {
        guard !busy else { return }
        location.requestWhenInUseAuthorization()
        status = "Allow location access. If previously denied, enable it in Watch Settings > Privacy & Security > Location Services."
    }

    func trigger(source: String) {
        guard active, !busy, pending == nil else { return }
        guard Date().timeIntervalSince(lastTrigger) >= 30 else {
            status = "30-second help cooldown. Wait before sending again."
            return
        }
        lastTrigger = Date()
        let started = Date(), useTestMode = testMode, address = serverURL
        busy = true
        lastReceipt = nil
        flowTask = Task {
            defer { busy = false; sending = false; countdown = nil }
            do {
                let base = try ServerAddress.parse(address)
                WKInterfaceDevice.current().play(.notification)
                for remaining in stride(from: 5, through: 1, by: -1) {
                    countdown = remaining
                    status = "\(useTestMode ? "Test" : "Help") alert in \(remaining)s"
                    try await Task.sleep(nanoseconds: 1_000_000_000)
                }
                countdown = nil
                status = "Connecting… You can still cancel."
                let info: ServerStatus = try await WatchHTTP.request(base, path: "watch/status")
                guard info.protocol == 1 else { throw WatchError(message: "Unsupported server version") }
                try Task.checkCancellation()
                status = "Getting location… You can still cancel."
                let fix = await currentLocation()
                try Task.checkCancellation()
                let stamp = ISO8601DateFormatter()
                stamp.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
                let alert = HelpAlert(event_id: UUID().uuidString.lowercased(),
                    server_session: info.server_session, source: source,
                    timestamp: stamp.string(from: started), test_mode: useTestMode,
                    latitude: fix?.coordinate.latitude, longitude: fix?.coordinate.longitude,
                    accuracy: fix?.horizontalAccuracy,
                    location_timestamp: fix.map { stamp.string(from: $0.timestamp) })
                let item = PendingAlert(baseURL: base.absoluteString, alert: alert)
                // Persist before the first POST. A timeout is NOT proof that delivery failed.
                try savePending(item)
                sending = true
                status = "Sending… Receipt not yet confirmed."
                try await deliver(item)
            } catch is CancellationError { status = "Cancelled before sending. No alert sent." }
            catch {
                status = pending == nil ? "No alert sent: \(error.localizedDescription)"
                    : "Delivery unconfirmed: \(error.localizedDescription). Retry uses the same alert."
                WKInterfaceDevice.current().play(.failure)
            }
        }
    }

    func cancelBeforeSending() {
        guard busy && !sending else { return }
        flowTask?.cancel()
        finishLocation(nil)
    }

    func retry() {
        guard !busy, let item = pending else { return }
        busy = true
        sending = true // Retried alert may already be at the server; cancellation cannot undo it.
        flowTask = Task {
            defer { busy = false; sending = false }
            do {
                let info: ServerStatus = try await WatchHTTP.request(try ServerAddress.parse(item.baseURL), path: "watch/status")
                guard info.server_session == item.alert.server_session else {
                    throw WatchError(message: "Server changed/restarted. Discard and send a fresh alert.")
                }
                try await deliver(item)
            } catch { status = "Delivery unconfirmed: \(error.localizedDescription)" }
        }
    }

    func discard() {
        guard !busy else { return }
        pending = nil
        UserDefaults.standard.removeObject(forKey: "pendingAlert")
        status = "Local retry discarded. This does not cancel an alert already received. Check the dashboard."
    }

    func refreshReceipt() {
        guard !busy, let receipt = lastReceipt, let base = lastReceiptBase else { return }
        busy = true
        flowTask = Task {
            defer { busy = false }
            do {
                let updated: AlertReceipt = try await WatchHTTP.request(base, path: "watch/alerts/\(receipt.event_id)")
                lastReceipt = updated
                status = "\(updated.status): \(updated.message)"
            } catch { status = "Status unavailable: \(error.localizedDescription)" }
        }
    }

    private func savePending(_ item: PendingAlert) throws {
        UserDefaults.standard.set(try JSONEncoder().encode(item), forKey: "pendingAlert")
        pending = item
    }

    private func deliver(_ item: PendingAlert) async throws {
        let base = try ServerAddress.parse(item.baseURL)
        let receipt: AlertReceipt = try await WatchHTTP.request(base, path: "watch/alerts", body: JSONEncoder().encode(item.alert))
        guard receipt.event_id == item.alert.event_id else { throw WatchError(message: "Receipt ID did not match") }
        lastReceipt = receipt
        lastReceiptBase = base
        pending = nil
        UserDefaults.standard.removeObject(forKey: "pendingAlert")
        status = "Received — \(receipt.message)"
        WKInterfaceDevice.current().play(.success)
    }

    private func updateMotion() {
        motion.stopDeviceMotionUpdates()
        detector.reset()
        guard active && shakeEnabled else { return }
        guard motion.isDeviceMotionAvailable else { status = "Motion unavailable on this device. Use Send Help."; return }
        motion.deviceMotionUpdateInterval = 1.0 / 25.0
        motion.startDeviceMotionUpdates(to: .main) { [weak self] data, error in
            guard let data = data else {
                if error != nil { Task { @MainActor [weak self] in self?.status = "Motion unavailable. Use Send Help." } }
                return
            }
            let a = data.userAcceleration
            let magnitude = sqrt(a.x * a.x + a.y * a.y + a.z * a.z)
            let time = data.timestamp
            Task { @MainActor [weak self] in
                guard let self = self, self.active, self.shakeEnabled, !self.busy, self.pending == nil else { return }
                if self.detector.sample(magnitude: magnitude, time: time) { self.trigger(source: "watch_shake") }
            }
        }
    }

    private func currentLocation() async -> CLLocation? {
        if Task.isCancelled { return nil }
        return await withCheckedContinuation { continuation in
            locationWaiter = continuation
            locationTimer = Task {
                do { try await Task.sleep(nanoseconds: 12_000_000_000) }
                catch { return }
                finishLocation(nil)
            }
            requestAuthorizedLocation()
        }
    }

    private func requestAuthorizedLocation() {
        guard locationWaiter != nil else { return }
        switch location.authorizationStatus {
        case .notDetermined: location.requestWhenInUseAuthorization()
        case .authorizedWhenInUse, .authorizedAlways: location.requestLocation()
        default: finishLocation(nil)
        }
    }

    private func finishLocation(_ fix: CLLocation?) {
        locationTimer?.cancel()
        locationTimer = nil
        location.stopUpdatingLocation()
        let waiter = locationWaiter
        locationWaiter = nil
        waiter?.resume(returning: fix)
    }

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        Task { @MainActor [weak self] in self?.requestAuthorizedLocation() }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        Task { @MainActor [weak self] in
            let fix = locations.reversed().first { LocationPolicy.usable(latitude: $0.coordinate.latitude,
                longitude: $0.coordinate.longitude, accuracy: $0.horizontalAccuracy, timestamp: $0.timestamp) }
            self?.finishLocation(fix)
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        Task { @MainActor [weak self] in self?.finishLocation(nil) }
    }
}
