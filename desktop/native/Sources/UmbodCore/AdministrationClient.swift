import Foundation

/// Native presentation mapping over Umbod's shared administration API.
@MainActor public final class AdministrationClient {
    let origin: String
    let token: String
    let timeout: TimeInterval
    public init(origin: String, token: String, timeout: TimeInterval = 45) { self.origin = origin; self.token = token; self.timeout = timeout }

    public func send(_ method: String, _ path: String, _ body: [String: Any]? = nil) async throws -> [String: Any] {
        guard let url = URL(string: origin + path) else { throw ContractError.message("Invalid backend address") }
        var request = URLRequest(url: url)
        request.httpMethod = method; request.timeoutInterval = timeout
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        let value = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw ContractError.message(value["detail"] as? String ?? "Backend request failed (\((response as? HTTPURLResponse)?.statusCode ?? 0)).")
        }
        return value
    }
    func component(_ value: String) -> String {
        value.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? ""
    }
    func connector(_ id: String) -> String { "/api/admin/connectors/mcp/" + component(id) }

    public func status() async throws -> [String: Any] {
        let host = try await send("GET", "/desktop/state")
        let inventory = try await send("GET", "/api/admin/connectors/mcp")
        let saved = host["servers"] as? [String: [String: Any]] ?? [:]
        var servers: [[String: Any]] = [], tools: [[String: Any]] = [], enabled: [String] = []
        var statuses: [String: String] = [:]
        var oauthStatuses: [String: String] = [:]
        let hostOAuth = host["oauth_status"] as? [String: String] ?? [:]
        let permissions = try await send("GET", "/api/admin/mcp-permissions/groups/desktop-owner")
        let grants = permissions["capabilities"] as? [[String: Any]] ?? []
        let connectorGrants = Set(permissions["connector_ids"] as? [String] ?? [])
        for item in inventory["connectors"] as? [[String: Any]] ?? [] {
            guard let id = item["connector_id"] as? String else { continue }
            let detail = try await send("GET", connector(id))
            var server = saved.values.first { $0["id"] as? String == id } ?? ["transport": "http", "url": detail["endpoint_url"] ?? ""]
            server["id"] = id; server["name"] = item["display_name"]
            if let iconURL = item["icon_url"] as? String, !iconURL.isEmpty {
                server["icon_url"] = iconURL
            }
            servers.append(server)
            if let key = server["host_id"] as? String { oauthStatuses[id] = hostOAuth[key] ?? (server["oauth"] as? Bool == true ? "signed_in" : "signed_out") }
            let health = item["health"] as? [String: Any] ?? [:]
            statuses[id] = health["status"] as? String == "healthy" ? "Connected" : "Disconnected"
            let catalog = try await send("GET", connector(id) + "/tools")
            for tool in catalog["tools"] as? [[String: Any]] ?? [] {
                guard let name = tool["name"] as? String else { continue }
                let identity = id + "." + name
                tools.append(["name": identity, "description": tool["description"] ?? "", "inputSchema": tool["input_schema"] ?? [:]])
                let granted = connectorGrants.contains(id) || grants.contains { $0["connector_id"] as? String == id && $0["capability_kind"] as? String == "tool" && $0["capability_key"] as? String == name }
                if tool["activation_status"] as? String == "enabled" && granted { enabled.append(identity) }
            }
        }
        for (key, message) in host["transport_errors"] as? [String: String] ?? [:] {
            if let id = saved[key]?["id"] as? String { statuses[id] = message }
        }
        let registered = Set(servers.compactMap { $0["id"] as? String })
        for (key, value) in saved where !registered.contains(value["id"] as? String ?? "") {
            var pending = value
            let id = "pending:" + key
            pending["id"] = id; pending["host_id"] = key
            servers.append(pending)
            oauthStatuses[id] = hostOAuth[key] ?? (value["oauth"] as? Bool == true ? "signed_in" : "signed_out")
            statuses[id] = "Not connected — open connection settings to sign in or connect"
        }
        var result = host
        result["oauth_status"] = oauthStatuses
        result["servers"] = servers; result["tools"] = tools; result["allowed_tools"] = enabled; result["statuses"] = statuses
        return result
    }

    public func save(_ draft: [String: Any]) async throws -> [String: Any] {
        var draft = draft
        let requestedID = draft["id"] as? String ?? ""
        let id = requestedID.hasPrefix("pending:") ? "" : requestedID
        if !id.isEmpty {
            let state = try await send("GET", "/desktop/state")
            let saved = state["servers"] as? [String: [String: Any]] ?? [:]
            draft["host_id"] = saved.values.first { $0["id"] as? String == id }?["host_id"]
        } else if requestedID.hasPrefix("pending:") {
            draft["host_id"] = String(requestedID.dropFirst(8))
            draft["id"] = ""
        }
        let prepared = try await send("POST", "/desktop/upstreams", draft)
        guard let configuration = prepared["configuration"] as? [String: Any], let hostID = prepared["host_id"] as? String else { throw ContractError.message("Invalid transport response") }
        let result: [String: Any]
        let connectorID: String
        if id.isEmpty {
            let slug = "desktop-" + UUID().uuidString.lowercased()
            do {
                result = try await send("POST", "/api/admin/connectors/mcp", ["metadata": ["display_name": draft["name"] as? String ?? "Connector", "tool_name_prefix": slug.replacingOccurrences(of: "-", with: "_"), "capability_description": "Tools from \(draft["name"] as? String ?? "connector")", "public_path": "/mcp/proxies/" + slug], "configuration": configuration])
            } catch {
                // Keep a disconnected draft so OAuth and offline connections can be repaired.
                return ["server": ["id": "pending:" + hostID], "status": "pending"]
            }
            guard let createdID = result["connector_id"] as? String else { throw ContractError.message("Missing connector identity") }
            connectorID = createdID
        } else {
            connectorID = id
            if prepared["connection_changed"] as? Bool != false {
                _ = try await send("PUT", connector(id) + "/configuration", configuration)
            }
            result = [:]
            _ = try await send("PATCH", connector(id), ["display_name": draft["name"] as? String ?? "Connector"])
        }
        _ = try await send("PUT", "/desktop/upstreams/" + component(hostID) + "/binding", ["connector_id": connectorID])
        return ["server": ["id": connectorID]]
    }

    public func grant(_ identity: String, allow: Bool) async throws -> [String: Any] {
        guard let separator = identity.firstIndex(of: ".") else { throw ContractError.message("Invalid tool identity") }
        let id = String(identity[..<separator]), tool = String(identity[identity.index(after: separator)...])
        _ = try await send("POST", "/api/admin/mcp-permissions/groups/desktop-owner")
        // Tool enablement includes publication; discovery alone does not expose tools.
        // This also repairs connectors saved by older desktop builds without publication.
        if allow { _ = try await send("PUT", connector(id) + "/publication") }
        // Revoke activation first; only grant permission after activation succeeds.
        _ = try await send("PUT", connector(id) + "/tools/activation", ["tools": [["tool_id": tool, "activation_status": allow ? "enabled" : "disabled"]]])
        return try await send("PUT", "/api/admin/mcp-permissions/groups/desktop-owner/permissions", ["capabilities": [["connector_id": id, "capability_kind": "tool", "capability_key": tool, "permission_status": allow ? "enabled" : "disabled"]]])
    }

    public func action(_ body: [String: Any]) async throws -> [String: Any] {
        let id = body["id"] as? String ?? ""
        switch body["action"] as? String {
        case "health": return try await send("GET", "/desktop/health")
        case "shutdown": return try await send("POST", "/desktop/shutdown")
        case "status": return try await status()
        case "server_save": return try await save(body["server"] as? [String: Any] ?? [:])
        case "connect":
            var connectorID = id
            if id.hasPrefix("pending:") {
                let state = try await send("GET", "/desktop/state")
                let saved = state["servers"] as? [String: [String: Any]] ?? [:]
                guard var draft = saved[String(id.dropFirst(8))] else { throw ContractError.message("Connector draft is missing") }
                draft["id"] = id
                // Retry an offline draft even when its saved configuration is unchanged.
                draft["reconnect"] = true
                let response = try await save(draft)
                connectorID = (response["server"] as? [String: Any])?["id"] as? String ?? ""
                guard !connectorID.hasPrefix("pending:") && !connectorID.isEmpty else { throw ContractError.message("Cannot connect. Check the executable, address, or sign-in and retry.") }
            } else {
                let state = try await send("GET", "/desktop/state")
                let saved = state["servers"] as? [String: [String: Any]] ?? [:]
                if let key = saved.first(where: { $0.value["id"] as? String == id })?.key {
                    _ = try await send("POST", "/desktop/upstreams/" + component(key) + "/restart")
                }
            }
            _ = try await send("POST", connector(connectorID) + "/discoveries")
            return try await send("PUT", connector(connectorID) + "/publication")
        case "server_remove":
            let state = try await send("GET", "/desktop/state")
            let saved = state["servers"] as? [String: [String: Any]] ?? [:]
            if id.hasPrefix("pending:") { return try await send("DELETE", "/desktop/upstreams/" + component(String(id.dropFirst(8)))) }
            _ = try await send("DELETE", connector(id))
            if let key = saved.first(where: { $0.value["id"] as? String == id })?.key { _ = try await send("DELETE", "/desktop/upstreams/" + component(key)) }
            return [:]
        case "grant": return try await grant(body["tool"] as? String ?? "", allow: body["allow"] as? Bool ?? false)
        case "secret_set": return try await send("PUT", "/desktop/credentials/" + component(body["reference"] as? String ?? ""), ["value": body["value"] ?? ""])
        case "secret_delete": return try await send("DELETE", "/desktop/credentials/" + component(body["reference"] as? String ?? ""))
        case "connection_setup", "connection_token": return try await send("GET", "/desktop/connection")
        default: return try await send("POST", "/desktop/actions", body)
        }
    }
}
