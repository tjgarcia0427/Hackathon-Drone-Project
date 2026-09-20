import SwiftUI

struct ContentView: View {
    @EnvironmentObject var model: WatchModel
    @State private var confirmLive = false
    @State private var confirmDiscard = false
    @State private var confirmRetryLive = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 12) {
                    Text(model.testMode ? "TEST MODE" : "LIVE HELP ALERTS")
                        .font(.caption.bold()).foregroundColor(model.testMode ? .cyan : .orange)
                    if let count = model.countdown { Text("\(count)").font(.largeTitle.bold()) }
                    Button(model.testMode ? "Send Test Help" : "Send Help") { model.trigger(source: "watch_button") }
                        .tint(model.testMode ? .blue : .red)
                        .disabled(model.busy || model.pending != nil)
                    if model.busy && !model.sending {
                        Button("Cancel before sending", role: .cancel) { model.cancelBeforeSending() }.tint(.orange)
                    }
                    Text(model.status).font(.footnote).frame(maxWidth: .infinity, alignment: .leading)
                        .accessibilityIdentifier("delivery-status")
                    if let pending = model.pending {
                        Text(pending.alert.test_mode ? "Pending TEST alert" : "Pending LIVE alert — retry may create a mission.")
                            .font(.caption.bold()).foregroundColor(pending.alert.test_mode ? .cyan : .orange)
                        Button("Retry delivery") {
                            if pending.alert.test_mode { model.retry() } else { confirmRetryLive = true }
                        }.disabled(model.busy)
                        Button("Discard local retry", role: .destructive) { confirmDiscard = true }.disabled(model.busy)
                    }
                    if model.lastReceipt != nil {
                        Button("Refresh alert status") { model.refreshReceipt() }.disabled(model.busy)
                    }
                    Toggle("Shake to alert", isOn: $model.shakeEnabled).disabled(model.busy || model.pending != nil)
                    Text("Three deliberate shakes in 2 seconds. Keep this app visible. Shake turns off when you leave it.")
                        .font(.caption2).foregroundColor(.secondary)
                    Toggle("Test mode", isOn: Binding(get: { model.testMode }, set: { value in
                        if value { model.testMode = true } else { confirmLive = true }
                    })).disabled(model.busy || model.pending != nil)
                    NavigationLink("Server settings") {
                        Form {
                            TextField("Server URL", text: $model.serverURL)
                                .textInputAutocapitalization(.never).autocorrectionDisabled()
                                .disabled(model.busy || model.pending != nil)
                            Button("Test connection") { model.checkConnection() }.disabled(model.busy)
                            Button("Enable location") { model.enableLocation() }.disabled(model.busy)
                            Text(model.status).font(.footnote)
                            Text("Use the Mac's Wi-Fi IP and port 8000. The Watch needs a network route to it.")
                                .font(.caption2)
                        }.navigationTitle("Server").onAppear { model.shakeEnabled = false }
                    }
                    Text("Demo help gesture. No automatic fall detection or emergency-services call.")
                        .font(.caption2).foregroundColor(.secondary)
                }.padding(.horizontal, 4)
            }.navigationTitle("Guardian Angel")
        }
        .confirmationDialog("Enable live alerts?", isPresented: $confirmLive, titleVisibility: .visible) {
            Button("Enable live alerts", role: .destructive) { model.testMode = false }
        } message: {
            Text("Valid GPS can create a drone plan. Server auto-dispatch may launch the mission if enabled. Use a supervised demo area.")
        }
        .confirmationDialog("Discard retry?", isPresented: $confirmDiscard, titleVisibility: .visible) {
            Button("Discard local retry", role: .destructive) { model.discard() }
        } message: { Text("This cannot cancel an alert already received. Check the dashboard before sending another.") }
        .confirmationDialog("Retry the pending LIVE alert?", isPresented: $confirmRetryLive, titleVisibility: .visible) {
            Button("Retry LIVE alert", role: .destructive) { model.retry() }
        } message: { Text("The original alert keeps its live setting even if Test mode is now on. A retry can create a mission if the server has not received it yet.") }
    }
}
