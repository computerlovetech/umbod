use umbod_gateway::platform;
#[test]
fn private_replace_and_owner_lock() {
    let dir = tempfile::tempdir().unwrap();
    let root = dir.path().join("private");
    platform::private_dir(&root).unwrap();
    let path = root.join("secret.json");
    platform::atomic_write(&path, b"first").unwrap();
    platform::atomic_write(&path, b"second").unwrap();
    assert_eq!(std::fs::read(&path).unwrap(), b"second");
    let lock = platform::owner_lock(&root).unwrap();
    assert!(platform::owner_lock(&root).is_err());
    drop(lock);
    assert!(platform::owner_lock(&root).is_ok());
}
#[test]
fn refuses_non_executable_and_relative_commands() {
    let dir = tempfile::tempdir().unwrap();
    let file = dir.path().join("unsafe.cmd");
    std::fs::write(&file, "echo no").unwrap();
    assert!(platform::validate_executable(&file).is_err());
    assert!(platform::validate_executable(std::path::Path::new("relative.exe")).is_err());
}

#[tokio::test]
async fn server_save_rejects_non_executable_before_persisting() {
    let runtime = umbod_gateway::Runtime::memory(Default::default());
    let directory = tempfile::tempdir().unwrap();
    let command = directory.path().join("wrapper.cmd");
    std::fs::write(&command, b"echo unsafe").unwrap();
    let result = umbod_gateway::http_api::action(&runtime, serde_json::json!({"action":"server_save", "server":{"name":"Invalid executable", "transport":"stdio", "command":command}})).await;
    assert!(result.is_err());
    assert!(runtime.inner.lock().await.config.servers.is_empty());
}

#[cfg(windows)]
#[test]
fn windows_private_objects_have_protected_current_user_dacl() {
    let dir = tempfile::tempdir().unwrap();
    let root = dir.path().join("private");
    platform::private_dir(&root).unwrap();
    let path = root.join("runtime.json");
    platform::atomic_write(&path, b"fixture capability").unwrap();
    // Read actual OS ACLs, including the runtime file and a backup outside a private parent.
    let backup = dir.path().join("backup.json");
    platform::atomic_write(&backup, b"fixture backup").unwrap();
    for item in [&root, &path, &backup] {
        // Windows PowerShell inherits PSModulePath from the pwsh CI host. Get-Acl
        // can then resolve an incompatible PowerShell 7 security module. Read the
        // real ACL through .NET Framework instead, with module loading disabled
        // so this regression cannot silently regain that dependency.
        let script = r#"
$ErrorActionPreference = 'Stop'
$PSModuleAutoLoadingPreference = 'None'
$p = $env:UMBOD_ACL_TEST
if ([System.IO.Directory]::Exists($p)) {
    $a = [System.IO.Directory]::GetAccessControl($p)
} else {
    $a = [System.IO.File]::GetAccessControl($p)
}
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$rules = $a.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier])
if (!$a.AreAccessRulesProtected) { exit 2 }
if ($rules.Count -ne 1) { exit 3 }
$r = $rules[0]
if (!$r.IdentityReference.Equals($sid)) { exit 4 }
if ($r.IsInherited) { exit 5 }
if ($r.AccessControlType -ne [System.Security.AccessControl.AccessControlType]::Allow) { exit 6 }
if ($r.FileSystemRights -ne [System.Security.AccessControl.FileSystemRights]::FullControl) { exit 7 }
"#;
        let output = std::process::Command::new("powershell.exe")
            .args(["-NoProfile", "-NonInteractive", "-Command", script])
            .env("PSModulePath", dir.path().join("no-modules"))
            .env("UMBOD_ACL_TEST", item)
            .output()
            .unwrap();
        assert!(output.status.success(), "ACL check failed: {:?}", output);
    }
}

#[cfg(windows)]
#[test]
fn windows_credential_manager_roundtrip_is_profile_isolated() {
    let reference = format!("upstream:fixture:{}", uuid::Uuid::new_v4());
    let service = "app.umbod.desktop.windows-tests";
    platform::credential_set(service, &reference, "fixture secret ✓").unwrap();
    let result = platform::credential_get(service, &reference);
    let isolated = platform::credential_get("app.umbod.desktop.windows-tests.other", &reference);
    platform::credential_delete(service, &reference).unwrap();
    assert_eq!(result.unwrap(), "fixture secret ✓");
    assert!(isolated.is_err());
    assert!(platform::credential_get(service, &reference).is_err());
}

#[test]
fn credential_targets_reject_nul_truncation_and_preserve_unicode_profiles() {
    assert!(platform::credential_target("dev", "upstream:key\0alias").is_err());
    assert!(platform::credential_target("dev\0release", "upstream:key").is_err());
    let target = platform::credential_target("app.umbod.desktop.dev", "upstream:🔑").unwrap();
    assert_eq!(target.last(), Some(&0));
    assert_eq!(
        String::from_utf16(&target[..target.len() - 1]).unwrap(),
        "app.umbod.desktop.dev:upstream:🔑"
    );
}

#[test]
fn windows_image_validation_rejects_dos_only_disguised_exe() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("fake.exe");
    let mut bytes = vec![0; 132];
    bytes[..2].copy_from_slice(b"MZ");
    bytes[60..64].copy_from_slice(&128u32.to_le_bytes());
    std::fs::write(&path, &bytes).unwrap();
    assert!(platform::validate_windows_image(&path).is_err());
    bytes[128..132].copy_from_slice(b"PE\0\0");
    std::fs::write(&path, &bytes).unwrap();
    assert!(platform::validate_windows_image(&path).is_ok());
}
