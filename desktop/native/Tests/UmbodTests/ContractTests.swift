import Foundation
import UmbodCore
@main struct ContractTests {
    @MainActor static func main() async throws {
        precondition(ActivationState([:]).stage == .choose)
        let journey: [String: Any] = ["client":"c", "server":"s", "configured":false, "activated":false]
        precondition(ActivationState(["activation":journey]).stage == .connect)
        precondition(ActivationState(["activation":journey,"statuses":["s":"Connected"]]).stage == .approve)
        precondition(ActivationState(["activation":journey,"statuses":["s":"Connected"],"allowed_tools":["s.search_issues"]]).stage == .configure)
        precondition(ActivationState(["activation":["client":"c","server":"s","configured":true,"activated":false],"statuses":["s":"Connected"],"allowed_tools":["s.search_issues"]]).stage == .tryPrompt)
        precondition(ActivationState(["activation":["client":"c","server":"s","configured":true,"activated":true]]).stage == .activated)
        print("PASS: native activation stages depend on backend facts, never copied prompt")
        let isolated = URL(fileURLWithPath:"/private/tmp/umbod-fixture")
        precondition(ClientConfiguration.destination(home:URL(fileURLWithPath:"/Users/not-real"),dataDirectory:isolated).path == "/private/tmp/umbod-fixture/fixture-claude.json")
        var server = ServerDraft()
        server.name = "Local fixture"
        server.command = "/usr/bin/python3"
        server.arguments = "/tmp/fixture.py\n--flag"
        let value = try server.payload()
        precondition(value["transport"] as? String == "stdio")
        precondition(value["args"] as? [String] == ["/tmp/fixture.py", "--flag"])
        precondition(value["oauth"] as? Bool == false)
        let config = try ClientConfiguration.bridge(bundlePath: "/Applications/Umbod.app")
        precondition(config.contains("/Applications/Umbod.app/Contents/MacOS/umbod-gateway"))
        precondition(!config.contains("token"))
        precondition(!config.contains("alice"))
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let backend = Backend()
        let executable = URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent("target/debug/umbod-gateway")
        try await backend.start(executable: executable, directory: directory)
        let status = try await backend.request(["action": "status"])
        precondition(status["servers"] is [Any])
        precondition(backend.gateway.hasPrefix("127.0.0.1:"))
        let conflictDirectory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: conflictDirectory, withIntermediateDirectories: true)
        let port = Int(backend.gateway.split(separator: ":").last!)!
        try JSONSerialization.data(withJSONObject:["gateway_port":port]).write(to:conflictDirectory.appendingPathComponent("config.json"))
        let conflict = Backend()
        var portError = false
        do { try await conflict.start(executable:executable,directory:conflictDirectory) }
        catch { portError = error.localizedDescription.contains("port") }
        conflict.stop()
        try? FileManager.default.removeItem(at:conflictDirectory)
        precondition(portError, "Native startup must explain the saved-port conflict")
        print("PASS: native startup exposes actionable saved-port conflict")
        server.arguments = FileManager.default.currentDirectoryPath + "/scripts/fixture_stdio.py"
        let saved = try await backend.request(["action": "server_save", "server": try server.payload()])
        let savedServer = saved["server"] as! [String: Any]
        _ = try await backend.request(["action": "connect", "id": savedServer["id"]!])
        let connected = try await backend.request(["action": "status"])
        precondition((connected["tools"] as? [Any])?.count == 2)
        let connection = try await backend.request(["action": "connection_setup"])
        let connectionID = connection["id"] as! String
        let again = try await backend.request(["action": "connection_setup"])
        precondition(again["id"] as? String == connectionID)
        let toolName = ((connected["tools"] as! [[String: Any]])[0])["name"] as! String
        _ = try await backend.request(["action": "grant", "tool": toolName, "allow": true])
        let allowed = try await backend.request(["action": "status"])
        precondition((allowed["allowed_tools"] as? [String])?.contains(toolName) == true)
        _ = try await backend.request(["action": "grant", "tool": toolName, "allow": false])
        _ = try await backend.request(["action": "client_remove", "id": connectionID])
        print("PASS: connector save → real stdio discovery → shared connection → global permission → revocation")
        backend.stop()
        precondition(!backend.isRunning)
        try? FileManager.default.removeItem(at: directory)
        print("PASS: native backend launch, authenticated API contract, owner shutdown")
        let devConfig = try ClientConfiguration.bridge(bundlePath: "/tmp/Umbod Dev.app", environment: .dev, executable: AppEnvironment.dev.gatewayExecutable)
        precondition(devConfig.contains("umbod-dev"))
        precondition(devConfig.contains("--profile"))
        precondition(AppEnvironment.dev.dataDirectory != AppEnvironment.release.dataDirectory)
        let persistentDirectory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let firstUI = Backend()
        try await firstUI.start(executable: executable, directory: persistentDirectory, persistent: true, environment: .dev)
        let persistentPID = firstUI.processID
        let persistentEndpoint = firstUI.gateway
        firstUI.stop() // UI detaches; the gateway remains available.
        let secondUI = Backend()
        try await secondUI.start(executable: executable, directory: persistentDirectory, persistent: true, environment: .dev)
        precondition(secondUI.processID == persistentPID)
        precondition(secondUI.gateway == persistentEndpoint)
        precondition(!secondUI.updateAvailable)
        _ = try await secondUI.request(["action":"status"])
        try await secondUI.shutdown()
        try await secondUI.start(executable: executable, directory: persistentDirectory, persistent: true, environment: .dev)
        precondition(secondUI.processID != persistentPID)
        precondition(secondUI.gateway == persistentEndpoint)
        try await secondUI.shutdown()
        try FileManager.default.removeItem(at: persistentDirectory)
        print("PASS: persistent gateway survives UI detach, reattaches to same PID, restarts on same endpoint")
        print("PASS: Swift server contract and secret-free bridge configuration")
    }
}
