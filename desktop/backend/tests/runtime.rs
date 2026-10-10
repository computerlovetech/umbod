mod support;
use serde_json::json;
use umbod_gateway::{Config, Runtime, Server};
#[tokio::test]
async fn stdio_discovery_calls_and_live_acl() {
    let mut config = Config::default();
    config.servers.push(Server {
        id: "local".into(),
        name: "Fixture".into(),
        transport: "stdio".into(),
        command: support::python(),
        args: vec![format!(
            "{}/scripts/fixture_stdio.py",
            env!("CARGO_MANIFEST_DIR")
        )],
        ..Default::default()
    });
    let runtime = Runtime::memory(config);
    runtime.connect("local").await.unwrap();
    assert_eq!(runtime.catalog().await.len(), 2);
    assert!(runtime.list().await.is_empty());
    assert!(
        runtime
            .call("local.echo", json!({"text":"hello"}))
            .await
            .is_err()
    );
    runtime.grant("local.echo", true).await.unwrap();
    assert_eq!(runtime.list().await.len(), 1);
    let result = runtime
        .call("local.echo", json!({"text":"hello"}))
        .await
        .unwrap();
    assert_eq!(result["content"][0]["text"], "hello");
    runtime.grant("local.echo", false).await.unwrap();
    assert!(
        runtime
            .call("local.echo", json!({"text":"hello"}))
            .await
            .is_err()
    );
    runtime.shutdown().await;
}
#[tokio::test]
async fn removed_api_tools_cannot_be_created_or_called() {
    let runtime = Runtime::memory(Config::default());
    assert!(
        umbod_gateway::http_api::action(
            &runtime,
            json!({"action":"custom_save", "tool":{"id":"api.echo"}})
        )
        .await
        .is_err()
    );
    assert!(
        umbod_gateway::http_api::action(
            &runtime,
            json!({"action":"client_add", "name":"Unneeded registration"})
        )
        .await
        .is_err()
    );
    assert!(runtime.catalog().await.is_empty());
    assert!(runtime.call("api.echo", json!({})).await.is_err());
}
#[tokio::test]
async fn local_secret_is_injected_from_keychain_without_persisting_value() {
    let reference = format!("upstream:env-fixture:{}", uuid::Uuid::new_v4());
    let value = umbod_gateway::new_token();
    umbod_gateway::secret_set(&reference, &value).unwrap();
    let mut config = Config::default();
    config.servers.push(Server {
        id: "environment".into(),
        name: "Environment fixture".into(),
        transport: "stdio".into(),
        command: support::python(),
        args: vec![
            format!("{}/scripts/fixture_stdio.py", env!("CARGO_MANIFEST_DIR")),
            "--require-env".into(),
        ],
        env: std::collections::BTreeMap::from([("UMBOD_FIXTURE_SECRET".into(), reference.clone())]),
        ..Default::default()
    });
    assert!(!serde_json::to_string(&config).unwrap().contains(&value));
    let runtime = Runtime::memory(config);
    runtime.connect("environment").await.unwrap();
    assert_eq!(runtime.catalog().await.len(), 2);
    runtime.shutdown().await;
    umbod_gateway::secret_delete(&reference).unwrap();
}
