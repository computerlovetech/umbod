import Foundation
public struct ServerDraft {
    public var id = ""
    public var name = ""
    public var transport = "stdio"
    public var command = ""
    public var arguments = ""
    public var url = ""
    public var oauth = false
    public var headerReferences = "{}"
    public var environmentReferences = "{}"
    public init() {}
    public init(_ value: [String: Any]) {
        id = value["id"] as? String ?? ""; name = value["name"] as? String ?? ""
        transport = value["transport"] as? String ?? "stdio"; command = value["command"] as? String ?? ""
        arguments = (value["args"] as? [String] ?? []).joined(separator: "\n"); url = value["url"] as? String ?? ""
        oauth = value["oauth"] as? Bool ?? false
        headerReferences = (try? JSONText.encode(value["headers"] ?? [:])) ?? "{}"
        environmentReferences = (try? JSONText.encode(value["env"] ?? [:])) ?? "{}"
    }
    public func payload() throws -> [String: Any] {
        let headers = try JSONSerialization.jsonObject(with: Data(headerReferences.utf8))
        let env = try JSONSerialization.jsonObject(with: Data(environmentReferences.utf8))
        guard headers is [String: String], env is [String: String] else { throw ContractError.message("Credential references must be JSON objects mapping names to Keychain references.") }
        return ["id": id, "name": name, "transport": transport, "command": command,
                "args": arguments.split(separator: "\n").map(String.init), "url": url,
                "oauth": oauth, "headers": headers, "env": env]
    }
}
public enum ContractError: LocalizedError {
    case message(String)
    public var errorDescription: String? { if case let .message(text) = self { return text }; return nil }
}
public enum JSONText {
    public static func encode(_ value: Any) throws -> String {
        String(decoding: try JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]), as: UTF8.self)
    }
}
public enum ClientConfiguration {
    public static func bridge(bundlePath: String, environment: AppEnvironment = .release, executable: URL? = nil) throws -> String {
        try JSONText.encode(["mcpServers": [environment.serverName: ["command": executable?.path ?? bundlePath + "/Contents/MacOS/umbod-gateway", "args": ["bridge", "--profile", environment.rawValue]]]])
    }
}
extension ClientConfiguration {
    public static func destination(home: URL, dataDirectory: URL?) -> URL {
        if let dataDirectory { return dataDirectory.appendingPathComponent("fixture-claude.json") }
        return home.appendingPathComponent("Library/Application Support/Claude/claude_desktop_config.json")
    }
}
