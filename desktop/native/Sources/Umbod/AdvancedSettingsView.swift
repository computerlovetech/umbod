import SwiftUI
import UmbodCore

struct AdvancedSettingsView: View {
    @EnvironmentObject var model: AppModel
    @ObservedObject var settings: AdvancedSettingsModel
    @State private var loadError = ""
    var body: some View {
        Panel {
            VStack(alignment: .leading, spacing: 16) {
                Text("Connector tool exposure").font(.headline)
                if let effective = settings.effective, model.online {
                    Text("Running: \(effective.exposureMode.rawValue) · Administrator MCP: \(effective.administratorEnabled ? "enabled" : "disabled")")
                        .font(.callout).foregroundStyle(Brand.muted)
                } else {
                    Text("No verified running settings. Start the connection or retry the restart.").foregroundStyle(Brand.muted)
                }
                Picker("Exposure mode", selection: $settings.draft.exposureMode) {
                    ForEach(ConnectorExposureMode.allCases, id: \.self) { mode in
                        Text(mode.rawValue).tag(mode)
                    }
                }.disabled(settings.saved == nil || settings.working || model.busy || !model.online)
                Text(settings.draft.exposureMode.explanation).font(.callout).foregroundStyle(Brand.muted)
                Text("Exposure changes alter the MCP tool list. Connected clients may need a new session or tool-catalog refresh after restart.")
                    .font(.callout).foregroundStyle(Brand.muted)
                Divider()
                Toggle("Enable administrator MCP tools", isOn: Binding(
                    get: { settings.draft.administratorEnabled },
                    set: { settings.requestAdministrator($0) }
                )).disabled(settings.saved == nil || settings.working || model.busy || !model.online)
                Text("Every MCP client using the Desktop agent token receives this access. Connected agents can read and change connector configuration, activation, policy and grants.")
                    .font(.callout).foregroundStyle(Brand.muted)
                if settings.hasPendingChanges {
                    Label(settings.draft != settings.saved ? "Unsaved changes — restart required" : "Saved changes — not yet verified active", systemImage: "arrow.clockwise")
                        .font(.callout)
                }
                if !loadError.isEmpty { Text(loadError).foregroundStyle(Brand.danger) }
                if !settings.error.isEmpty { Text(settings.error).foregroundStyle(Brand.danger).textSelection(.enabled) }
                if !settings.notice.isEmpty { Text(settings.notice).foregroundStyle(Brand.accent) }
                HStack {
                    Button("Save and restart connection") {
                        Task {
                            model.busy = true
                            defer { model.busy = false }
                            await settings.saveAndRestart(request: { try await model.backend.request($0) }, stop: {
                                try await model.backend.shutdown()
                                model.online = false
                            }, start: {
                                try await model.backend.start(directory: model.dataDirectory, persistent: model.dataDirectory == nil, testCredentials: CommandLine.arguments.contains("--test-credentials"))
                            })
                            model.online = model.backend.isRunning
                            if settings.error.isEmpty { try? await model.refresh() }
                        }
                    }.disabled(model.busy || !settings.canSaveAndRestart(isOnline: model.online))
                    if settings.working { ProgressView().controlSize(.small) }
                    if model.online {
                        Button("Reload settings") { Task { await reload() } }.disabled(model.busy || settings.working)
                    }
                }
            }
        }
        .task { if model.online && !settings.working && !model.busy { await reload() } }
        .alert("Enable administrator MCP tools?", isPresented: Binding(
            get: { settings.confirmAdministrator },
            set: { if !$0 { settings.cancelAdministrator() } }
        )) {
            Button("Cancel", role: .cancel) { settings.cancelAdministrator() }
            Button("Enable administrator tools", role: .destructive) { settings.acceptAdministrator() }
        } message: {
            Text("Administrator MCP lets connected agents read and change Umbod's connector configuration, activation, policy and grants. Every agent using this Desktop connection will receive this access after restart.")
        }
    }
    private func reload() async {
        do {
            try await settings.load(preserveDraft: true) { try await model.backend.request($0) }
            loadError = ""
        } catch { loadError = "Could not read backend settings. Start or restart the connection in General settings, then reload. \(error.localizedDescription)" }
    }
}
