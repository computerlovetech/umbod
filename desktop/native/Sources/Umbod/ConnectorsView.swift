import SwiftUI
import AppKit
import UmbodCore

private enum ConnectorSheet: Identifiable {
    case add, edit(String), manage(String)
    var id: String { switch self { case .add: "add"; case .edit(let id): "edit-\(id)"; case .manage(let id): "manage-\(id)" } }
}
struct ServersView: View {
    @EnvironmentObject var model: AppModel
    @State private var sheet: ConnectorSheet?
    @Binding var selectedConnector: String?
    @State private var removal: String?
    // An offline draft receives its backend ID after first successful discovery.
    // Keep the selected detail and sheet attached through its stable host identity.
    private func connector(_ id: String) -> [String: Any]? {
        model.servers.first {
            $0["id"] as? String == id ||
            (id.hasPrefix("pending:") && $0["host_id"] as? String == String(id.dropFirst("pending:".count)))
        }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            if let id = selectedConnector, let connector = connector(id) {
                Button { selectedConnector = nil } label: { Label("All connectors", systemImage: "chevron.left") }
                ConnectorToolsView(connector: connector, manage: { sheet = .manage(id) }).id(id)
            } else {
                Button { sheet = .add } label: { Label("Add connector", systemImage: "plus") }.buttonStyle(BrandButtonStyle(primary: true)).accessibilityIdentifier("connectors.add")
                if model.servers.isEmpty {
                    ContentUnavailableView("No connectors yet", systemImage: "externaldrive.badge.plus", description: Text("Add a connector to make its tools available to your apps."))
                } else {
                    Panel {
                        ForEach(model.servers.indices, id: \.self) { index in
                            let server = model.servers[index]
                            let id = server["id"] as? String ?? ""
                            let tools = model.tools.filter { ($0["name"] as? String ?? "").hasPrefix(id + ".") }
                            if index > 0 { Divider() }
                            HStack(spacing: 16) {
                                Button { selectedConnector = id } label: {
                                    HStack(spacing: 14) {
                                        ConnectorIconView(
                                            source: server["icon_url"] as? String,
                                            fallbackSystemName: server["transport"] as? String == "stdio" ? "terminal" : "network"
                                        )
                                        VStack(alignment: .leading, spacing: 6) {
                                            Text(server["name"] as? String ?? "Connector").font(.system(size: 15, weight: .semibold))
                                            Text(model.statuses[id] ?? "Disconnected").font(.caption).foregroundStyle(Brand.muted)
                                        }
                                        Spacer()
                                        Text("\(tools.filter { model.allowedTools.contains($0["name"] as? String ?? "") }.count) / \(tools.count) tools enabled").font(.caption).foregroundStyle(Brand.muted)
                                        Image(systemName: "chevron.right").foregroundStyle(Brand.muted)
                                    }.padding(.vertical, 6).contentShape(Rectangle())
                                }.buttonStyle(.plain).accessibilityIdentifier("connector.row.\(server["name"] as? String ?? "")")
                                Menu {
                                    Button("Connection settings") { sheet = .manage(id) }
                                    Button("Connect / rediscover") { model.act(["action":"connect", "id":id]) }.disabled(model.busy)
                                    Button("Edit connection") { sheet = .edit(id) }
                                    Divider()
                                    Button("Remove connector", role: .destructive) { removal = id }
                                } label: { Image(systemName: "ellipsis").frame(width: 22, height: 22) }
                                .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize().help("Manage \(server["name"] as? String ?? "connector")")
                            }
                        }
                    }
                }
            }
        }
        .sheet(item: $sheet) { route in
            switch route {
            case .add: ServerEditor(draft: ServerDraft())
            case .edit(let id):
                if let server = connector(id) { ServerEditor(draft: ServerDraft(server)) }
            case .manage(let id):
                if let server = connector(id) {
                    ConnectorManagementView(server: server, edit: { sheet = .edit(id) })
                }
            }
        }
        .confirmationDialog("Remove this connector and its tool permissions?", isPresented: Binding(get: { removal != nil }, set: { if !$0 { removal = nil } }), titleVisibility: .visible) {
            Button("Remove connector", role: .destructive) {
                if let id = removal { model.act(["action":"server_remove", "id":id]); if selectedConnector == id { selectedConnector = nil } }
                removal = nil
            }
        }
    }
}
private struct ConnectorIconView: View {
    let source: String?
    let fallbackSystemName: String

