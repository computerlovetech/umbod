import Foundation
public struct ActivationState {
    public enum Stage { case choose, connect, approve, configure, tryPrompt, activated }
    public let client: String
    public let server: String
    public let configured: Bool
    public let activated: Bool
    public let fixture: Bool
    public let connected: Bool
    public let approved: Bool
    public var stage: Stage {
        if activated { return .activated }
        if client.isEmpty { return .choose }
        if !connected { return .connect }
        if !approved { return .approve }
        if !configured { return .configure }
        return .tryPrompt
    }
    public init(_ status: [String: Any]) {
        let journey = status["activation"] as? [String: Any] ?? [:]
        client = journey["client"] as? String ?? ""
        server = journey["server"] as? String ?? ""
        configured = journey["configured"] as? Bool ?? false
        activated = journey["activated"] as? Bool ?? false
        fixture = journey["fixture"] as? Bool ?? false
        connected = (status["statuses"] as? [String:String])?[server] == "Connected"
        let grants = status["allowed_tools"] as? [String] ?? []
        let prefix = server
        approved = ["issue_read","list_issues","search_issues"].contains { grants.contains("\(prefix).\($0)") }
    }
    public static let tools = ["issue_read", "list_issues", "search_issues"]
}
