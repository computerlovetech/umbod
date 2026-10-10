import SwiftUI
import AppKit
import UmbodCore

@MainActor final class AppModel: ObservableObject {
    static let shared = AppModel()
    let backend = Backend()
    @Published var activation = ActivationState([:])
    @Published var diagnostics: [String: Any] = [:]
    @Published var dailyCalls: [String: Int] = [:]
    @Published var dailyTrackingStarted: Int?
    @Published var toolUsage: [String: [String: Int]] = [:]
    @Published var clientSetup: [String: Any] = [:]
    var dataDirectory: URL? {
        guard let i = CommandLine.arguments.firstIndex(of: "--data-dir"), CommandLine.arguments.count > i+1 else { return nil }
        return URL(fileURLWithPath: CommandLine.arguments[i+1]).resolvingSymlinksInPath()
    }
    var clientConfig: URL {
        if dataDirectory != nil, let i = CommandLine.arguments.firstIndex(of: "--client-config"), CommandLine.arguments.count > i+1 { return URL(fileURLWithPath: CommandLine.arguments[i+1]).resolvingSymlinksInPath() }
        return ClientConfiguration.destination(home: FileManager.default.homeDirectoryForCurrentUser, dataDirectory: dataDirectory ?? (AppEnvironment.current == .dev ? AppEnvironment.current.dataDirectory : nil))
    }
    @Published var servers: [[String: Any]] = []
    @Published var tools: [[String: Any]] = []
    @Published var allowedTools: Set<String> = []
    @Published var statuses: [String: String] = [:]
    @Published var error = ""
    @Published var notice = ""
    @Published var settingsSection: SettingsSection = .general
    @Published var settingsPresented = false
    @Published var busy = false
    @Published var online = false
    private var starting = false
    func start() async {
        guard !starting && !backend.isRunning else { return }
        starting = true
        defer { starting = false }
        do {
            if CommandLine.arguments.contains("--smoke-report") && dataDirectory == nil { throw ContractError.message("Smoke tests require --data-dir isolation") }
            try await backend.start(directory: dataDirectory, persistent: dataDirectory == nil); online = true; try await refresh()
                if let flag = CommandLine.arguments.firstIndex(of: "--smoke-report"), CommandLine.arguments.count > flag + 1 {
                    let path = CommandLine.arguments[flag + 1]
                    var survived = false, reopened = false
                    if CommandLine.arguments.contains("--smoke-close-reopen"), let window = NSApp.windows.first(where: { $0.title == AppEnvironment.current.name }) {
                        window.performClose(nil)
                        try await Task.sleep(for: .milliseconds(250))
                        _ = try await backend.request(["action":"status"])
                        survived = backend.isRunning && !window.isVisible
                        window.makeKeyAndOrderFront(nil)
                        reopened = window.isVisible
                    }
                    let report: [String: Any] = ["backgroundSurvivedClose":survived,"reopened":reopened].merging( ["backendRunning": backend.isRunning, "backendPID": backend.processID, "bundlePath": Bundle.main.bundlePath, "gateway": backend.gateway,
                        "serverCount": servers.count, "windowCount": NSApp.windows.count,
                        "windows": NSApp.windows.map { ["title": $0.title, "visible": $0.isVisible, "width": $0.frame.width, "height": $0.frame.height] as [String: Any] }]) { _, new in new }
                    try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: URL(fileURLWithPath: path))
                    if CommandLine.arguments.contains("--smoke-exit") { Task { @MainActor in try? await Task.sleep(for: .milliseconds(200)); NSApp.terminate(nil) } }
                } }
        catch { self.error = error.localizedDescription; online = false }
    }
    func refresh() async throws {
        let state = try await backend.request(["action": "status"])
        activation = ActivationState(state)
        diagnostics = state["diagnostics"] as? [String: Any] ?? [:]
        toolUsage = state["tool_usage"] as? [String: [String: Int]] ?? [:]
        dailyCalls = state["daily_calls"] as? [String: Int] ?? [:]
        dailyTrackingStarted = state["daily_tracking_started"] as? Int
        clientSetup = state["client_setup"] as? [String: Any] ?? [:]
        servers = state["servers"] as? [[String: Any]] ?? []
        tools = state["tools"] as? [[String: Any]] ?? []
        allowedTools = Set(state["allowed_tools"] as? [String] ?? [])
        statuses = state["statuses"] as? [String: String] ?? [:]
        online = backend.isRunning
    }
    func act(_ body: [String: Any], success: String = "") {
        Task { busy = true; error = ""; defer { busy = false }
            do { _ = try await backend.request(body); try await refresh(); notice = success }
            catch { self.error = error.localizedDescription }
        }
    }
    func copy(_ text: String, message: String = "Copied to clipboard") {
        NSPasteboard.general.clearContents(); NSPasteboard.general.setString(text, forType: .string); notice = message
    }
    func signIn(_ id: String, clientID: String) {
        Task { busy = true; error = ""; defer { busy = false }
            do { let result = try await backend.request(["action": "oauth_begin", "id": id, "client_id": clientID]); if let value = result["url"] as? String, let url = URL(string: value) { NSWorkspace.shared.open(url) }; try await refresh() }
            catch { self.error = error.localizedDescription }
        }
    }
}
@MainActor final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Refresh the running Dock icon even when macOS cached an older bundle icon.
        if let iconURL = Bundle.main.url(forResource: "UmbodBrand", withExtension: "icns"),
           let icon = NSImage(contentsOf: iconURL) {
            NSApp.applicationIconImage = icon
        }
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }
    func applicationWillTerminate(_ notification: Notification) { AppModel.shared.backend.stop() }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag { sender.windows.first(where: { $0.title == AppEnvironment.current.name })?.makeKeyAndOrderFront(nil) }
        return true
    }
}
@main struct UmbodApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @StateObject private var model = AppModel.shared
    var body: some Scene {
        Window(AppEnvironment.current.name, id: "main") { Workspace().environmentObject(model).frame(minWidth: 950, minHeight: 680).task { Task { await model.start() } } }
            .defaultSize(width: 1120, height: 780)
            .commands {
                CommandGroup(replacing: .newItem) {}
                CommandGroup(replacing: .appSettings) { SettingsMenuButton().environmentObject(model) }
            }
        MenuBarExtra(AppEnvironment.current.name, systemImage: "point.3.connected.trianglepath.dotted") { BackgroundMenu() }
    }
}
enum Page: String, CaseIterable, Identifiable {
    case overview = "Overview", servers = "Connectors"
    var id: String { rawValue }
}
struct Workspace: View {
    @EnvironmentObject var model: AppModel
    @State private var page: Page? = .overview
    @State private var selectedConnector: String?
    var body: some View {
        HStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 8) {
                    UmbodMark().fill(.black).frame(width: 40, height: 40)
                    Text(AppEnvironment.current.name).font(.system(size: 24, weight: .semibold)).tracking(-1.44)
                }.padding(.horizontal, 4)
                Text(AppEnvironment.current == .dev ? "DEVELOPMENT" : "LOCAL WORKSPACE").font(.system(size: 10, design: .monospaced))
                    .tracking(0.8).foregroundStyle(Brand.muted)
                    .padding(.horizontal, 12).padding(.top, 18).padding(.bottom, 12)
                VStack(spacing: 4) {
                    ForEach(Page.allCases) { item in
                        Button { page = item } label: {
                            Label(item.rawValue, systemImage: item == .overview ? "square.grid.2x2" : "point.3.connected.trianglepath.dotted").frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .buttonStyle(NavigationButtonStyle(selected: page == item))
                        .accessibilityAddTraits(page == item ? [.isSelected] : [])
                    }
                }
                Spacer()
                Button {
                    model.settingsSection = .general
                    model.settingsPresented = true
                } label: {
                    Label("Settings", systemImage: "gearshape").frame(maxWidth: .infinity, alignment: .leading)
                }.buttonStyle(NavigationButtonStyle(selected: false)).padding(.bottom, 12)
                VStack(alignment: .leading, spacing: 6) {
                    Rectangle().fill(Brand.border).frame(height: 1).padding(.bottom, 6)
                    Label(model.online ? "Gateway running" : "Gateway offline", systemImage: "circle.fill")
                        .font(.system(size: 12, weight: .semibold)).foregroundStyle(model.online ? Brand.accent : Brand.muted)
                    Text("Private. Local. Yours.").font(.system(size: 12)).foregroundStyle(Brand.muted)
                }.padding(.horizontal, 8)
            }.padding(.horizontal, 16).padding(.top, 26).padding(.bottom, 18)
                .frame(width: 232).background(Brand.soft)
            Rectangle().fill(Brand.border).frame(width: 1)
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    if page != .servers || selectedConnector == nil {
                    HStack(alignment: .top) {
                        VStack(alignment: .leading, spacing: 10) {
                            Text((page ?? .overview).rawValue).font(.system(size: 32, weight: .semibold)).tracking(-1.28)
                            Text(subtitle).font(.system(size: 15)).foregroundStyle(Brand.muted).lineSpacing(5)
                        }
                        Spacer()
                        if model.busy { ProgressView().controlSize(.small) }
                        Button { Task { do { try await model.refresh() } catch { model.error = error.localizedDescription } } } label: {
                            Image(systemName: "arrow.clockwise")
                        }.help("Refresh connection status")
                    }
                    }
                    StatusMessages()
                    switch page ?? .overview { case .overview: Overview(page: $page); case .servers: ServersView(selectedConnector: $selectedConnector) }
                }.padding(.horizontal, 40).padding(.vertical, 48).frame(maxWidth: 1440, alignment: .leading)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }.background(Brand.canvas)
        }
        .disabled(model.settingsPresented)
        .accessibilityHidden(model.settingsPresented)
        .overlay {
            if model.settingsPresented {
                GeometryReader { geometry in
                    ZStack {
                        Color.black.opacity(0.28)
                            .onTapGesture { model.settingsPresented = false }
                            .accessibilityHidden(true)
                        SettingsView()
                            .frame(width: min(1000, geometry.size.width - 96),
                                   height: min(800, geometry.size.height - 96))
                            .clipShape(RoundedRectangle(cornerRadius: 16))
                            .overlay(RoundedRectangle(cornerRadius: 16).stroke(Brand.border))
                            .shadow(color: .black.opacity(0.2), radius: 24, y: 12)
                    }.frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
        }
        .modifier(BrandAppearance())
    }
    var subtitle: String { switch page ?? .overview {
        case .overview: "Your tool activity across connected apps."
        case .servers: "Choose a connector to manage its tools."
    } }
}
struct Panel<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View { VStack(alignment: .leading, spacing: 16) { content }.padding(18).frame(maxWidth: .infinity, alignment: .leading).background(Brand.canvas, in: RoundedRectangle(cornerRadius: 12)).overlay(RoundedRectangle(cornerRadius: 12).stroke(Brand.border)) }
}
struct ServerEditor: View {
    @EnvironmentObject var model: AppModel
    @Environment(\.dismiss) var dismiss
    @State var draft: ServerDraft
    @State private var credentialName = "Authorization"
    @State private var credential = ""
    @State private var localError = ""
    @State private var saving = false
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text(draft.id.isEmpty ? "Add connector" : "Edit connector").font(.title2.bold())
            ScrollView { VStack(alignment: .leading, spacing: 16) {
                TextField("Name", text: $draft.name)
                Picker("Connection", selection: $draft.transport) { Text("Local process · stdio").tag("stdio"); Text("Remote · Streamable HTTP").tag("http") }
                if draft.transport == "stdio" {
                    TextField("Executable (absolute path)", text: $draft.command)
                    Text("Arguments · one per line, no shell quoting").font(.caption).foregroundStyle(Brand.muted)
                    TextEditor(text: $draft.arguments).font(.system(.body, design: .monospaced)).frame(height: 65).padding(8).background(Brand.canvas).overlay(RoundedRectangle(cornerRadius: 8).stroke(Brand.border))
                } else { TextField("Endpoint URL", text: $draft.url) }
                VStack(alignment: .leading, spacing: 12) {
                    Text("Optional credential · stored only in Keychain").font(.system(size: 14, weight: .semibold)).padding(.top, 8)
                    TextField(draft.transport == "stdio" ? "Environment variable name" : "Header name (Authorization, X-API-Key…)", text: $credentialName)
                    SecureField(draft.transport == "stdio" ? "Secret environment value" : "Header value (include Bearer prefix for a bearer token)", text: $credential)
                    Text("Leave blank for no change. Use browser sign-in after saving for OAuth.").font(.caption).foregroundStyle(Brand.muted)
                }
                DisclosureGroup("Advanced credential references") { Text("JSON maps names to upstream: Keychain references. Never put secret values here.").font(.caption); TextField("Headers", text: $draft.headerReferences); TextField("Environment", text: $draft.environmentReferences) }
            }.padding(2) }.textFieldStyle(BrandTextFieldStyle())
            if !draft.id.isEmpty { Text("Saving edits disconnects this connector and resets its shared tool permissions. Reconnect and enable the tools you want.").font(.caption).foregroundStyle(Brand.muted) }
            if !localError.isEmpty { Text(localError).foregroundStyle(Brand.danger) }
            HStack { Spacer(); Button("Cancel") { dismiss() }; Button(saving ? "Saving…" : "Save connector") { save() }.buttonStyle(BrandButtonStyle(primary: true)).disabled(saving || draft.name.isEmpty) }
        }.padding(24).frame(width: 620, height: 660).modifier(BrandAppearance())
    }
    func save() {
        Task { saving = true; defer { saving = false }
            do {
                if draft.id.isEmpty { draft.id = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased() }
                var payload = try draft.payload()
                if !credential.isEmpty {
                    guard !credentialName.isEmpty else { throw ContractError.message("Enter a credential header or environment name") }
                    let reference = "upstream:\(draft.id):\(credentialName)"
                    _ = try await model.backend.request(["action": "secret_set", "reference": reference, "value": credential]); credential = ""
                    let key = draft.transport == "stdio" ? "env" : "headers"
                    var references = payload[key] as? [String: String] ?? [:]; references[credentialName] = reference; payload[key] = references
                }
                _ = try await model.backend.request(["action": "server_save", "server": payload]); try await model.refresh(); dismiss()
            } catch { localError = error.localizedDescription }
        }
    }
}
struct ConnectionView: View {
    @EnvironmentObject var model: AppModel
    @State private var copying = false
    @State private var guide: MCPClientGuide?
    private var configuration: String { (try? ClientConfiguration.bridge(bundlePath: Bundle.main.bundlePath, environment: .current, executable: model.dataDirectory == nil ? AppEnvironment.current.gatewayExecutable : nil)) ?? "" }
    var body: some View {
        if AppEnvironment.current == .dev {
            Text("Development connection. Use this in a dedicated test project or session; keep your everyday agents connected to Umbod.").font(.callout).foregroundStyle(Brand.muted)
        }
        ForEach(MCPClientGuide.allCases) { client in
            Panel {
                HStack(spacing: 16) {
                    Image(systemName: client.symbol).font(.title2).foregroundStyle(Brand.accent).frame(width: 28)
                    VStack(alignment: .leading, spacing: 5) {
                        Text(client.rawValue).font(.headline)
                        Text(client.summary).foregroundStyle(Brand.muted)
                    }
                    Spacer()
                    Button(client == .chatGPT ? "Details" : "Set up \(client.rawValue)") { guide = client }
                }
            }
        }
        .sheet(item: $guide) { client in
            MCPGuideSheet(client: client, configuration: configuration, copy: { copyConfiguration() })
        }
        Text("Other MCP clients").font(.headline).padding(.top, 8)
        Panel {
            Text("1. Copy your connection configuration").font(.headline)
            Text("Use this configuration with any client that supports local MCP connections.").foregroundStyle(Brand.muted)
            Text(configuration).font(.system(size: 12, design: .monospaced)).textSelection(.enabled)
                .padding(16).frame(maxWidth: .infinity, alignment: .leading).background(Brand.soft, in: RoundedRectangle(cornerRadius: 8))
            Button(copying ? "Preparing…" : "Copy configuration") { copyConfiguration() }
                .buttonStyle(BrandButtonStyle(primary: true)).disabled(copying)
            Text("2. Add Umbod in your client's MCP settings").font(.headline)
            Text("Merge the \(AppEnvironment.current.serverName) entry into its mcpServers configuration, keeping any existing entries.").foregroundStyle(Brand.muted)
            Text("3. Start using your tools").font(.headline)
            Text("Enable tools by opening their connector in Umbod. Every MCP client gets the same enabled tools.").foregroundStyle(Brand.muted)
        }
        Panel {
            DisclosureGroup("Advanced: direct HTTP connection") {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Endpoint: http://\(model.backend.gateway)/mcp").textSelection(.enabled)
                    Text("Use Authorization: Bearer <Umbod connection token>. The gateway reuses its saved port across restarts; the bridge reads its runtime record.").font(.callout).foregroundStyle(Brand.muted)
                    Button("Copy connection token") { copyConfiguration(token: true) }.disabled(copying)
                }.padding(.top, 12)
            }
        }
        // Also initialize for users who select and copy the visible JSON themselves.
        .task { do { _ = try await model.backend.request(["action": "connection_setup"]) } catch { if !Task.isCancelled { model.error = error.localizedDescription } } }
    }
    private func copyConfiguration(token: Bool = false) {
        Task {
            copying = true
            defer { copying = false }
            do {
                _ = try await model.backend.request(["action": "connection_setup"])
                if token {
                    let value = try await model.backend.request(["action": "connection_token"])
                    if let credential = value["token"] as? String { model.copy(credential, message: "Connection token copied. Treat the clipboard as sensitive.") }
                } else { model.copy(configuration) }
            } catch { model.error = error.localizedDescription }
        }
    }
}
enum SettingsSection: String, CaseIterable {
    case general = "General", mcp = "MCP"
    var symbol: String { self == .general ? "slider.horizontal.3" : "point.3.connected.trianglepath.dotted" }
    var subtitle: String {
        self == .general ? "Manage your local gateway and application preferences." : "Use your connector tools in your AI client. Choose a setup guide below."
    }
}
struct SettingsMenuButton: View {
    @EnvironmentObject var model: AppModel
    @Environment(\.openWindow) private var openWindow
    var body: some View {
        Button("Settings…") {
            model.settingsSection = .general
            openWindow(id: "main")
            model.settingsPresented = true
        }.keyboardShortcut(",", modifiers: .command)
    }
}
struct StatusMessages: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        if !model.error.isEmpty {
            HStack { Image(systemName: "exclamationmark.triangle"); Text(model.error).textSelection(.enabled); Spacer(); Button("Dismiss") { model.error = "" } }
                .padding(16).background(Brand.dangerSoft, in: RoundedRectangle(cornerRadius: 12)).foregroundStyle(Brand.danger)
        }
        if !model.notice.isEmpty {
            HStack { Image(systemName: "checkmark.circle"); Text(model.notice); Spacer(); Button { model.notice = "" } label: { Image(systemName: "xmark") }.help("Dismiss notification") }
                .padding(16).background(Brand.accentSoft, in: RoundedRectangle(cornerRadius: 12))
        }
    }
}
struct SettingsView: View {
    @EnvironmentObject var model: AppModel
    @FocusState private var closeFocused: Bool
    var body: some View {
        HStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 0) {
                Text("SETTINGS").font(.system(size: 10, design: .monospaced))
                    .tracking(0.8).foregroundStyle(Brand.muted)
                    .padding(.horizontal, 12).padding(.bottom, 24)
                VStack(spacing: 4) {
                    ForEach(SettingsSection.allCases, id: \.self) { section in
                        Button { model.settingsSection = section } label: {
                            Label(section.rawValue, systemImage: section.symbol)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .buttonStyle(NavigationButtonStyle(selected: model.settingsSection == section))
                        .accessibilityAddTraits(model.settingsSection == section ? [.isSelected] : [])
                    }
                }
                Spacer()
                Text("\(AppEnvironment.current.name) · \(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "Development")").font(.system(size: 12)).foregroundStyle(Brand.muted)
                    .padding(.horizontal, 12)
            }.padding(.horizontal, 16).padding(.vertical, 32)
                .frame(width: 212).background(Brand.soft)
            Rectangle().fill(Brand.border).frame(width: 1)
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    HStack {
                        Text(model.settingsSection.rawValue).font(.system(size: 32, weight: .semibold)).tracking(-1.28)
                        Spacer()
                        if model.busy { ProgressView().controlSize(.small) }
                        Button { model.settingsPresented = false } label: {
                            Image(systemName: "xmark")
                        }
                        .help("Close settings (Esc)")
                        .accessibilityLabel("Close settings")
                        .keyboardShortcut(.cancelAction)
                        .focused($closeFocused)
                    }
                    Text(model.settingsSection.subtitle).font(.system(size: 15)).foregroundStyle(Brand.muted)
                    StatusMessages()
                    if model.settingsSection == .mcp { ConnectionView() } else { GeneralSettingsView() }
                }.padding(40).frame(maxWidth: 900, alignment: .leading).frame(maxWidth: .infinity, alignment: .leading)
            }.background(Brand.canvas)
        }.modifier(BrandAppearance())
            .onAppear { closeFocused = true }
    }
}
struct GeneralSettingsView: View {
    @EnvironmentObject var model: AppModel
    @State private var reference = "upstream:"
    @State private var secret = ""
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 24) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Gateway").font(.headline)
                    Text(model.online ? "Running on loopback only" : "Offline").foregroundStyle(Brand.muted)
                    if model.backend.updateAvailable {
                        Text("Backend update ready. Restart gateway to apply.").font(.caption).foregroundStyle(Brand.accent)
                    }
                }
                Spacer()
                Button(model.online ? "Restart gateway" : "Start gateway") {
                    Task {
                        model.busy = true
                        defer { model.busy = false }
                        do { try await model.backend.shutdown(); model.online = false; await model.start() }
                        catch { model.error = error.localizedDescription }
                    }
                }.disabled(model.busy)
                Button("Stop gateway") {
                    Task {
                        model.busy = true
                        defer { model.busy = false }
                        do { try await model.backend.shutdown(); model.online = false }
                        catch { model.error = error.localizedDescription }
                    }
                }.disabled(model.busy || !model.online)
            }.padding(24)
            Divider().overlay(Brand.border).padding(.horizontal, 24)
            HStack(spacing: 24) {
                Text("MCP address").font(.headline)
                Spacer()
                Text(model.backend.gateway).foregroundStyle(Brand.muted).textSelection(.enabled)
            }.padding(24)
            Divider().overlay(Brand.border).padding(.horizontal, 24)
            Text("The gateway stays running when you quit this app. Restart it to load backend changes; active tool calls may be interrupted. Your connections and endpoint are preserved.")
                .font(.caption).foregroundStyle(Brand.muted).padding(24)
        }.background(Brand.soft, in: RoundedRectangle(cornerRadius: 12))
        Panel {
            Text("Local setup diagnostics").font(.headline)
            Toggle("Keep local funnel counts and timing", isOn: Binding(get: { model.diagnostics["enabled"] as? Bool ?? false }, set: { model.act(["action":"diagnostics_set", "enabled":$0]) }))
            Text("Off by default. Turning off erases recorded counts and timing. No tokens, prompts, arguments or results; nothing is sent to analytics services.").font(.caption).foregroundStyle(.secondary)
            if model.diagnostics["enabled"] as? Bool == true {
                Text((try? JSONText.encode(model.diagnostics)) ?? "{}").font(.system(.caption, design: .monospaced)).textSelection(.enabled)
            }
        }
        Panel { Text("Credential vault").font(.headline); Text("Store a credential for a custom header or environment variable. Reference names are public identifiers; values stay in macOS Keychain.").foregroundStyle(Brand.muted); TextField("Reference, e.g. upstream:weather-key", text: $reference).textFieldStyle(BrandTextFieldStyle()); SecureField("Credential value", text: $secret).textFieldStyle(BrandTextFieldStyle()); HStack { Button("Store in Keychain") { model.act(["action": "secret_set", "reference": reference, "value": secret], success: "Credential stored in Keychain"); secret = "" }.disabled(secret.isEmpty || reference == "upstream:"); Button("Delete credential", role: .destructive) { model.act(["action": "secret_delete", "reference": reference], success: "Credential deleted") }.disabled(reference == "upstream:") } }
        Panel { Text("\(AppEnvironment.current.name) · \(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "Development")").font(.headline); Text("Native SwiftUI interface · Rust MCP gateway\nLocal connectors and shared tool permissions.").foregroundStyle(Brand.muted); Text("This build is ad-hoc signed and not notarized. Real OAuth providers have not been certified. Legacy SSE-only connectors are unsupported.").font(.caption).foregroundStyle(Brand.muted); Button("Open project") { NSWorkspace.shared.open(URL(string: "https://github.com/computerlovetech/umbod")!) } }
    }
}
