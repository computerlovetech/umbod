mod support;
use rmcp::{ServiceExt, transport::TokioChildProcess};
use serde_json::{Value, json};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt};
#[tokio::test]
async fn packaged_stdio_bridge_reads_keychain_and_obeys_gateway_revocation() {
    let dir = tempfile::tempdir().unwrap();
    let binary = std::env::var("UMBOD_TEST_BINARY")
        .unwrap_or_else(|_| env!("CARGO_BIN_EXE_umbod-gateway").into());
    let mut owner = tokio::process::Command::new(&binary)
        .arg("serve")
        .arg("--persistent")
        .arg("--data-dir")
        .arg(dir.path())
        .kill_on_drop(true)
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null())
        .spawn()
        .unwrap();
    let mut input = owner.stdin.take().unwrap();
    input
        .write_all(b"{\"admin_token\":\"fixture-bridge-owner-token\"}\n")
        .await
        .unwrap();
    let ready: Value = serde_json::from_str(
        &tokio::io::BufReader::new(owner.stdout.take().unwrap())
            .lines()
            .next_line()
            .await
            .unwrap()
            .unwrap(),
    )
    .unwrap();
    let manage = format!("http://{}/manage", ready["management"].as_str().unwrap());
    let http = reqwest::Client::new();
    async fn action(http: &reqwest::Client, url: &str, body: Value) -> Value {
        let response = http
            .post(url)
            .bearer_auth("fixture-bridge-owner-token")
            .json(&body)
            .send()
            .await
            .unwrap();
        assert!(response.status().is_success());
        response.json().await.unwrap()
    }
    action(&http,&manage,json!({"action":"server_save","server":{"id":"local","name":"Bridge fixture","transport":"stdio","command":support::python(),"args":[format!("{}/scripts/fixture_stdio.py",env!("CARGO_MANIFEST_DIR")),"--pid-file",dir.path().join("fixture.pid")]}})).await;
    action(&http, &manage, json!({"action":"connect","id":"local"})).await;
    let created = action(&http, &manage, json!({"action":"connection_setup"})).await;
    let id = created["id"].as_str().unwrap();
    action(
        &http,
        &manage,
        json!({"action":"grant","tool":"local.echo","allow":true}),
    )
    .await;
    let mut command = tokio::process::Command::new(&binary);
    command
        .arg("bridge")
        .arg("--data-dir")
        .arg(dir.path())
        .kill_on_drop(true);
    let transport = TokioChildProcess::builder(command)
        .stderr(std::process::Stdio::null())
        .spawn()
        .unwrap()
        .0;
    let client =
        tokio::time::timeout(std::time::Duration::from_secs(15), ().serve(transport)).await;
    if !matches!(&client, Ok(Ok(_))) {
        action(&http, &manage, json!({"action":"client_remove","id":id})).await;
    }
    let client = client
        .expect("bridge handshake timeout")
        .expect("bridge handshake failed");
    let mut legacy_command = tokio::process::Command::new(&binary);
    legacy_command
        .arg("bridge")
        .arg(id)
        .arg("--data-dir")
        .arg(dir.path())
        .kill_on_drop(true);
    let legacy_transport = TokioChildProcess::builder(legacy_command)
        .stderr(std::process::Stdio::null())
        .spawn()
        .unwrap()
        .0;
    let legacy = ().serve(legacy_transport).await.unwrap();
    assert_eq!(legacy.list_all_tools().await.unwrap().len(), 1);
    assert_eq!(client.list_all_tools().await.unwrap().len(), 1);
    let call = || {
        serde_json::from_value(json!({"name":"local.echo","arguments":{"text":"bridge works"}}))
            .unwrap()
    };
    assert_eq!(
        serde_json::to_value(client.call_tool(call()).await.unwrap()).unwrap()["content"][0]["text"],
        "bridge works"
    );
    action(
        &http,
        &manage,
        json!({"action":"grant","tool":"local.echo","allow":false}),
    )
    .await;
    assert!(client.list_all_tools().await.unwrap().is_empty());
    assert!(legacy.list_all_tools().await.unwrap().is_empty());
    assert!(legacy.call_tool(call()).await.is_err());
    legacy.cancel().await.unwrap();
    assert!(client.call_tool(call()).await.is_err());
    client.cancel().await.unwrap();
    action(&http, &manage, json!({"action":"client_remove","id":id})).await;
    #[cfg(unix)]
    let fixture_pid = std::fs::read_to_string(dir.path().join("fixture.pid")).unwrap();
    drop(input);
    action(&http, &manage, json!({"action":"shutdown"})).await;
    assert!(
        tokio::time::timeout(std::time::Duration::from_secs(8), owner.wait())
            .await
            .unwrap()
            .unwrap()
            .success()
    );
    #[cfg(unix)]
    assert!(
        !std::process::Command::new("/bin/kill")
            .arg("-0")
            .arg(fixture_pid.trim())
            .stderr(std::process::Stdio::null())
            .status()
            .unwrap()
            .success(),
        "owned fixture process survived shutdown"
    );
}
