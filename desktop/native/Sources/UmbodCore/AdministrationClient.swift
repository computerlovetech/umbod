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
            throw ContractError.message(Self.errorMessage(value, statusCode: (response as? HTTPURLResponse)?.statusCode ?? 0))
        }
        return value
    }

    public static func errorMessage(_ body: [String: Any], statusCode: Int) -> String {
        if let detail = body["detail"] as? String, !detail.isEmpty { return detail }
        if let detail = body["detail"] as? [String: Any], let message = detail["message"] as? String, !message.isEmpty {
            if detail["code"] as? String == "auth_rejected" {
                return message + " Sign in with browser from the connector page, or check its authentication credentials."
            }
            return message
        }
        return "Backend request failed (\(statusCode))."
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
        var oauthErrors: [String: String] = [:]
        var oauthStages: [String: String] = [:]
        let authentication = try await send("GET", "/api/admin/connectors/mcp/oauth/status")
        let hostOAuthStages = authentication["oauth_stages"] as? [String: String] ?? [:]
        let hostOAuthErrors = authentication["oauth_errors"] as? [String: String] ?? [:]
        let hostOAuth = authentication["oauth_status"] as? [String: String] ?? [:]
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
            if let key = server["host_id"] as? String { oauthErrors[id] = hostOAuthErrors[key]; oauthStages[id] = hostOAuthStages[key] }
            let health = item["health"] as? [String: Any] ?? [:]
            statuses[id] = Self.connectionStatus(health: health, oauth: oauthStatuses[id] ?? "", pending: false)
            let catalog = try await send("GET", connector(id) + "/tools")
            for tool in catalog["tools"] as? [[String: Any]] ?? [] {
                guard let name = tool["name"] as? String else { continue }
                let identity = id + "." + name
                tools.append(["name": identity, "description": tool["description"] ?? "", "inputSchema": tool["input_schema"] ?? [:], "annotations": tool["annotations"] ?? [:]])
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
            oauthErrors[id] = hostOAuthErrors[key]
            oauthStages[id] = hostOAuthStages[key]
            statuses[id] = Self.connectionStatus(health: [:], oauth: oauthStatuses[id] ?? "", pending: true)
        }
        var result = host
        result["oauth_status"] = oauthStatuses
        result["oauth_errors"] = oauthErrors
        result["oauth_stages"] = oauthStages
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
                result = try await send("POST", "/api/admin/connectors/mcp", ["metadata": ["display_name": draft["name"] as? String ?? "Connector", "capability_description": "Tools from \(draft["name"] as? String ?? "connector")", "public_path": "/mcp/proxies/" + slug], "configuration": configuration])
            } catch {
                // Keep a disconnected draft so OAuth and offline connections can be repaired.
                return ["server": ["id": "pending:" + hostID], "status": "pending"]
            }
            guard let createdID = result["connector_id"] as? String else { throw ContractError.message("Missing connector identity") }
            connectorID = createdID
        } else {
            connectorID = id
            if prepared["connection_changed"] as? Bool != false {
                do {
                    _ = try await send("PUT", connector(id) + "/configuration", configuration)
                } catch {
                    // The local proxy already holds the saved connection. Keep its
                    // identity and permissions while guided setup repairs sign-in.
                    let oauthState = try await send("GET", "/api/admin/connectors/mcp/oauth/status")
                    let authentication = oauthState["oauth_status"] as? [String: String] ?? [:]
                    guard authentication[hostID] == "sign_in_required" else { throw error }
                }
            }
            result = [:]
            let current = try await send("GET", connector(id))
            let name = draft["name"] as? String ?? "Connector"
            if current["display_name"] as? String != name {
                _ = try await send("PATCH", connector(id), ["display_name": name])
            }
        }
        _ = try await send("PUT", "/desktop/upstreams/" + component(hostID) + "/binding", ["connector_id": connectorID])
        return ["server": ["id": connectorID]]
    }

    public func grant(_ identity: String, allow: Bool) async throws -> [String: Any] {
        guard let separator = identity.firstIndex(of: ".") else { throw ContractError.message("Invalid tool identity") }
        let id = String(identity[..<separator]), tool = String(identity[identity.index(after: separator)...])
        return try await grantTools(id, tools: [tool], allow: allow)
    }

    public func grantTools(_ id: String, tools: [String], allow: Bool) async throws -> [String: Any] {
        guard !id.isEmpty, !id.hasPrefix("pending:"), !tools.isEmpty,
              tools.allSatisfy({ !$0.isEmpty }), Set(tools).count == tools.count else {
            throw ContractError.message("Choose discovered tools from one connector.")
        }
        _ = try await send("POST", "/api/admin/mcp-permissions/groups/desktop-owner")
        if allow { _ = try await send("PUT", connector(id) + "/publication") }
        _ = try await send("PUT", connector(id) + "/tools/activation", ["tools": tools.map {
            ["tool_id": $0, "activation_status": allow ? "enabled" : "disabled"]
        }])
        return try await send("PUT", "/api/admin/mcp-permissions/groups/desktop-owner/permissions", ["capabilities": tools.map {
            ["connector_id": id, "capability_kind": "tool", "capability_key": $0, "permission_status": allow ? "enabled" : "disabled"]
        }])
    }

    public static func connectionStatus(health: [String: Any], oauth: String, pending: Bool) -> String {
        if oauth == "pending" { return "Waiting for sign-in…" }
        if oauth == "sign_in_required" || health["reason"] as? String == "auth_rejected" {
            return "Sign-in required"
        }
        if oauth == "discovery_failed" { return "Authorized — retry tool discovery" }
        if oauth == "cancelled" { return "Sign-in cancelled — retry when ready" }
        if oauth == "failed" { return "Sign-in failed — try again" }
        if health["status"] as? String == "healthy" { return "Connected" }
        if oauth == "signed_in" && pending { return "Signed in — ready to discover tools" }
        if health["reason"] as? String == "timeout" { return "Connection timed out — retry" }
        if health["reason"] as? String == "unreachable" { return "Server unreachable — check connection" }
        return pending ? "Not connected — continue setup" : "Disconnected"
    }

    public func action(_ body: [String: Any]) async throws -> [String: Any] {
        let id = body["id"] as? String ?? ""
        switch body["action"] as? String {
        case "oauth_begin", "oauth_refresh", "oauth_logout", "oauth_cancel", "oauth_details", "oauth_discover":
            let operation = String((body["action"] as? String ?? "").dropFirst(6))
            let path = "/api/admin/connectors/mcp/oauth/" + component(id)
            if operation == "details" { return try await send("GET", path) }
            var payload: [String: Any] = [:]
            if operation == "begin" {
                payload["client_id"] = body["client_id"] ?? ""
                if let scopes = body["scopes"] { payload["scopes"] = scopes }
            }
            return try await send("POST", path + "/" + operation, payload)
        case "settings_get": return try await send("GET", "/desktop/settings")
        case "settings_save": return try await send("PUT", "/desktop/settings", body["settings"] as? [String: Any] ?? [:])
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
            // The removal confirmation includes permissions, including stale grants
            // for tools that are no longer present in a disconnected catalog.
            let permissions = try await send("GET", "/api/admin/mcp-permissions/groups/desktop-owner")
            let capabilities = (permissions["capabilities"] as? [[String: Any]] ?? []).filter { $0["connector_id"] as? String == id }.map { grant in
                var change = grant
                change["permission_status"] = "disabled"
                return change
            }
            let connectors: [[String: Any]] = (permissions["connector_ids"] as? [String] ?? []).contains(id)
                ? [["connector_id": id, "permission_status": "disabled"]] : []
            if !capabilities.isEmpty || !connectors.isEmpty {
                _ = try await send("PUT", "/api/admin/mcp-permissions/groups/desktop-owner/permissions", ["capabilities": capabilities, "connectors": connectors])
            }
            _ = try await send("DELETE", connector(id))
            if let key = saved.first(where: { $0.value["id"] as? String == id })?.key { _ = try await send("DELETE", "/desktop/upstreams/" + component(key)) }
            return [:]
        case "grant": return try await grant(body["tool"] as? String ?? "", allow: body["allow"] as? Bool ?? false)
        case "grant_tools": return try await grantTools(id, tools: body["tools"] as? [String] ?? [], allow: body["allow"] as? Bool ?? false)
        case "secret_set": return try await send("PUT", "/desktop/credentials/" + component(body["reference"] as? String ?? ""), ["value": body["value"] ?? ""])
        case "secret_delete": return try await send("DELETE", "/desktop/credentials/" + component(body["reference"] as? String ?? ""))
        case "connection_setup", "connection_token": return try await send("GET", "/desktop/connection")
        default: return try await send("POST", "/desktop/actions", body)
        }
    }
}
