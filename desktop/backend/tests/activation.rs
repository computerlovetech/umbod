mod support;
use serde_json::json;
use umbod_gateway::{Config, Runtime, http_api};
#[tokio::test]
async fn curated_recipe_has_exact_tools_and_no_implicit_grants() {
    let runtime = Runtime::memory(Config::default());
    let recipe = http_api::action(&runtime, json!({"action":"activation_catalog"}))
        .await
        .unwrap();
    assert_eq!(
        recipe["endpoint"],
        "https://api.githubcopilot.com/mcp/x/issues/readonly"
    );
    assert_eq!(
        recipe["tools"],
        json!(["issue_read", "list_issues", "search_issues"])
    );
    assert_eq!(recipe["auth"], "pat");
    assert!(runtime.inner.lock().await.config.allowed_tools.is_empty());
}
#[tokio::test]
async fn preset_is_atomic_exact_and_requires_discovery_and_consent() {
    use umbod_gateway::{Client, Server};
    let mut config = Config::default();
    config.clients.push(Client {
        id: "fixture".into(),
        ..Default::default()
    });
    config.servers.push(Server {
        id: "issues".into(),
        name: "Labeled GitHub MCP fixture".into(),
        transport: "stdio".into(),
        command: support::python(),
        args: vec![format!(
            "{}/scripts/fixture_issues.py",
            env!("CARGO_MANIFEST_DIR")
        )],
        ..Default::default()
    });
    config.activation = Some(umbod_gateway::activation::Journey {
        client: "fixture".into(),
        server: "issues".into(),
        fixture: true,
        ..Default::default()
    });
    let runtime = Runtime::memory(config);
    let request = json!({"action":"activation_approve","client":"fixture","server":"issues","tools":["issue_read","search_issues"],"consent":true});
    assert!(http_api::action(&runtime, request.clone()).await.is_err());
    runtime.connect("issues").await.unwrap();
    assert!(http_api::action(&runtime,json!({"action":"activation_approve","client":"fixture","server":"issues","tools":["issue_read","create_issue"],"consent":true})).await.is_err());
    assert!(runtime.list().await.is_empty());
    http_api::action(&runtime, request).await.unwrap();
    assert_eq!(runtime.list().await.len(), 2);
    assert!(
        !runtime
            .inner
            .lock()
            .await
            .config
            .allowed("issues.list_issues")
    );
    runtime.shutdown().await;
}
#[tokio::test]
async fn onboarding_resumes_without_overwriting_existing_data_or_secrets() {
    let dir = tempfile::tempdir().unwrap();
    let runtime = Runtime::persistent(dir.path().join("config.json")).unwrap();
    let started = http_api::action(
        &runtime,
        json!({"action":"activation_start","diagnostics":true}),
    )
    .await
    .unwrap();
    let again = http_api::action(
        &runtime,
        json!({"action":"activation_start","diagnostics":true}),
    )
    .await
    .unwrap();
    assert_eq!(started["client"], again["client"]);
    let status = http_api::action(&runtime, json!({"action":"status"}))
        .await
        .unwrap();
    assert_eq!(runtime.inner.lock().await.config.clients.len(), 1);
    assert_eq!(status["activation"]["activated"], false);
    assert_eq!(status["activation"]["configured"], false);
    assert_eq!(status["diagnostics"]["events"]["onboarding_start"], 1);
    let restored = Runtime::persistent(dir.path().join("config.json")).unwrap();
    assert_eq!(
        http_api::action(&restored, json!({"action":"activation_start"}))
            .await
            .unwrap()["client"],
        started["client"]
    );
    http_api::action(
        &runtime,
        json!({"action":"client_remove","id":started["client"]}),
    )
    .await
    .unwrap();
}
#[tokio::test]
async fn client_configuration_is_previewed_consented_backed_up_and_reversible() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir
        .path()
        .canonicalize()
        .unwrap()
        .join("claude_desktop_config.json");
    let original = b"{\"theme\":\"dark\",\"mcpServers\":{\"other\":{\"command\":\"untouched\"}}}";
    std::fs::write(&path, original).unwrap();
    let runtime = Runtime::persistent(dir.path().join("umbod/config.json")).unwrap();
    let journey = http_api::action(&runtime, json!({"action":"activation_start"}))
        .await
        .unwrap();
    let preview = http_api::action(
        &runtime,
        json!({"action":"client_preview","path":path,"command":env!("CARGO_BIN_EXE_umbod-gateway")}),
    )
    .await
    .unwrap();
    assert_eq!(std::fs::read(&path).unwrap(), original);
    assert!(
        !preview.to_string().contains("theme"),
        "preview must not expose unrelated client secrets"
    );
    assert!(
        http_api::action(
            &runtime,
            json!({"action":"client_apply","preview":preview["id"]})
        )
        .await
        .is_err()
    );
    let applied = http_api::action(
        &runtime,
        json!({"action":"client_apply","preview":preview["id"],"consent":true}),
    )
    .await
    .unwrap();
    let edited: serde_json::Value = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
    assert_eq!(edited["theme"], "dark");
    assert_eq!(edited["mcpServers"]["other"]["command"], "untouched");
    assert_eq!(
        std::fs::read(applied["backup"].as_str().unwrap()).unwrap(),
        original
    );
    assert_eq!(edited["mcpServers"].as_object().unwrap().len(), 2);
    http_api::action(&runtime, json!({"action":"client_undo","consent":true}))
        .await
        .unwrap();
    assert_eq!(std::fs::read(&path).unwrap(), original);
    http_api::action(
        &runtime,
        json!({"action":"client_remove","id":journey["client"]}),
    )
    .await
    .unwrap();
}
#[tokio::test]
async fn only_successful_registered_downstream_calls_activate_and_fixtures_stay_labeled() {
    use rmcp::{
        ServiceExt,
        transport::{
            StreamableHttpClientTransport,
            streamable_http_client::StreamableHttpClientTransportConfig,
        },
    };
    use umbod_gateway::{
        Client, Server,
        activation::{Diagnostics, Journey},
    };
    let mut config = Config::default();
    config.clients.push(Client {
        id: "fixture".into(),
        token_hash: umbod_gateway::token_hash("fixture-token"),
        ..Default::default()
    });
    config.servers.push(Server {
        id: "issues".into(),
        transport: "stdio".into(),
        command: support::python(),
        args: vec![format!(
            "{}/scripts/fixture_issues.py",
            env!("CARGO_MANIFEST_DIR")
        )],
        ..Default::default()
    });
    config.activation = Some(Journey {
        client: "fixture".into(),
        server: "issues".into(),
        configured: true,
        fixture: true,
        ..Default::default()
    });
    config.diagnostics = Diagnostics {
        enabled: true,
        started_at: Some(umbod_gateway::activation::now()),
        ..Default::default()
    };
    config.grant("issues.search_issues", true);
    let runtime = Runtime::memory(config);
    runtime.connect("issues").await.unwrap();
    runtime
        .call("issues.search_issues", json!({}))
        .await
        .unwrap();
    assert!(
        !runtime
            .inner
            .lock()
            .await
            .config
            .activation
            .as_ref()
            .unwrap()
            .activated
    );
    let running = http_api::start(runtime.clone(), "fixture-admin".into())
        .await
        .unwrap();
    let transport = StreamableHttpClientTransport::with_client(
        reqwest::Client::new(),
        StreamableHttpClientTransportConfig::with_uri(format!("http://{}/mcp", running.gateway))
            .auth_header("fixture-token"),
    );
    let client = ().serve(transport).await.unwrap();
    client.list_all_tools().await.unwrap();
    assert!(
        client
            .call_tool(
                serde_json::from_value(json!({"name":"issues.create_issue","arguments":{}}))
                    .unwrap()
            )
            .await
            .is_err()
    );
    client
        .call_tool(
            serde_json::from_value(
                json!({"name":"issues.search_issues","arguments":{"fail":true}}),
            )
            .unwrap(),
        )
        .await
        .unwrap();
    assert!(
        !runtime
            .inner
            .lock()
            .await
            .config
            .activation
            .as_ref()
            .unwrap()
            .activated
    );
    for _ in 0..2 {
        client.call_tool(serde_json::from_value(json!({"name":"issues.search_issues","arguments":{"private_query":"MUST_NOT_BE_RECORDED"}})).unwrap()).await.unwrap();
    }
    let state = http_api::action(&runtime, json!({"action":"status"}))
        .await
        .unwrap();
    assert_eq!(state["activation"]["activated"], true);
    assert_eq!(state["activation"]["fixture"], true);
    assert_eq!(state["diagnostics"]["events"]["fixture_successful_call"], 2);
    assert!(
        state["diagnostics"]["events"]
            .get("downstream_successful_call")
            .is_none()
    );
    assert!(!state.to_string().contains("MUST_NOT_BE_RECORDED"));
    client.cancel().await.unwrap();
    running.stop.cancel();
    runtime.shutdown().await;
}
#[tokio::test]
async fn credential_setup_is_keychain_only_and_diagnostics_can_be_erased() {
    let dir = tempfile::tempdir().unwrap();
    let runtime = Runtime::persistent(dir.path().join("config.json")).unwrap();
    let journey = http_api::action(
        &runtime,
        json!({"action":"activation_start","diagnostics":true}),
    )
    .await
    .unwrap();
    let response = http_api::action(
        &runtime,
        json!({"action":"activation_token","token":"labeled-fixture-pat"}),
    )
    .await
    .unwrap();
    assert!(!response.to_string().contains("labeled-fixture-pat"));
    let server = journey["server"].as_str().unwrap();
    let reference = format!("upstream:{server}:pat");
    assert_eq!(
        umbod_gateway::secret_get(&reference).unwrap(),
        "Bearer labeled-fixture-pat"
    );
    assert!(
        !std::fs::read_to_string(dir.path().join("config.json"))
            .unwrap()
            .contains("labeled-fixture-pat")
    );
    http_api::action(
        &runtime,
        json!({"action":"diagnostics_set","enabled":false}),
    )
    .await
    .unwrap();
    let state = http_api::action(&runtime, json!({"action":"status"}))
        .await
        .unwrap();
    assert_eq!(state["diagnostics"]["events"], json!({}));
    assert_eq!(state["diagnostics"]["started_at"], serde_json::Value::Null);
    umbod_gateway::secret_delete(&reference).unwrap();
    http_api::action(
        &runtime,
        json!({"action":"client_remove","id":journey["client"]}),
    )
    .await
    .unwrap();
}
#[tokio::test]
async fn changed_configuration_and_symlinks_are_refused_without_overwriting() {
    let dir = tempfile::tempdir().unwrap();
    let root = dir.path().canonicalize().unwrap();
    let path = root.join("client.json");
    std::fs::write(&path, b"{}").unwrap();
    let runtime = Runtime::persistent(root.join("data/config.json")).unwrap();
    let journey = http_api::action(&runtime, json!({"action":"activation_start"}))
        .await
        .unwrap();
    let preview = http_api::action(
        &runtime,
        json!({"action":"client_preview","path":path,"command":env!("CARGO_BIN_EXE_umbod-gateway")}),
    )
    .await
    .unwrap();
    std::fs::write(&path, b"{\"later\":true}").unwrap();
    assert!(
        http_api::action(
            &runtime,
            json!({"action":"client_apply","preview":preview["id"],"consent":true})
        )
        .await
        .is_err()
    );
    assert_eq!(std::fs::read(&path).unwrap(), b"{\"later\":true}");
    #[cfg(unix)]
    {
        let link = root.join("link.json");
        std::os::unix::fs::symlink(&path, &link).unwrap();
        assert!(
        http_api::action(
            &runtime,
            json!({"action":"client_preview","path":link,"command":env!("CARGO_BIN_EXE_umbod-gateway")})
        )
        .await
        .is_err()
    );
    }
    // A preview must not be usable after deleting and replacing the client identity.
    let preview = http_api::action(
        &runtime,
        json!({"action":"client_preview","path":path,"command":env!("CARGO_BIN_EXE_umbod-gateway")}),
    )
    .await
    .unwrap();
    http_api::action(
        &runtime,
        json!({"action":"client_remove","id":journey["client"]}),
    )
    .await
    .unwrap();
    let next = http_api::action(&runtime, json!({"action":"activation_start"}))
        .await
        .unwrap();
    let stale = http_api::action(
        &runtime,
        json!({"action":"client_apply","preview":preview["id"],"consent":true}),
    )
    .await;
    http_api::action(
        &runtime,
        json!({"action":"client_remove","id":next["client"]}),
    )
    .await
    .unwrap();
    assert!(stale.is_err(), "a preview belongs to its original client");
}
#[tokio::test]
async fn reviewed_preset_cannot_be_used_for_an_unrelated_remote_server() {
    use umbod_gateway::{Client, Server};
    let mut config = Config::default();
    config.clients.push(Client {
        id: "fixture".into(),
        ..Default::default()
    });
    config.servers.push(Server {
        id: "notgithub".into(),
        transport: "stdio".into(),
        command: support::python(),
        args: vec![format!(
            "{}/scripts/fixture_issues.py",
            env!("CARGO_MANIFEST_DIR")
        )],
        ..Default::default()
    });
    let runtime = Runtime::memory(config);
    runtime.connect("notgithub").await.unwrap();
    let result=http_api::action(&runtime,json!({"action":"activation_approve","client":"fixture","server":"notgithub","tools":["search_issues"],"consent":true})).await;
    runtime.shutdown().await;
    assert!(
        result.is_err(),
        "matching tool names alone do not establish a reviewed integration"
    );
}
// Acceptance coverage of transaction failure paths after the vertical implementation slices.
#[tokio::test]
async fn failed_persistence_rolls_back_client_file_and_legacy_config_migrates() {
    #[cfg(unix)]
    use std::os::unix::fs::PermissionsExt;
    let dir = tempfile::tempdir().unwrap();
    let root = dir.path().canonicalize().unwrap();
    let config = root.join("config.json");
    std::fs::write(
        &config,
        br#"{"grants":{"legacy":["old.read"]},"servers":[{"id":"old"}],"clients":[{"id":"legacy"}],"custom_tools":[]}"#,
    )
    .unwrap();
    let runtime = Runtime::persistent(config.clone()).unwrap();
    let journey = http_api::action(&runtime, json!({"action":"activation_start"}))
        .await
        .unwrap();
    assert!(runtime.inner.lock().await.config.allowed("old.read"));
    assert!(!runtime.inner.lock().await.config.diagnostics.enabled);
    let path = root.join("client.json");
    std::fs::write(&path, b"{\"existing\":true}").unwrap();
    let preview = http_api::action(
        &runtime,
        json!({"action":"client_preview","path":path,"command":env!("CARGO_BIN_EXE_umbod-gateway")}),
    )
    .await
    .unwrap();
    std::fs::remove_file(&config).unwrap();
    std::fs::create_dir(&config).unwrap();
    assert!(
        http_api::action(
            &runtime,
            json!({"action":"client_apply","preview":preview["id"],"consent":true})
        )
        .await
        .is_err()
    );
    assert_eq!(std::fs::read(&path).unwrap(), b"{\"existing\":true}");
    #[cfg(unix)]
    assert_eq!(
        std::fs::metadata(preview["backup"].as_str().unwrap())
            .unwrap()
            .permissions()
            .mode()
            & 0o777,
        0o600
    );
    assert!(
        !runtime
            .inner
            .lock()
            .await
            .config
            .activation
            .as_ref()
            .unwrap()
            .configured
    );
    std::fs::remove_dir(&config).unwrap();
    http_api::action(
        &runtime,
        json!({"action":"client_remove","id":journey["client"]}),
    )
    .await
    .unwrap();
}
