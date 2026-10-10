import SwiftUI
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
    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            if let id = selectedConnector, let connector = model.servers.first(where: { $0["id"] as? String == id }) {
                Button { selectedConnector = nil } label: { Label("All connectors", systemImage: "chevron.left") }
                ConnectorToolsView(connector: connector, manage: { sheet = .manage(id) }).id(id)
            } else {
                Button { sheet = .add } label: { Label("Add connector", systemImage: "plus") }.buttonStyle(BrandButtonStyle(primary: true))
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
                                        Image(systemName: server["transport"] as? String == "stdio" ? "terminal" : "network")
                                            .font(.system(size: 20)).foregroundStyle(Brand.accent).frame(width: 38, height: 38).background(Brand.accentSoft, in: RoundedRectangle(cornerRadius: 10))
                                        VStack(alignment: .leading, spacing: 6) {
                                            Text(server["name"] as? String ?? "Connector").font(.system(size: 15, weight: .semibold))
                                            Text(model.statuses[id] ?? "Disconnected").font(.caption).foregroundStyle(Brand.muted)
                                        }
                                        Spacer()
                                        Text("\(tools.filter { model.allowedTools.contains($0["name"] as? String ?? "") }.count) / \(tools.count) tools enabled").font(.caption).foregroundStyle(Brand.muted)
                                        Image(systemName: "chevron.right").foregroundStyle(Brand.muted)
                                    }.padding(.vertical, 6).contentShape(Rectangle())
                                }.buttonStyle(.plain)
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
                if let server = model.servers.first(where: { $0["id"] as? String == id }) { ServerEditor(draft: ServerDraft(server)) }
            case .manage(let id):
                if let server = model.servers.first(where: { $0["id"] as? String == id }) {
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
struct ConnectorManagementView: View {
    @EnvironmentObject var model: AppModel
    @Environment(\.dismiss) private var dismiss
    let server: [String: Any]
    var edit: () -> Void
    @State private var clientID = ""
    private var id: String { server["id"] as? String ?? "" }
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack { Text(server["name"] as? String ?? "Connection settings").font(.title2.bold()); Spacer(); Button("Done") { dismiss() } }
            StatusMessages()
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
                    TextField("Public client ID (optional)", text: $clientID)
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
                                HStack { Text("Available to your apps"); Spacer(); permissionToggle(name) }
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
            .labelsHidden().toggleStyle(.switch).controlSize(.small).disabled(model.busy)
    }
}
