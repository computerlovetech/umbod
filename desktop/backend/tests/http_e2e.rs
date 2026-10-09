use rmcp::{
    ErrorData, RoleServer, ServerHandler, ServiceExt,
    model::*,
    service::RequestContext,
    transport::{
        StreamableHttpClientTransport,
        streamable_http_client::StreamableHttpClientTransportConfig,
        streamable_http_server::{
            StreamableHttpServerConfig, StreamableHttpService, session::local::LocalSessionManager,
        },
    },
};
use serde_json::json;
use std::sync::{
    Arc,
    atomic::{AtomicBool, AtomicUsize, Ordering},
};
use umbod_gateway::*;
#[derive(Clone)]
struct Fixture {
    new_tool: Arc<AtomicBool>,
    calls: Arc<AtomicUsize>,
}
impl ServerHandler for Fixture {
    fn get_info(&self) -> ServerConfig {
        ServerConfig::new(ServerCapabilities::builder().enable_tools().build())
    }
    async fn list_tools(
        &self,
        _: Option<PaginatedRequestParams>,
        _: RequestContext<RoleServer>,
    ) -> Result<ListToolsResult, ErrorData> {
        let mut tools = vec![
            json!({"name":"echo","inputSchema":{"type":"object","properties":{"text":{"type":"string"}},"required":["text"],"additionalProperties":false}}),
        ];
        if self.new_tool.load(Ordering::SeqCst) {
            tools.push(json!({"name":"new","inputSchema":{"type":"object"}}));
        }
        Ok(serde_json::from_value(json!({"tools":tools})).unwrap())
    }
    async fn call_tool(
        &self,
        r: CallToolRequestParams,
        _: RequestContext<RoleServer>,
    ) -> Result<CallToolResponse, ErrorData> {
        self.calls.fetch_add(1, Ordering::SeqCst);
        let arguments = r.arguments.unwrap();
        let text = arguments["text"].as_str().unwrap();
        if text == "tool-error" {
            return Ok(CallToolResult::error(vec![ContentBlock::text("fixture failure")]).into());
        }
        if text == "transport-error" {
            return Err(ErrorData::internal_error("fixture transport failure", None));
        }
        Ok(CallToolResult::success(vec![ContentBlock::text(text)]).into())
    }
}
#[tokio::test]
async fn http_sse_proxy_acl_new_tools_malformed_and_restart() {
    let fixture = Fixture {
        new_tool: Default::default(),
        calls: Default::default(),
    };
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let make = fixture.clone();
    let mut options = StreamableHttpServerConfig::default();
    options.json_response = false;
    options.legacy_session_mode = true;
    let service = StreamableHttpService::new(
        move || Ok(make.clone()),
        Arc::new(LocalSessionManager::default()),
        options,
    );
    let upstream = tokio::spawn(async move {
        axum::serve(listener, axum::Router::new().nest_service("/mcp", service))
            .await
            .unwrap()
    });
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("config.json");
    let runtime = Runtime::persistent(path.clone()).unwrap();
    http_api::action(&runtime,json!({"action":"server_save","server":{"id":"remote","name":"HTTP SSE fixture","transport":"http","url":format!("http://{address}/mcp")}})).await.unwrap();
    runtime.connect("remote").await.unwrap();
    {
        let mut inner = runtime.inner.lock().await;
        inner.config.clients.push(Client {
            id: "alice".into(),
            name: "Alice".into(),
            token_hash: token_hash("fixture-alice"),
        });
        inner.config.clients.push(Client {
            id: "bob".into(),
            name: "Bob".into(),
            token_hash: token_hash("fixture-bob"),
        });
        runtime.persist(&inner.config).unwrap();
    }
    let running = http_api::start(runtime.clone(), "fixture-admin-token".into())
        .await
        .unwrap();
    let endpoint = format!("http://{}/mcp", running.gateway);
    let client = ()
        .serve(StreamableHttpClientTransport::with_client(
            reqwest::Client::new(),
            StreamableHttpClientTransportConfig::with_uri(endpoint.clone())
                .auth_header("fixture-alice"),
        ))
        .await
        .unwrap();
    assert!(client.list_all_tools().await.unwrap().is_empty());
    let call = || {
        serde_json::from_value(
            json!({"name":"remote.echo","arguments":{"text":"through real HTTP and SSE"}}),
        )
        .unwrap()
    };
    assert!(client.call_tool(call()).await.is_err());
    assert_eq!(fixture.calls.load(Ordering::SeqCst), 0);
    runtime.grant("remote.echo", true).await.unwrap();
    assert_eq!(client.list_all_tools().await.unwrap().len(), 1);
    let result = client.call_tool(call()).await.unwrap();
    assert_eq!(
        serde_json::to_value(result).unwrap()["content"][0]["text"],
        "through real HTTP and SSE"
    );
    let bob = ()
        .serve(StreamableHttpClientTransport::with_client(
            reqwest::Client::new(),
            StreamableHttpClientTransportConfig::with_uri(endpoint.clone())
                .auth_header("fixture-bob"),
        ))
        .await
        .unwrap();
    assert_eq!(bob.list_all_tools().await.unwrap().len(), 1);
    assert!(bob.call_tool(call()).await.is_ok());
    fixture.new_tool.store(true, Ordering::SeqCst);
    runtime.connect("remote").await.unwrap();
    assert_eq!(runtime.catalog().await.len(), 2);
    assert_eq!(client.list_all_tools().await.unwrap().len(), 1);
    assert!(
        client
            .call_tool(serde_json::from_value(json!({"name":"remote.new","arguments":{}})).unwrap())
            .await
            .is_err()
    );
    assert!(
        client
            .call_tool(
                serde_json::from_value(json!({"name":"remote.echo","arguments":{"text":42}}))
                    .unwrap()
            )
            .await
            .is_err()
    );
    let malformed = reqwest::Client::new()
        .post(&endpoint)
        .bearer_auth("fixture-alice")
        .header("Content-Type", "application/json")
        .header("Accept", "application/json, text/event-stream")
        .body("{bad")
        .send()
        .await
        .unwrap();
    assert!(malformed.status().is_client_error());
    runtime.grant("remote.echo", false).await.unwrap();
    assert!(client.call_tool(call()).await.is_err());
    assert!(bob.call_tool(call()).await.is_err());
    assert!(bob.list_all_tools().await.unwrap().is_empty());
    runtime.grant("remote.echo", true).await.unwrap();
    let failed = client
        .call_tool(
            serde_json::from_value(json!({"name":"remote.echo","arguments":{"text":"tool-error"}}))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(serde_json::to_value(failed).unwrap()["isError"], true);
    assert!(
        client
            .call_tool(
                serde_json::from_value(
                    json!({"name":"remote.echo","arguments":{"text":"transport-error"}})
                )
                .unwrap()
            )
            .await
            .is_err()
    );
    // Only dispatched calls count, across both clients. Denied and malformed requests do not.
    let status = http_api::action(&runtime, json!({"action":"status"}))
        .await
        .unwrap();
    assert_eq!(
        status["tool_usage"],
        json!({"remote.echo":{"succeeded":2,"failed":2}})
    );
    assert!(
        !std::fs::read_to_string(&path)
            .unwrap()
            .contains("through real HTTP and SSE")
    );
    assert_eq!(
        status["daily_calls"]
            .as_object()
            .unwrap()
            .values()
            .map(|v| v.as_u64().unwrap())
            .sum::<u64>(),
        4
    );
    client.cancel().await.unwrap();
    bob.cancel().await.unwrap();
    running.stop.cancel();
    runtime.shutdown().await;
    let restored = Runtime::persistent(path).unwrap();
    restored.connect("remote").await.unwrap();
    assert_eq!(restored.list().await.len(), 1);
    assert_eq!(
        restored
            .call("remote.echo", json!({"text":"after restart"}))
            .await
            .unwrap()["content"][0]["text"],
        "after restart"
    );
    let status = http_api::action(&restored, json!({"action":"status"}))
        .await
        .unwrap();
    assert_eq!(
        status["tool_usage"],
        json!({"remote.echo":{"succeeded":3,"failed":2}})
    );
    assert_eq!(
        status["daily_calls"]
            .as_object()
            .unwrap()
            .values()
            .map(|v| v.as_u64().unwrap())
            .sum::<u64>(),
        5
    );
    restored.shutdown().await;
    upstream.abort();
}
#[tokio::test]
async fn upstream_fixture_exercises_legacy_sessions_and_sse_wire_format() {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let service = StreamableHttpService::new(
        || {
            Ok(Fixture {
                new_tool: Default::default(),
                calls: Default::default(),
            })
        },
        Arc::new(LocalSessionManager::default()),
        StreamableHttpServerConfig::default(),
    );
    let task = tokio::spawn(async move {
        axum::serve(listener, axum::Router::new().nest_service("/mcp", service))
            .await
            .unwrap()
    });
    let http = reqwest::Client::new();
    let url = format!("http://{address}/mcp");
    let init=http.post(&url).header("Accept","application/json, text/event-stream").json(&json!({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"session-fixture-test","version":"1"}}})).send().await.unwrap();
    assert!(init.status().is_success());
    let session = init.headers()["mcp-session-id"]
        .to_str()
        .unwrap()
        .to_string();
    assert!(!session.is_empty());
    let _ = init.text().await.unwrap();
    let notification = http
        .post(&url)
        .header("Accept", "application/json, text/event-stream")
        .header("Mcp-Session-Id", &session)
        .header("MCP-Protocol-Version", "2025-11-25")
        .json(&json!({"jsonrpc":"2.0","method":"notifications/initialized"}))
        .send()
        .await
        .unwrap();
    assert_eq!(notification.status(), 202);
    let list = http
        .post(&url)
        .header("Accept", "application/json, text/event-stream")
        .header("Mcp-Session-Id", &session)
        .header("MCP-Protocol-Version", "2025-11-25")
        .json(&json!({"jsonrpc":"2.0","id":2,"method":"tools/list"}))
        .send()
        .await
        .unwrap();
    assert_eq!(list.headers()["content-type"], "text/event-stream");
    let text = list.text().await.unwrap();
    assert!(text.contains("data:"), "SSE data field missing: {text}");
    assert!(text.contains("echo"));
    let delete = http
        .delete(&url)
        .header("Mcp-Session-Id", &session)
        .header("MCP-Protocol-Version", "2025-11-25")
        .send()
        .await
        .unwrap();
    assert!(delete.status().is_success());
    task.abort();
}
#[tokio::test]
async fn authenticated_upstream_header_stays_out_of_downstream_catalog_and_config() {
    let reference = format!("upstream:fixture:{}", uuid::Uuid::new_v4());
    let secret = umbod_gateway::new_token();
    secret_set(&reference, &secret).unwrap();
    let observed = Arc::new(AtomicBool::new(false));
    let seen = observed.clone();
    let expected = secret.clone();
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let service = StreamableHttpService::new(
        || {
            Ok(Fixture {
                new_tool: Default::default(),
                calls: Default::default(),
            })
        },
        Arc::new(LocalSessionManager::default()),
        StreamableHttpServerConfig::default(),
    );
    let app = axum::Router::new()
        .nest_service("/mcp", service)
        .layer(axum::middleware::from_fn(
            move |request: axum::extract::Request, next: axum::middleware::Next| {
                let expected = expected.clone();
                let seen = seen.clone();
                async move {
                    if request
                        .headers()
                        .get("x-api-key")
                        .and_then(|v| v.to_str().ok())
                        != Some(expected.as_str())
                    {
                        return axum::response::IntoResponse::into_response(
                            http::StatusCode::UNAUTHORIZED,
                        );
                    }
                    seen.store(true, Ordering::SeqCst);
                    next.run(request).await
                }
            },
        ));
    let task = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    let runtime = Runtime::memory(Config::default());
    http_api::action(&runtime,json!({"action":"server_save","server":{"id":"authenticated","name":"Authenticated fixture","transport":"http","url":format!("http://{address}/mcp"),"headers":{"X-API-Key":reference}}})).await.unwrap();
    runtime.connect("authenticated").await.unwrap();
    assert!(observed.load(Ordering::SeqCst));
    runtime.grant("authenticated.echo", true).await.unwrap();
    assert!(
        !serde_json::to_string(&runtime.list().await)
            .unwrap()
            .contains(&secret)
    );
    assert!(
        !serde_json::to_string(&runtime.inner.lock().await.config)
            .unwrap()
            .contains(&secret)
    );
    assert_eq!(
        runtime
            .call("authenticated.echo", json!({"text":"authenticated call"}))
            .await
            .unwrap()["content"][0]["text"],
        "authenticated call"
    );
    runtime.shutdown().await;
    secret_delete(&reference).unwrap();
    task.abort();
}
