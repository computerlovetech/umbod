use serde_json::json;
use umbod_gateway::{Config, Runtime, http_api};
#[tokio::test]
async fn management_is_isolated_and_gateway_enforces_identity() {
    let mut config = Config::default();
    // Existing installations may still authenticate using an old per-client token.
    config.clients.push(umbod_gateway::Client {
        id: "legacy".into(),
        name: "Legacy".into(),
        token_hash: umbod_gateway::token_hash("fixture-client-token"),
    });
    let runtime = Runtime::memory(config);
    let running = http_api::start(runtime, "test-admin-secret".into())
        .await
        .unwrap();
    let http = reqwest::Client::new();
    let manage = format!("http://{}/manage", running.management);
    assert_eq!(
        http.post(&manage)
            .json(&json!({"action":"status"}))
            .send()
            .await
            .unwrap()
            .status(),
        401
    );
    assert_eq!(
        http.post(&manage)
            .bearer_auth("test-admin-secret")
            .header("Origin", "https://evil.example")
            .json(&json!({"action":"status"}))
            .send()
            .await
            .unwrap()
            .status(),
        403
    );
    assert_eq!(
        http.post(&manage)
            .bearer_auth("test-admin-secret")
            .header("Host", "evil.example")
            .json(&json!({"action":"status"}))
            .send()
            .await
            .unwrap()
            .status(),
        403
    );
    let token = "fixture-client-token";
    let endpoint = format!("http://{}/mcp", running.gateway);
    assert_eq!(
        http.post(&endpoint)
            .json(&json!({}))
            .send()
            .await
            .unwrap()
            .status(),
        401
    );
    assert_eq!(
        http.post(&manage)
            .bearer_auth(token)
            .json(&json!({"action":"status"}))
            .send()
            .await
            .unwrap()
            .status(),
        401
    );
    use rmcp::{
        ServiceExt,
        transport::{
            StreamableHttpClientTransport,
            streamable_http_client::StreamableHttpClientTransportConfig,
        },
    };
    let transport = StreamableHttpClientTransport::with_client(
        http,
        StreamableHttpClientTransportConfig::with_uri(endpoint).auth_header(token),
    );
    let client = ().serve(transport).await.unwrap();
    assert!(client.list_all_tools().await.unwrap().is_empty());
    assert!(
        client
            .call_tool(serde_json::from_value(json!({"name":"unknown", "arguments":{}})).unwrap())
            .await
            .is_err()
    );
    client.cancel().await.unwrap();
    running.stop.cancel();
}
#[tokio::test]
async fn server_credentials_cannot_reference_downstream_identity() {
    let runtime = Runtime::memory(Config::default());
    let result=http_api::action(&runtime,json!({"action":"server_save","server":{"id":"bad","name":"Bad reference","transport":"http","url":"https://example.com/mcp","headers":{"Authorization":"client:alice"}}})).await;
    assert!(
        result.is_err(),
        "Upstream credential references must be restricted to their own namespace"
    );
}
#[tokio::test]
async fn editing_server_invalidates_pending_oauth_and_prior_grants() {
    let runtime = Runtime::memory(Config::default());
    let server =
        json!({"id":"edited","name":"Before","transport":"http","url":"https://example.com/mcp"});
    http_api::action(&runtime, json!({"action":"server_save","server":server}))
        .await
        .unwrap();
    {
        let mut inner = runtime.inner.lock().await;
        inner
            .oauth_pending
            .insert("edited".into(), "pending-generation".into());
    }
    runtime.grant("edited.echo", true).await.unwrap();
    http_api::action(&runtime,json!({"action":"server_save","server":{"id":"edited","name":"After","transport":"http","url":"https://different.example/mcp","oauth":true}})).await.unwrap();
    let inner = runtime.inner.lock().await;
    assert!(!inner.oauth_pending.contains_key("edited"));
    assert!(!inner.config.servers[0].oauth);
    assert!(!inner.config.allowed("edited.echo"));
}
#[tokio::test]
async fn gateway_port_survives_restart_and_conflicts_do_not_silently_move_it() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("config.json");
    let runtime = Runtime::persistent(path.clone()).unwrap();
    let running = http_api::start(runtime, "fixture-admin".into())
        .await
        .unwrap();
    let port = running.gateway.port();
    running.stop.cancel();
    tokio::time::sleep(std::time::Duration::from_millis(100)).await;
    let restored = Runtime::persistent(path.clone()).unwrap();
    let again = http_api::start(restored, "fixture-admin".into())
        .await
        .unwrap();
    assert_eq!(
        again.gateway.port(),
        port,
        "persist the chosen port instead of silently switching"
    );
    again.stop.cancel();
    tokio::time::sleep(std::time::Duration::from_millis(100)).await;
    let blocker = tokio::net::TcpListener::bind((std::net::Ipv4Addr::LOCALHOST, port))
        .await
        .unwrap();
    let conflict =
        http_api::start(Runtime::persistent(path).unwrap(), "fixture-admin".into()).await;
    assert!(conflict.is_err());
    drop(blocker);
}
#[tokio::test]
async fn saving_new_non_oauth_server_does_not_delete_unowned_vault_entry() {
    let id = uuid::Uuid::new_v4().simple().to_string();
    let reference = format!("upstream:oauth:{id}");
    umbod_gateway::secret_set(&reference, "labeled-fixture-existing-entry").unwrap();
    let runtime = Runtime::memory(Config::default());
    http_api::action(&runtime,json!({"action":"server_save","server":{"id":id,"name":"Fixture new server","transport":"http","url":"https://example.com/mcp"}})).await.unwrap();
    let preserved = umbod_gateway::secret_get(&reference).is_ok();
    umbod_gateway::secret_delete(&reference).unwrap();
    assert!(
        preserved,
        "a new config must not delete an existing vault entry it does not own"
    );
}
