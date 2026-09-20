import SwiftUI

@main
struct GuardianWatchApp: App {
    @StateObject private var model = WatchModel()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            ContentView().environmentObject(model)
                .onAppear { model.setActive(scenePhase == .active) }
                .onChange(of: scenePhase) { model.setActive($0 == .active) }
        }
    }
}
