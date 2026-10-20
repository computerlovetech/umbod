import Foundation
import Combine

public enum ConnectorExposureMode: String, Codable, CaseIterable, Sendable {
    case gateway, flat, codemode
    public var explanation: String {
        switch self {
        case .gateway: return "Recommended. Exposes search_tools and execute_tool. Uploaded-file connector tools are currently unsupported."
        case .flat: return "Exposes each enabled tool directly. Required for uploaded-file tools; can increase startup time and context size."
        case .codemode: return "Exposes search_tools and execute_code. Uploaded-file connector tools are currently unsupported."
        }
    }
}

public struct DesktopBackendSettings: Codable, Equatable, Sendable {
    public var exposureMode: ConnectorExposureMode = .gateway
    public var administratorEnabled = false
    enum CodingKeys: String, CodingKey {
        case exposureMode = "connector_tool_exposure_mode"
        case administratorEnabled = "mcp_administrator_enabled"
    }
    public init() {}
    public init(_ value: [String: Any]) throws {
        self = try JSONDecoder().decode(Self.self, from: JSONSerialization.data(withJSONObject: value))
    }
    public var payload: [String: Any] {
        ["connector_tool_exposure_mode": exposureMode.rawValue, "mcp_administrator_enabled": administratorEnabled]
    }
}

/// Only backend responses establish saved/effective state; never UserDefaults.
@MainActor public final class AdvancedSettingsModel: ObservableObject {
    @Published public var draft = DesktopBackendSettings() {
        didSet { notice = "" }
    }
    @Published public private(set) var saved: DesktopBackendSettings?
    @Published public private(set) var effective: DesktopBackendSettings?
    @Published public private(set) var confirmAdministrator = false
    @Published public private(set) var working = false
    @Published public private(set) var error = ""
    @Published public private(set) var notice = ""
    public var hasPendingChanges: Bool { saved != nil && (draft != saved || saved != effective) }
    public init() {}
    public func canSaveAndRestart(isOnline: Bool) -> Bool {
        guard saved != nil, !working else { return false }
        return isOnline ? hasPendingChanges : effective == nil && draft == saved
    }
    public func requestAdministrator(_ enabled: Bool) {
        if enabled && !draft.administratorEnabled { confirmAdministrator = true }
        else { draft.administratorEnabled = enabled }
    }
    public func acceptAdministrator() { draft.administratorEnabled = true; confirmAdministrator = false }
    public func cancelAdministrator() { confirmAdministrator = false }
    private func snapshot(_ response: [String: Any]) throws -> (DesktopBackendSettings, DesktopBackendSettings) {
        guard let pending = response["pending"] as? [String: Any], let running = response["effective"] as? [String: Any] else {
            throw ContractError.message("Backend settings are unavailable. Restart the connection and retry.")
        }
        return try (DesktopBackendSettings(pending), DesktopBackendSettings(running))
    }
    public func load(preserveDraft: Bool = false, request: ([String: Any]) async throws -> [String: Any]) async throws {
        let retainDraft = preserveDraft && saved != nil && draft != saved
        let (pending, running) = try snapshot(await request(["action": "settings_get"]))
        saved = pending; effective = running
        if !retainDraft { draft = pending }
    }
    public func saveAndRestart(
        request: ([String: Any]) async throws -> [String: Any],
        stop: () async throws -> Void,
        start: () async throws -> Void
    ) async {
        guard !working, saved != nil else { return }
        working = true; error = ""; notice = ""
        defer { working = false }
        var persisted = false
        do {
            // After a failed start the backend is offline, but the saved draft is
            // already durable. Retry startup without requiring an offline API.
            if effective != nil || saved != draft {
                let (pending, running) = try snapshot(await request(["action": "settings_save", "settings": draft.payload]))
                saved = pending; effective = running
                guard pending == draft else { throw ContractError.message("Backend did not save the selected settings.") }
            }
            persisted = true
            try await stop()
            effective = nil
            try await start()
            let health = try await request(["action": "health"])
            guard health["status"] as? String == "ok" else { throw ContractError.message("Backend health check failed.") }
            let (pending, running) = try snapshot(await request(["action": "settings_get"]))
            guard pending == saved, running == saved else { throw ContractError.message("Running backend settings do not match the saved settings.") }
            saved = pending; effective = running
            notice = "Settings active. Connected MCP clients may need a new session or tool-catalog refresh."
        } catch {
            self.error = persisted
                ? "Settings are saved, but restart was not verified. Retry Save and restart connection, or Start in General settings. Your connections, credentials and permissions are retained. \(error.localizedDescription)"
                : "Could not verify that settings were saved. The connection was not restarted. Reload settings to check the saved values, then retry. \(error.localizedDescription)"
        }
    }
}
