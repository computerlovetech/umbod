import SwiftUI
import AppKit
import UmbodCore

struct BackgroundMenu: View {
    @Environment(\.openWindow) private var openWindow
    var body: some View {
        Button("Open \(AppEnvironment.current.name)") { openWindow(id: "main"); NSApp.activate(ignoringOtherApps: true) }
        Text("Quitting the app keeps connections running")
        Divider()
        Button("Quit \(AppEnvironment.current.name)") { NSApp.terminate(nil) }.keyboardShortcut("q")
    }
}
struct ActivationView: View {
    @EnvironmentObject var model: AppModel
    @State private var token = ""
    @State private var diagnostics = false
    @State private var selected = Set(ActivationState.tools)
    @State private var preview: [String: Any] = [:]
    @State private var showPreview = false
    @State private var restore = false
    @State private var repository = ""
    private var a: ActivationState { model.activation }
    private var installed: Bool {
        [URL(fileURLWithPath: "/Applications/Claude.app"),FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Applications/Claude.app")].contains { FileManager.default.fileExists(atPath: $0.path) }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Panel {
                Text("Connect your apps to your AI. Once.").font(.largeTitle.bold())
                Text("Find open GitHub issues in Claude Desktop. Your account stays in Keychain; you choose the tools Claude can use.").foregroundStyle(.secondary)
                HStack { Label("Claude Desktop", systemImage: "laptopcomputer"); Image(systemName: "arrow.right"); Label("GitHub issues", systemImage: "tray.full"); Spacer(); Text(installed ? "Claude detected" : "Claude not detected in Applications").font(.caption).foregroundStyle(.secondary) }
                Text("First-class setup · PAT authentication · provider and client validation pending").font(.caption).foregroundStyle(.secondary)
                if model.dataDirectory != nil { Label("Isolated validation data", systemImage: "testtube.2").foregroundStyle(.orange) }
            }
            if a.stage == .choose { choose }
            else {
                HStack(spacing: 14) {
                    progress("Account", a.connected)
                    progress("Permissions", a.approved)
                    progress("Client setup", a.configured)
                    progress("First result", a.activated)
                }.font(.callout)
                switch a.stage {
                case .choose: EmptyView()
                case .connect: connect
                case .approve: permissions
                case .configure: configure
                case .tryPrompt: firstPrompt
                case .activated:
                    Panel {
                        Label(a.fixture ? "Fixture call verified" : "First downstream result received", systemImage: "checkmark.circle.fill").font(.title2).foregroundStyle(.teal)
                        Text(a.fixture ? "This is a local test result, not evidence of Claude or GitHub provider validation." : "A successful issue-reading call used this client's registered identity. Umbod records no prompts or result bodies. The identity does not independently attest which client product sent it.").foregroundStyle(.secondary)
                        Text(a.connected ? "GitHub connection is ready." : "Connection needs attention. Open Servers to reconnect.").font(.callout)
                    }
                    firstPrompt
                }
                if a.stage != .connect {
                    DisclosureGroup("Account and reconnect") { connect }
                }
                if !model.clientSetup.isEmpty {
                    Panel {
                        Text("Client configuration backup").font(.headline)
                        Text(model.clientSetup["backup"] as? String ?? "").font(.caption).textSelection(.enabled)
                        Button("Undo Umbod's client configuration…", role: .destructive) { restore = true }
                        Text("Restores the exact prior file only if it has not changed since setup. Later edits are protected. Restart Claude after restoring.").font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            Label("Your gateway stays running when you quit Umbod. Stop it explicitly in Settings.", systemImage: "menubar.rectangle").font(.caption).foregroundStyle(.secondary)
        }
        .disabled(model.busy || !model.online)
        .task {
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(3))
                if !model.busy && model.online { try? await model.refresh() }
            }
        }
        .sheet(isPresented: $showPreview) { previewSheet }
        .confirmationDialog("Restore the client configuration backup?", isPresented: $restore) {
            Button("Restore backup", role: .destructive) { model.act(["action":"client_undo","consent":true], success:"Client configuration restored. Restart Claude Desktop.") }
        } message: { Text("This restores only the file shown in setup, after checking it has not changed. The backup is retained.") }
    }
    var choose: some View {
        Panel {
            Text("1 · Choose your first outcome").font(.title2.bold())
            Text("Claude Desktop → Read GitHub issues").font(.headline)
            Text("Use a GitHub fine-grained personal access token limited to your chosen repositories, with Issues: read-only and the required metadata access. Organization approval or SSO policy may apply. No packages will be installed.").foregroundStyle(.secondary)
            HStack {
                Link("Get Claude Desktop", destination: URL(string:"https://claude.ai/download")!)
                Link("GitHub token guidance", destination: URL(string:"https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens")!)
            }
            Toggle("Keep setup counts and timing locally (optional)", isOn: $diagnostics)
            Text("No external analytics. No tokens, prompts, tool arguments or responses. You can erase diagnostics in Settings.").font(.caption).foregroundStyle(.secondary)
            Button("Set up GitHub issues") { model.act(["action":"activation_start","diagnostics":diagnostics]) }.buttonStyle(.borderedProminent).accessibilityIdentifier("activation.start")
            Text("Existing servers and clients remain available in the sidebar.").font(.caption).foregroundStyle(.secondary)
        }
    }
    var connect: some View {
        Panel {
            Text("2 · Connect your GitHub account").font(.title2.bold())
            Text("Paste a limited PAT. Umbod sends it only to GitHub's hosted read-only issues endpoint; Claude receives a separate local identity.").foregroundStyle(.secondary)
            SecureField("GitHub personal access token", text: $token).textFieldStyle(.roundedBorder).accessibilityIdentifier("activation.token")
            HStack {
                Button("Save token & connect") { saveToken() }.buttonStyle(.borderedProminent).disabled(token.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty)
                Button("Reconnect with saved token") { model.act(["action":"connect","id":a.server]) }
                Link("Create a limited token", destination: URL(string:"https://github.com/settings/personal-access-tokens")!)
            }
            Text(model.statuses[a.server] ?? "Not connected").font(.callout).textSelection(.enabled)
            Text("If access fails: check expiry, selected repositories, Issues read permission, and organization approval. Replace an expired PAT here. GitHub browser OAuth is not configured for this app.").font(.caption).foregroundStyle(.secondary)
        }
    }
    var permissions: some View {
        Panel {
            Text("3 · Approve exact issue-reading tools").font(.title2.bold())
            Text("Only these selected names will be granted to this Claude identity. Future tools stay blocked. Access follows the repositories allowed by your PAT.").foregroundStyle(.secondary)
            ForEach(ActivationState.tools, id: \.self) { name in
                let found = model.tools.contains { $0["name"] as? String == "\(a.server).\(name)" }
                Toggle(isOn: Binding(get: { selected.contains(name) }, set: { if $0 { selected.insert(name) } else { selected.remove(name) } })) {
                    VStack(alignment:.leading) {
                        Text(name).font(.system(.body, design:.monospaced))
                        Text(description(name) + (found ? "" : " · Not discovered: deselect or reconnect")).font(.caption).foregroundStyle(found ? Color.secondary : Color.red)
                    }
                }
            }
            Button("Approve selected tools") { model.act(["action":"activation_approve","client":a.client,"server":a.server,"tools":selected.sorted(),"consent":true]) }.buttonStyle(.borderedProminent).disabled(selected.isEmpty || selected.contains { name in !model.tools.contains { $0["name"] as? String == "\(a.server).\(name)" } })
            Text("These permissions apply to every connected app. Change or revoke them by opening the connector.").font(.caption).foregroundStyle(.secondary)
        }
    }
    var configure: some View {
        Panel {
            Text("4 · Connect Claude Desktop to Umbod").font(.title2.bold())
            Text("Quit Claude first. Preview the one entry Umbod will add. Other servers and settings are preserved; a private backup lets you undo this change.").foregroundStyle(.secondary)
            Text("No credential is written to Claude's configuration. Umbod locates its bundled bridge for you.").font(.caption).foregroundStyle(.secondary)
            Button("Preview Claude configuration…") { makePreview() }.buttonStyle(.borderedProminent).accessibilityIdentifier("activation.preview")
        }
    }
    var firstPrompt: some View {
        Panel {
            Text("5 · Ask Claude for a useful result").font(.title2.bold())
            Text("Restart Claude Desktop, open a new chat, enable Umbod's tools, and use this prompt. The gateway keeps running when you quit Umbod.").foregroundStyle(.secondary)
            TextField("Repository, e.g. owner/repository", text:$repository).textFieldStyle(.roundedBorder)
            Text(prompt).textSelection(.enabled).padding(12).background(.primary.opacity(0.04),in:RoundedRectangle(cornerRadius:8))
            Button("Copy first prompt") { model.copy(prompt) }
            if !a.activated { Label("Waiting for a successful call from the registered client",systemImage:"clock").foregroundStyle(.secondary) }
            Text("Copying this prompt or connecting a server does not count as activation. If no tools appear, restart Claude, check its MCP status, then review Permissions and the GitHub connection.").font(.caption).foregroundStyle(.secondary)
        }
    }
    var prompt: String { "Use Umbod's available GitHub issue-reading tools to find open issues in \(repository.isEmpty ? "OWNER/REPOSITORY" : repository). Summarize three actionable issues and include their links. Do not change anything." }
    var previewSheet: some View {
        VStack(alignment:.leading,spacing:16) {
            Text("Review Claude configuration").font(.title2.bold())
            Text("File: \(preview["path"] as? String ?? "")").font(.caption).textSelection(.enabled)
            Text("Add entry: \(preview["entry_name"] as? String ?? "")").font(.headline)
            ScrollView { Text((try? JSONText.encode(preview["entry"] ?? [:])) ?? "").font(.system(.caption,design:.monospaced)).textSelection(.enabled).frame(maxWidth:.infinity,alignment:.leading) }.frame(height:160)
            Text("Backup: \(preview["backup"] as? String ?? "")").font(.caption).textSelection(.enabled)
            Text("Umbod checks the file has not changed since this preview, writes a backup, applies this entry, and verifies it. Claude runs the bundled bridge with your user permissions.").font(.callout).foregroundStyle(.secondary)
            HStack { Spacer(); Button("Cancel") { showPreview=false }; Button("Allow & configure Claude") { applyPreview() }.buttonStyle(.borderedProminent).accessibilityIdentifier("activation.consent") }
        }.padding(24).frame(width:640)
    }
    func description(_ name: String) -> String {
        switch name { case "issue_read": "Read an issue and its details"; case "list_issues": "List repository issues"; default: "Search issues with a query" }
    }
    func progress(_ title: String,_ done: Bool) -> some View { Label(title,systemImage:done ? "checkmark.circle.fill":"circle").foregroundStyle(done ? .teal:.secondary) }
    func saveToken() {
        Task { model.busy=true;model.error="";defer{model.busy=false}
            do { _ = try await model.backend.request(["action":"activation_token","token":token]);token="";_ = try await model.backend.request(["action":"connect","id":a.server]);try await model.refresh() }
            catch { token="";model.error=error.localizedDescription;try? await model.refresh() }
        }
    }
    func makePreview() {
        Task { do { preview=try await model.backend.request(["action":"client_preview","path":model.clientConfig.path,"command":Bundle.main.bundleURL.appendingPathComponent("Contents/MacOS/umbod-gateway").path]);showPreview=true }catch{model.error=error.localizedDescription} }
    }
    func applyPreview() { showPreview=false;model.act(["action":"client_apply","preview":preview["id"] as? String ?? "","consent":true],success:"Claude configured. Restart Claude Desktop to load Umbod.") }
}