    var body: some View {
        Group {
            if let source, let icon = ConnectorIconSource(source) {
                switch icon {
                case .embedded(let data):
                    if let image = NSImage(data: data) {
                        Image(nsImage: image).resizable().scaledToFit()
                    } else {
                        fallback
                    }
                case .remote(let url):
                    AsyncImage(url: url) { phase in
                        if let image = phase.image {
                            image.resizable().scaledToFit()
                        } else {
                            fallback
                        }
                    }
                }
            } else {
                fallback
            }
        }
        .frame(width: 38, height: 38)
        .background(Brand.accentSoft, in: RoundedRectangle(cornerRadius: 10))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private var fallback: some View {
        Image(systemName: fallbackSystemName)
            .font(.system(size: 20))
            .foregroundStyle(Brand.accent)
    }
}
struct ConnectorManagementView: View {
    @EnvironmentObject var model: AppModel
    @Environment(\.dismiss) private var dismiss
    let server: [String: Any]
    var edit: () -> Void
    @State private var clientID = ""
    @State private var advancedSignIn = false
    private var id: String { server["id"] as? String ?? "" }
    private var oauthStatus: String {
        switch model.oauthStatuses[id] {
        case "pending": "Waiting for browser sign-in…"
        case "signed_in": "Signed in"
        case "failed": "Sign-in failed. Try again."
        default: server["oauth"] as? Bool == true ? "Signed in" : "Not signed in"
        }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack { Text(server["name"] as? String ?? "Connection settings").font(.title2.bold()); Spacer(); Button("Done") { dismiss() } }
            StatusMessages()
            if model.busy {
                HStack { ProgressView().controlSize(.small); Text(model.activity) }
                    .accessibilityIdentifier("connector.progress")
            }
            Text(model.statuses[id] ?? "Disconnected").foregroundStyle(Brand.muted)
            Panel {
                Text("Connection").font(.headline)
                Text(server["transport"] as? String == "stdio" ? (server["command"] as? String ?? "") : (server["url"] as? String ?? "")).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                HStack {
                    Button("Connect / rediscover") { model.act(["action":"connect", "id":id]) }.disabled(model.busy)
                    Button("Edit connection", action: edit)
                }
            }
            if server["transport"] as? String == "http" {
                Panel {
                    Text("Browser sign-in (OAuth)").font(.headline)
                    Text(oauthStatus).font(.callout).foregroundStyle(Brand.muted)
                    Button { advancedSignIn.toggle() } label: {
                        HStack {
                            Text("Use a custom client ID")
                            Spacer()
                            Image(systemName: advancedSignIn ? "chevron.up" : "chevron.down")
                        }.frame(maxWidth: .infinity).contentShape(Rectangle())
                    }
                    if advancedSignIn {
                        TextField("Public client ID (optional)", text: $clientID)
                        Text("Only needed when your provider supplies a client ID.").font(.caption)
                    }
                    HStack {
                        Button("Sign in with browser") { model.signIn(id, clientID: clientID) }
                        Button("Refresh token") { model.act(["action":"oauth_refresh", "id":id], success: "Token refreshed and transport reconnected.") }
                        Button("Sign out") { model.act(["action":"oauth_logout", "id":id]) }
                    }.disabled(model.busy)
                    Text("After signing in, connect to discover tools.").font(.caption).foregroundStyle(Brand.muted)
                }
            }
        }.padding(28).frame(width: 600).modifier(BrandAppearance())
    }
}
struct ConnectorToolsView: View {
    @EnvironmentObject var model: AppModel
    let connector: [String: Any]
    var manage: () -> Void
    @State private var query = ""
    @State private var filter = "All tools"
    @State private var selectedName: String?
    private var id: String { connector["id"] as? String ?? "" }
    private var tools: [[String: Any]] {
        model.tools.filter { ($0["name"] as? String ?? "").hasPrefix(id + ".") }
            .sorted { ($0["name"] as? String ?? "") < ($1["name"] as? String ?? "") }
    }
    private var filtered: [[String: Any]] {
        tools.filter { tool in
            let name = tool["name"] as? String ?? ""
            let enabled = model.allowedTools.contains(name)
            return (filter == "All tools" || enabled == (filter == "Enabled")) &&
                (query.isEmpty || name.localizedCaseInsensitiveContains(query) || (tool["description"] as? String ?? "").localizedCaseInsensitiveContains(query))
        }
    }
    private var selected: [String: Any]? { filtered.first { $0["name"] as? String == selectedName } ?? filtered.first }
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack {
                VStack(alignment: .leading, spacing: 8) {
                    Text(connector["name"] as? String ?? "Connector").font(.system(size: 24, weight: .semibold))
                    Text("\(model.statuses[id] ?? "Disconnected") · \(tools.filter { model.allowedTools.contains($0["name"] as? String ?? "") }.count) of \(tools.count) tools enabled").foregroundStyle(Brand.muted)
                }
                Spacer()
                Button("Connection settings", action: manage)
            }
            Text("Enabled tools are available to every app connected to Umbod.").font(.callout).foregroundStyle(Brand.muted)
                .padding(14).frame(maxWidth: .infinity, alignment: .leading).background(Brand.soft, in: RoundedRectangle(cornerRadius: 8))
            HStack(spacing: 12) {
                TextField("Search tools…", text: $query).frame(maxWidth: 340)
                Picker("Show", selection: $filter) { ForEach(["All tools", "Enabled", "Disabled"], id: \.self) { Text($0) } }.frame(width: 180)
                Spacer()
            }
            if tools.isEmpty {
                ContentUnavailableView("No tools discovered", systemImage: "wrench.and.screwdriver", description: Text("Open connection settings to connect or rediscover tools."))
            } else if filtered.isEmpty {
                ContentUnavailableView.search(text: query)
            } else {
                HStack(alignment: .top, spacing: 24) {
                    ScrollView {
                        VStack(spacing: 0) {
                            ForEach(filtered.indices, id: \.self) { index in
                                let tool = filtered[index]
                                let name = tool["name"] as? String ?? ""
                                HStack(spacing: 10) {
                                    Button { selectedName = name } label: {
                                        Text(String(name.dropFirst(id.count + 1))).font(.system(size: 12, design: .monospaced))
                                            .frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 10).contentShape(Rectangle())
                                    }.buttonStyle(.plain).accessibilityAddTraits(selected?["name"] as? String == name ? [.isSelected] : [])
                                    permissionToggle(name)
                                }.padding(.horizontal, 14).padding(.vertical, 5)
                                    .background(selected?["name"] as? String == name ? Brand.accentSoft : Brand.canvas)
                                if index < filtered.count - 1 { Divider() }
                            }
                        }
                    }.frame(maxWidth: .infinity).frame(height: 470).clipShape(RoundedRectangle(cornerRadius: 12))
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Brand.border))
                    ScrollView {
                        if let tool = selected {
                            let name = tool["name"] as? String ?? ""
                            VStack(alignment: .leading, spacing: 20) {
                                Text("TOOL DETAILS").font(.system(size: 10, design: .monospaced)).tracking(1).foregroundStyle(Brand.muted)
                                Text(String(name.dropFirst(id.count + 1))).font(.system(size: 15, weight: .semibold, design: .monospaced)).textSelection(.enabled)
                                Text(tool["description"] as? String ?? "No description provided.").font(.system(size: 14)).lineSpacing(4).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
                                HStack { Text(model.allowedTools.contains(name) ? "Enabled for your apps" : "Disabled for your apps"); Spacer(); permissionToggle(name) }
                                Divider()
                                DisclosureGroup("Input schema") {
                                    Text((try? JSONText.encode(tool["inputSchema"] ?? [:])) ?? "{}").font(.system(size: 12, design: .monospaced)).textSelection(.enabled).padding(.top, 12)
                                }.id(name)
                            }.padding(24).frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }.frame(maxWidth: .infinity).frame(height: 470).background(Brand.soft, in: RoundedRectangle(cornerRadius: 12))
                }
            }
        }
    }
    private func permissionToggle(_ name: String) -> some View {
        Toggle("Allow \(String(name.dropFirst(id.count + 1)))", isOn: Binding(get: { model.allowedTools.contains(name) }, set: { model.act(["action":"grant", "tool":name, "allow":$0]) }))
            .accessibilityIdentifier("tool.allow.\(String(name.dropFirst(id.count + 1)))").labelsHidden().toggleStyle(.switch).controlSize(.small).disabled(model.busy)
    }
}
