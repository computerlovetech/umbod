import Foundation
import UmbodCore

@MainActor func advancedSettingsTests() async throws {
    let model = AdvancedSettingsModel()
    let defaults = DesktopBackendSettings()
    var pending = defaults
    var running = defaults
    var calls: [String] = []
    let request: ([String: Any]) async throws -> [String: Any] = { body in
        let action = body["action"] as! String
        calls.append(action)
        if action == "settings_save" { pending = try DesktopBackendSettings(body["settings"] as! [String: Any]) }
        if action == "health" { return ["status": "ok"] }
        return ["pending": pending.payload, "effective": running.payload, "restart_required": pending != running]
    }
    try await model.load(request: request)
    precondition(model.effective == defaults && !model.hasPendingChanges)
    model.requestAdministrator(true)
    precondition(model.confirmAdministrator && !model.draft.administratorEnabled)
    model.cancelAdministrator()
    precondition(!model.confirmAdministrator && !model.draft.administratorEnabled)
    model.requestAdministrator(true)
    model.acceptAdministrator()
    model.draft.exposureMode = .flat
    precondition(model.hasPendingChanges)
    await model.saveAndRestart(request: request, stop: {
        calls.append("stop")
        precondition(model.saved == pending && model.effective == defaults)
    }, start: { calls.append("start"); running = pending })
    precondition(calls.suffix(5) == ["settings_save", "stop", "start", "health", "settings_get"])
    precondition(model.effective == pending && !model.hasPendingChanges && model.error.isEmpty)
    model.draft.exposureMode = .codemode
    precondition(model.notice.isEmpty, "A new draft must not retain the previous active-settings notice")
    await model.saveAndRestart(request: request, stop: {}, start: { throw ContractError.message("Fixture port conflict") })
    precondition(model.saved?.exposureMode == .codemode && model.effective == nil && model.hasPendingChanges)
    precondition(model.error.contains("saved") && model.error.contains("Retry") && model.error.contains("Fixture port conflict"))
    await model.saveAndRestart(request: request, stop: {}, start: { running = pending })
    precondition(model.error.isEmpty && model.effective?.exposureMode == .codemode)
    model.draft.administratorEnabled = false
    let previous = model.saved
    await model.saveAndRestart(request: { _ in throw ContractError.message("Fixture disk full") }, stop: { preconditionFailure("Must not stop after failed save") }, start: {})
    precondition(model.saved == previous && model.effective == previous && model.hasPendingChanges)
    precondition(model.error.contains("Could not verify") && model.error.contains("not restarted"))
    await model.saveAndRestart(request: { body in
        if body["action"] as? String == "health" { return ["status": "failed"] }
        return try await request(body)
    }, stop: {}, start: { running = pending })
    precondition(model.effective == nil && model.error.contains("Retry"))
    ContractTests.log("PASS: advanced settings confirmation, pending, save/stop/start/health, failed-save and restart recovery")
}
