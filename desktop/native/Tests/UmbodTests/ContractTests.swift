import Foundation
import UmbodCore
@main struct ContractTests {
    static func log(_ value: String) { FileHandle.standardOutput.write(Data((value + "\n").utf8)) }
    @MainActor static func main() async throws {
        try updateTests()
        try await connectorEditorTests()
        if CommandLine.arguments.contains("--updates-only") { return }
        precondition(ActivationState([:]).stage == .choose)
        let journey: [String: Any] = ["client":"c", "server":"s", "configured":false, "activated":false]
        precondition(ActivationState(["activation":journey]).stage == .connect)
        precondition(ActivationState(["activation":journey,"statuses":["s":"Connected"]]).stage == .approve)
        precondition(ActivationState(["activation":journey,"statuses":["s":"Connected"],"allowed_tools":["s.search_issues"]]).stage == .configure)
        precondition(ActivationState(["activation":["client":"c","server":"s","configured":true,"activated":false],"statuses":["s":"Connected"],"allowed_tools":["s.search_issues"]]).stage == .tryPrompt)
        precondition(ActivationState(["activation":["client":"c","server":"s","configured":true,"activated":true]]).stage == .activated)
        log("PASS: native activation stages depend on backend facts, never copied prompt")
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
        precondition(config.contains("/Applications/Umbod.app/Contents/MacOS/umbod-desktop"))
        precondition(!config.contains("token"))
        precondition(!config.contains("alice"))
        let embeddedIcon = ConnectorIconSource("data:image/svg+xml;base64,PHN2Zy8+")
        precondition(embeddedIcon == .embedded(Data("<svg/>".utf8)))
        precondition(ConnectorIconSource("data:text/plain;base64,dGVzdA==") == nil)
        precondition(ConnectorIconSource("javascript:alert(1)") == nil)
        precondition(ConnectorIconSource("https://example.com/icon.svg") == .remote(URL(string: "https://example.com/icon.svg")!))
        log("PASS: connector icon sources accept HTTPS and embedded images only")
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("umbod-test-" + UUID().uuidString)
        let backend = Backend()
        let desktop = ProcessInfo.processInfo.environment["UMBOD_TEST_RESOURCES"].map { URL(fileURLWithPath: $0) } ?? URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let app = ProcessInfo.processInfo.environment["UMBOD_TEST_APP"].map { URL(fileURLWithPath: $0) } ?? desktop.appendingPathComponent("dist/Umbod Dev.app")
        let executable = app.appendingPathComponent("Contents/MacOS/umbod-desktop")
        let profile = try String(contentsOf: app.appendingPathComponent("Contents/Resources/umbod-profile"), encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines)
        let environment: AppEnvironment = profile == "release" ? .release : .dev
        try await backend.start(executable: executable, directory: directory, environment: environment, testCredentials: true)
        let status = try await backend.request(["action": "status"])
        precondition(status["servers"] is [Any])
        precondition(backend.gateway.hasPrefix("127.0.0.1:"))
        let conflictDirectory = FileManager.default.temporaryDirectory.appendingPathComponent("umbod-test-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: conflictDirectory, withIntermediateDirectories: true)
        let port = Int(backend.gateway.split(separator: ":").last!)!
        try JSONSerialization.data(withJSONObject:["port":port]).write(to:conflictDirectory.appendingPathComponent("python-endpoint.json"))
        let conflict = Backend()
        var portError = false
        do { try await conflict.start(executable:executable,directory:conflictDirectory, environment:environment, testCredentials: true) }
        catch { portError = error.localizedDescription.contains("port") }
        conflict.stop()
        try? FileManager.default.removeItem(at:conflictDirectory)
        precondition(portError, "Native startup must explain the saved-port conflict")
        log("PASS: native startup exposes actionable saved-port conflict")
        server.command = executable.deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("Resources/python/bin/python3").path
        server.arguments = "-B\n" + desktop.appendingPathComponent("scripts/fixture_stdio.py").path
        let editor = ConnectorEditor(draft: server)
        editor.credentialName = "UMBOD_FIXTURE_SECRET"
        editor.credential = "fixture-only"
        editor.draft.arguments += "\n--require-env"
        try await editor.save { try await backend.request($0) }
        let connected = try await backend.request(["action": "status"])
        precondition((connected["tools"] as? [Any])?.count == 2)
        let connection = try await backend.request(["action": "connection_setup"])
        let connectionID = connection["token"] as! String
        let again = try await backend.request(["action": "connection_setup"])
        precondition(again["token"] as? String == connectionID)
        let toolName = (connected["tools"] as! [[String: Any]]).first { ($0["name"] as? String ?? "").hasSuffix(".echo") }!["name"] as! String
        _ = try await backend.request(["action": "grant", "tool": toolName, "allow": true])
        let allowed = try await backend.request(["action": "status"])
        precondition((allowed["allowed_tools"] as? [String])?.contains(toolName) == true)
        var renamed = (allowed["servers"] as! [[String: Any]]).first!
        renamed["name"] = "Renamed fixture"
        _ = try await backend.request(["action": "server_save", "server": try ServerDraft(renamed).payload()])
        let afterRename = try await backend.request(["action": "status"])
        precondition((afterRename["allowed_tools"] as? [String])?.contains(toolName) == true, "Renaming must preserve tool permissions")
        let agent = Process()
        agent.executableURL = executable.deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("Resources/python/bin/python3")
        agent.arguments = ["-I", "-B", "-c", """
        import asyncio, sys
        from fastmcp import Client
        from fastmcp.client.transports import StdioTransport
        async def main():
            async with Client(StdioTransport(command=sys.argv[1], args=['bridge', 'legacy-fixture-id', '--profile', sys.argv[3], '--data-dir', sys.argv[2], '--test-credentials']), mode='legacy') as client:
                async with asyncio.timeout(20):
                    while not (tools := await client.list_tools()):
                        await asyncio.sleep(.1)
                result = await client.call_tool(tools[0].name, {'text': 'native-python-fixture'})
                assert 'native-python-fixture' in str(result)
        asyncio.run(main())
        """, executable.path, directory.path, profile]
        agent.standardOutput = FileHandle.nullDevice
        try agent.run(); agent.waitUntilExit()
        precondition(agent.terminationStatus == 0, "Packaged agent bridge must call the enabled fixture tool")
        let used = try await backend.request(["action": "status"])
        let usage = used["tool_usage"] as! [String: [String: Int]]
        precondition(usage[toolName]?["succeeded"] == 1)
        log("PASS: packaged Python agent bridge calls enabled stdio tool and records usage")
        _ = try await backend.request(["action": "grant", "tool": toolName, "allow": false])
        log("PASS: connector save → real stdio discovery → shared connection → global permission → revocation")
        backend.stop()
        precondition(!backend.isRunning)
        log("PASS: native backend launch, authenticated API contract, owner shutdown")
        let devConfig = try ClientConfiguration.bridge(bundlePath: "/tmp/Umbod Dev.app", environment: .dev, executable: AppEnvironment.dev.gatewayExecutable)
        precondition(devConfig.contains("umbod-dev"))
        precondition(devConfig.contains("--profile"))
        precondition(AppEnvironment.dev.dataDirectory != AppEnvironment.release.dataDirectory)
        let persistentDirectory = directory
        let firstUI = Backend()
        try await firstUI.start(executable: executable, directory: persistentDirectory, persistent: true, environment: environment, testCredentials: true)
        _ = try await firstUI.request(["action": "grant", "tool": toolName, "allow": true])
        let persistentPID = firstUI.processID
        let persistentEndpoint = firstUI.gateway
        firstUI.stop() // UI detaches; the gateway remains available.
        let secondUI = Backend()
        try await secondUI.start(executable: executable, directory: persistentDirectory, persistent: true, environment: environment, testCredentials: true)
        precondition(secondUI.processID == persistentPID)
        precondition(secondUI.gateway == persistentEndpoint)
        precondition(!secondUI.updateAvailable)
        _ = try await secondUI.request(["action":"status"])
        try await secondUI.shutdown()
        try await secondUI.start(executable: executable, directory: persistentDirectory, persistent: true, environment: environment, testCredentials: true)
        precondition(secondUI.processID != persistentPID)
        precondition(secondUI.gateway == persistentEndpoint)
        let restored = try await secondUI.request(["action": "status"])
        precondition((restored["allowed_tools"] as? [String])?.contains(toolName) == true)
        let restoredAgent = Process()
        restoredAgent.executableURL = agent.executableURL
        restoredAgent.arguments = agent.arguments
        restoredAgent.standardOutput = FileHandle.nullDevice
        try restoredAgent.run(); restoredAgent.waitUntilExit()
        precondition(restoredAgent.terminationStatus == 0, "Persisted permissions and transport must survive restart")
        let movedDirectory = persistentDirectory.deletingLastPathComponent().appendingPathComponent("umbod-test-moved-" + UUID().uuidString)
        try FileManager.default.moveItem(at: persistentDirectory, to: movedDirectory)
        try FileManager.default.createDirectory(at: persistentDirectory, withIntermediateDirectories: true)
        let replacementRecord = persistentDirectory.appendingPathComponent("python-runtime.json")
        let replacement = Data("{\"pid\":123}".utf8)
        try replacement.write(to: replacementRecord)
        for _ in 0..<300 {
            if !secondUI.isRunning { break }
            try await Task.sleep(for: .milliseconds(50))
        }
        precondition(!secondUI.isRunning, "A gateway must stop when its profile is moved")
        let retainedRecord = try Data(contentsOf: replacementRecord)
        precondition(retainedRecord == replacement, "An orphan must not remove a replacement host's record")
        secondUI.stop()
        try FileManager.default.removeItem(at: movedDirectory)
        try FileManager.default.removeItem(at: persistentDirectory)
        log("PASS: moved profile stops its gateway and preserves replacement runtime metadata")
        log("PASS: persistent gateway survives UI detach, reattaches to same PID, restarts on same endpoint")
        log("PASS: Swift server contract and secret-free bridge configuration")
    }
}
