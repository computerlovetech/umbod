import Foundation

public enum AppEnvironment: String, Sendable {
    case release, dev
    public static var current: AppEnvironment {
        AppEnvironment(rawValue: Bundle.main.object(forInfoDictionaryKey: "UmbodChannel") as? String ?? "dev") ?? .dev
    }
    public var name: String { self == .release ? "Umbod" : "Umbod Dev" }
    public var serverName: String { self == .release ? "umbod" : "umbod-dev" }
    public var dataDirectory: URL {
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/\(name)")
    }
    public var gatewayExecutable: URL { dataDirectory.appendingPathComponent("bin/umbod-gateway") }
}
