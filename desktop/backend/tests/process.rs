use std::io::{BufRead, BufReader, Write};
use std::process::{Command, Stdio};
#[test]
fn backend_reports_dynamic_ports_and_stops_on_owner_eof() {
    let directory = tempfile::tempdir().unwrap();
    let mut child = Command::new(env!("CARGO_BIN_EXE_umbod-gateway"))
        .arg("serve")
        .arg("--data-dir")
        .arg(directory.path())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    let mut input = child.stdin.take().unwrap();
    writeln!(
        input,
        "{}",
        serde_json::json!({"admin_token":"test-owner-token"})
    )
    .unwrap();
    let mut line = String::new();
    BufReader::new(child.stdout.take().unwrap())
        .read_line(&mut line)
        .unwrap();
    let ready: serde_json::Value = serde_json::from_str(&line).expect("backend readiness JSON");
    assert_ne!(ready["gateway"], ready["management"]);
    assert!(ready["gateway"].as_str().unwrap().starts_with("127.0.0.1:"));
    assert!(!line.contains("test-owner-token"));
    drop(input);
    for _ in 0..50 {
        if let Some(status) = child.try_wait().unwrap() {
            assert!(status.success());
            return;
        }
        std::thread::sleep(std::time::Duration::from_millis(100));
    }
    let _ = child.kill();
    panic!("backend failed to stop on parent pipe EOF");
}
#[test]
fn second_owner_cannot_overwrite_runtime_record() {
    let directory = tempfile::tempdir().unwrap();
    fn launch(path: &std::path::Path) -> (std::process::Child, std::process::ChildStdin) {
        let mut child = Command::new(env!("CARGO_BIN_EXE_umbod-gateway"))
            .arg("serve")
            .arg("--data-dir")
            .arg(path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        let mut input = child.stdin.take().unwrap();
        writeln!(
            input,
            "{}",
            serde_json::json!({"admin_token":"test-owner-token"})
        )
        .unwrap();
        (child, input)
    }
    let (mut first, input) = launch(directory.path());
    let mut line = String::new();
    BufReader::new(first.stdout.take().unwrap())
        .read_line(&mut line)
        .unwrap();
    let record = std::fs::read(directory.path().join("runtime.json")).unwrap();
    let (mut second, second_input) = launch(directory.path());
    std::thread::sleep(std::time::Duration::from_millis(250));
    let rejected = second.try_wait().unwrap().is_some_and(|s| !s.success());
    let unchanged = std::fs::read(directory.path().join("runtime.json")).unwrap() == record;
    drop(second_input);
    let _ = second.wait();
    drop(input);
    let _ = first.wait();
    assert!(rejected, "Second owner must fail explicitly");
    assert!(unchanged, "Second owner overwrote runtime record");
}

#[tokio::test]
async fn persistent_profiles_survive_ui_exit_and_restart_independently() {
    use serde_json::{Value, json};
    #[cfg(unix)]
    use std::os::unix::fs::PermissionsExt;
    async fn launch(
        path: &std::path::Path,
        profile: &str,
        token: &str,
    ) -> (tokio::process::Child, Value) {
        use tokio::io::{AsyncBufReadExt, AsyncWriteExt};
        let mut child = tokio::process::Command::new(env!("CARGO_BIN_EXE_umbod-gateway"))
            .args(["serve", "--persistent", "--profile", profile, "--data-dir"])
            .arg(path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .kill_on_drop(true)
            .spawn()
            .unwrap();
        let mut input = child.stdin.take().unwrap();
        input
            .write_all(format!("{}\n", json!({"admin_token":token})).as_bytes())
            .await
            .unwrap();
        let line = tokio::io::BufReader::new(child.stdout.take().unwrap())
            .lines()
            .next_line()
            .await
            .unwrap()
            .unwrap();
        assert!(!line.contains(token));
        drop(input); // Exactly what happens when the UI exits.
        (child, serde_json::from_str(&line).unwrap())
    }
    async fn action(ready: &Value, token: &str, body: Value) -> reqwest::Response {
        reqwest::Client::new()
            .post(format!(
                "http://{}/manage",
                ready["management"].as_str().unwrap()
            ))
            .bearer_auth(token)
            .json(&body)
            .send()
            .await
            .unwrap()
    }
    let release_dir = tempfile::tempdir().unwrap();
    let dev_dir = tempfile::tempdir().unwrap();
    let release_token = "fixture-persistent-release";
    let dev_token = "fixture-persistent-development";
    let (mut release, release_ready) = launch(release_dir.path(), "release", release_token).await;
    let (mut dev, dev_ready) = launch(dev_dir.path(), "dev", dev_token).await;
    assert_ne!(release_ready["gateway"], dev_ready["gateway"]);
    for (dir, profile, token) in [
        (&release_dir, "release", release_token),
        (&dev_dir, "dev", dev_token),
    ] {
        let path = dir.path().join("runtime.json");
        #[cfg(unix)]
        assert_eq!(
            std::fs::metadata(&path).unwrap().permissions().mode() & 0o777,
            0o600
        );
        let record: Value = serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
        assert_eq!(record["profile"], profile);
        assert_eq!(record["admin_token"], token);
    }
    // Check credential namespace selection without crossing macOS executable ACLs.
    assert_ne!(
        umbod_gateway::profile::Profile::Release.service(),
        umbod_gateway::profile::Profile::Dev.service()
    );
    assert!(
        action(&dev_ready, release_token, json!({"action":"shutdown"}))
            .await
            .status()
            .is_client_error()
    );
    assert!(
        action(&dev_ready, dev_token, json!({"action":"status"}))
            .await
            .status()
            .is_success()
    );
    assert!(
        action(&release_ready, release_token, json!({"action":"status"}))
            .await
            .status()
            .is_success()
    );
    assert!(
        action(&dev_ready, dev_token, json!({"action":"shutdown"}))
            .await
            .status()
            .is_success()
    );
    tokio::time::timeout(std::time::Duration::from_secs(8), dev.wait())
        .await
        .unwrap()
        .unwrap();
    assert!(!dev_dir.path().join("runtime.json").exists());
    let (mut restarted, restarted_ready) = launch(dev_dir.path(), "dev", dev_token).await;
    assert_eq!(dev_ready["gateway"], restarted_ready["gateway"]);
    assert!(
        action(&release_ready, release_token, json!({"action":"status"}))
            .await
            .status()
            .is_success()
    );
    for (child, ready, token) in [
        (&mut release, &release_ready, release_token),
        (&mut restarted, &restarted_ready, dev_token),
    ] {
        assert!(
            action(ready, token, json!({"action":"shutdown"}))
                .await
                .status()
                .is_success()
        );
        assert!(
            tokio::time::timeout(std::time::Duration::from_secs(8), child.wait())
                .await
                .unwrap()
                .unwrap()
                .success()
        );
    }
}
