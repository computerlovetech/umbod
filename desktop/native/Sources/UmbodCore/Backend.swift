import Foundation
import Darwin
import CryptoKit
@MainActor public final class Backend {
    private var process: Process?
    private var owner: Pipe?
    private var token = ""
    private var persistent = false
    private var runtimeFile: URL?
    private var attachedPID: Int32 = 0
    public private(set) var updateAvailable = false
    public private(set) var management = ""
    public private(set) var gateway = ""
    public var processID: Int32 { process?.processIdentifier ?? attachedPID }
    public var isRunning: Bool { process?.isRunning ?? (attachedPID > 0 && kill(attachedPID, 0) == 0) }
    public init() {}
    public func start(executable: URL? = nil, directory: URL? = nil, persistent: Bool = false, environment: AppEnvironment = .current) async throws {
        guard !isRunning else { return }
        stop()
        var executable = executable ?? Bundle.main.bundleURL.appendingPathComponent("Contents/MacOS/umbod-gateway")
        guard FileManager.default.isExecutableFile(atPath: executable.path) else { throw ContractError.message("Bundled gateway is missing. Reinstall Umbod.app.") }
        self.persistent = persistent
        let directory = directory ?? environment.dataDirectory
        runtimeFile = directory.appendingPathComponent("runtime.json")
        if persistent {
            if let data = try? Data(contentsOf: runtimeFile!),
               let record = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               record["profile"] as? String == environment.rawValue,
               let savedToken = record["admin_token"] as? String,
               let pid = record["pid"] as? Int32,
               let address = record["management"] as? String,
               let endpoint = record["gateway"] as? String,
               address.hasPrefix("127.0.0.1:"), endpoint.hasPrefix("127.0.0.1:") {
                attachedPID = pid; token = savedToken; management = address; gateway = endpoint
                do {
                    let health = try await request(["action": "health"], timeout: 2)
                    guard health["profile"] as? String == environment.rawValue, health["pid"] as? Int32 == pid else {
                        throw ContractError.message("Gateway identity does not match this app.")
                    }
                    let installed = directory.appendingPathComponent("bin/umbod-gateway")
                    updateAvailable = (try? SHA256.hash(data: Data(contentsOf: installed))) != (try? SHA256.hash(data: Data(contentsOf: executable)))
                    return
                }
                catch { attachedPID = 0; token = ""; management = ""; gateway = "" }
            }
            // Stable executable location: rebuilding the UI cannot replace a running gateway.
            let bin = directory.appendingPathComponent("bin")
            try FileManager.default.createDirectory(at: bin, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
            let installed = bin.appendingPathComponent("umbod-gateway")
            let staging = bin.appendingPathComponent("gateway-\(UUID().uuidString)")
            try FileManager.default.copyItem(at: executable, to: staging)
            // rename is atomic and leaves any running executable inode intact.
            guard rename(staging.path, installed.path) == 0 else {
                try? FileManager.default.removeItem(at: staging)
                throw ContractError.message("Could not install the gateway executable.")
            }
            try Data((environment.rawValue + "\n").utf8).write(to: bin.appendingPathComponent("umbod-profile"), options: .atomic)
            executable = installed
        }
        let child = Process(); child.executableURL = executable
        child.arguments = ["serve", "--data-dir", directory.path, "--profile", environment.rawValue]
        if persistent { child.arguments!.append("--persistent") }
        let input = Pipe(), output = Pipe()
        child.standardInput = input; child.standardOutput = output; child.standardError = FileHandle.nullDevice
        token = UUID().uuidString + UUID().uuidString
        try child.run(); process = child; owner = input
        let startup = try JSONSerialization.data(withJSONObject: ["admin_token": token]) + Data([10])
        try input.fileHandleForWriting.write(contentsOf: startup)
        let timeout = Task { @MainActor in
            try? await Task.sleep(for: .seconds(15))
            if !Task.isCancelled && self.management.isEmpty { child.terminate(); self.stop() }
        }
        let data = await Task.detached { output.fileHandleForReading.availableData }.value
        timeout.cancel()
        let startupResult = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        if let message = startupResult?["error"] as? String { if child.isRunning { child.terminate() }; stop(); throw ContractError.message(message) }
        guard let ready = startupResult,
              let management = ready["management"] as? String, let gateway = ready["gateway"] as? String,
              management.hasPrefix("127.0.0.1:"), gateway.hasPrefix("127.0.0.1:") else {
            if child.isRunning { child.terminate() }; stop(); throw ContractError.message("Gateway could not start. Check Keychain access and configuration, then retry.")
        }
        self.management = management; self.gateway = gateway; updateAvailable = false
    }
    public func request(_ body: [String: Any], timeout: TimeInterval = 45) async throws -> [String: Any] {
        guard isRunning, let url = URL(string: "http://\(management)/manage") else { throw ContractError.message("Gateway stopped. Restart it in Settings.") }
        var request = URLRequest(url: url); request.httpMethod = "POST"; request.timeoutInterval = timeout
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let value = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { throw ContractError.message("Invalid gateway response") }
        guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw ContractError.message(value["error"] as? String ?? "Gateway request failed") }
        return value
    }
    /// Explicitly stop this environment's gateway; never signal a PID from disk.
    public func shutdown() async throws {
        guard isRunning else { stop(); return }
        if !persistent { stop(); return }
        _ = try await request(["action": "shutdown"], timeout: 5)
        for _ in 0..<100 {
            if let runtimeFile, !FileManager.default.fileExists(atPath: runtimeFile.path) {
                stop(); return
            }
            try await Task.sleep(for: .milliseconds(50))
        }
        throw ContractError.message("Gateway is still shutting down. Wait a moment before restarting.")
    }
    /// Detach from a persistent gateway. Owned test processes still stop with the UI.
    public func stop() {
        try? owner?.fileHandleForWriting.close(); owner = nil
        if let process, !persistent {
            let deadline = Date().addingTimeInterval(4)
            while process.isRunning && Date() < deadline { Thread.sleep(forTimeInterval: 0.05) }
            if process.isRunning { process.terminate() }
        }
        process = nil; attachedPID = 0; management = ""; gateway = ""; token = ""
    }
}
