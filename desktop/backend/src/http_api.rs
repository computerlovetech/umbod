use crate::*;
use axum::{
    Json, Router,
    extract::{DefaultBodyLimit, Request, State},
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::post,
};
use http::StatusCode;
use rmcp::transport::streamable_http_server::{
    StreamableHttpServerConfig, StreamableHttpService, session::local::LocalSessionManager,
};
use rmcp::{ErrorData, RoleServer, ServerHandler, model::*, service::RequestContext};
use std::net::SocketAddr;
use subtle::ConstantTimeEq;
use tokio_util::sync::CancellationToken;

#[derive(Clone)]
struct Api {
    runtime: Runtime,
    admin: String,
    stop: CancellationToken,
}
#[derive(Clone)]
struct Identity(String);
pub struct Running {
    pub management: SocketAddr,
    pub gateway: SocketAddr,
    pub stop: CancellationToken,
}
fn trusted(headers: &http::HeaderMap) -> bool {
    let host = headers
        .get("host")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    let host_ok = host.split(':').next() == Some("127.0.0.1");
    host_ok && !headers.contains_key("origin")
}
fn bearer(headers: &http::HeaderMap) -> &str {
    headers
        .get("authorization")
        .and_then(|v| v.to_str().ok())
        .and_then(|s| s.strip_prefix("Bearer "))
        .unwrap_or("")
}
async fn admin_guard(State(api): State<Api>, request: Request, next: Next) -> Response {
    if !trusted(request.headers()) {
        return StatusCode::FORBIDDEN.into_response();
    }
    if !bool::from(
        bearer(request.headers())
            .as_bytes()
            .ct_eq(api.admin.as_bytes()),
    ) {
        return StatusCode::UNAUTHORIZED.into_response();
    }
    next.run(request).await
}
async fn client_guard(State(api): State<Api>, mut request: Request, next: Next) -> Response {
    if !trusted(request.headers()) {
        return StatusCode::FORBIDDEN.into_response();
    }
    let hash = token_hash(bearer(request.headers()));
    let inner = api.runtime.inner.lock().await;
    let id = inner
        .config
        .clients
        .iter()
        .chain(inner.config.connection.iter())
        .find(|c| bool::from(c.token_hash.as_bytes().ct_eq(hash.as_bytes())))
        .map(|c| c.id.clone());
    drop(inner);
    match id {
        Some(id) => {
            request.extensions_mut().insert(Identity(id));
            next.run(request).await
        }
        None => StatusCode::UNAUTHORIZED.into_response(),
    }
}
#[derive(Clone)]
struct Gateway(Runtime);
fn identity(ctx: &RequestContext<RoleServer>) -> Result<String, ErrorData> {
    ctx.extensions
        .get::<http::request::Parts>()
        .and_then(|p| p.extensions.get::<Identity>())
        .map(|i| i.0.clone())
        .ok_or_else(|| ErrorData::invalid_request("Missing client identity", None))
}
impl ServerHandler for Gateway {
    fn get_info(&self) -> ServerConfig {
        ServerConfig::new(ServerCapabilities::builder().enable_tools().build())
    }
    async fn list_tools(
        &self,
        _: Option<PaginatedRequestParams>,
        ctx: RequestContext<RoleServer>,
    ) -> Result<ListToolsResult, ErrorData> {
        identity(&ctx)?;
        serde_json::from_value(json!({"tools":self.0.list().await}))
            .map_err(|_| ErrorData::internal_error("Invalid tool catalog", None))
    }
    async fn call_tool(
        &self,
        request: CallToolRequestParams,
        ctx: RequestContext<RoleServer>,
    ) -> Result<CallToolResponse, ErrorData> {
        let client = identity(&ctx)?;
        let result = self
            .0
            .call(&request.name, json!(request.arguments.unwrap_or_default()))
            .await
            .map_err(|e| ErrorData::invalid_request(e.to_string(), None))?;
        let result = serde_json::from_value::<CallToolResult>(result)
            .map_err(|_| ErrorData::internal_error("Invalid upstream result", None))?;
        if result.is_error != Some(true) {
            // Diagnostic persistence must never turn a completed tool call into a retryable failure.
            let _ = activation::downstream(&self.0, &client, &request.name).await;
        }
        Ok(result.into())
    }
}
pub async fn start(runtime: Runtime, admin: String) -> anyhow::Result<Running> {
    let management = tokio::net::TcpListener::bind("127.0.0.1:0").await?;
    let mut inner = runtime.inner.lock().await;
    let port = inner.config.gateway_port.unwrap_or(0);
    let gateway = tokio::net::TcpListener::bind((std::net::Ipv4Addr::LOCALHOST, port)).await
        .map_err(|_| anyhow::anyhow!("Saved gateway port {port} is unavailable. Close the conflicting listener, then retry. Umbod will not silently change your endpoint."))?;
    let mut config = inner.config.clone();
    config.gateway_port = Some(gateway.local_addr()?.port());
    runtime.persist(&config)?;
    inner.config = config;
    drop(inner);
    let stop = CancellationToken::new();
    let running = Running {
        management: management.local_addr()?,
        gateway: gateway.local_addr()?,
        stop: stop.clone(),
    };
    let api = Api {
        runtime: runtime.clone(),
        admin,
        stop: stop.clone(),
    };
    let app = Router::new()
        .route("/manage", post(manage))
        .layer(DefaultBodyLimit::max(1024 * 1024))
        .route_layer(middleware::from_fn_with_state(api.clone(), admin_guard))
        .with_state(api.clone());
    let cancel = stop.clone();
    tokio::spawn(async move {
        let _ = axum::serve(management, app)
            .with_graceful_shutdown(cancel.cancelled_owned())
            .await;
    });
    let mut config = StreamableHttpServerConfig::default();
    config.legacy_session_mode = false;
    config.json_response = true;
    config.cancellation_token = stop.clone();
    let service = StreamableHttpService::new(
        move || Ok(Gateway(runtime.clone())),
        Arc::new(LocalSessionManager::default()),
        config,
    );
    let app = Router::new()
        .nest_service("/mcp", service)
        .layer(DefaultBodyLimit::max(1024 * 1024))
        .layer(middleware::from_fn_with_state(api, client_guard));
    let cancel = stop.clone();
    tokio::spawn(async move {
        let _ = axum::serve(gateway, app)
            .with_graceful_shutdown(cancel.cancelled_owned())
            .await;
    });
    Ok(running)
}
async fn manage(State(api): State<Api>, Json(body): Json<Value>) -> Response {
    if body["action"] == "health" {
        return Json(
            json!({"ok":true,"pid":std::process::id(),"profile":profile::current().name()}),
        )
        .into_response();
    }
    if body["action"] == "shutdown" {
        api.stop.cancel();
        return Json(json!({"ok":true})).into_response();
    }
    match action(&api.runtime, body).await {
        Ok(result) => Json(result).into_response(),
        Err(error) => (
            StatusCode::BAD_REQUEST,
            Json(json!({"error":error.to_string()})),
        )
            .into_response(),
    }
}
fn string<'a>(body: &'a Value, key: &str) -> anyhow::Result<&'a str> {
    body[key]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("Missing {key}"))
}
pub async fn action(runtime: &Runtime, body: Value) -> anyhow::Result<Value> {
    match string(&body, "action")? {
        "diagnostics_set" => {
            let enabled = body["enabled"]
                .as_bool()
                .ok_or_else(|| anyhow::anyhow!("Missing enabled"))?;
            let mut inner = runtime.inner.lock().await;
            let mut config = inner.config.clone();
            config.diagnostics = activation::Diagnostics {
                enabled,
                started_at: enabled.then(activation::now),
                ..Default::default()
            };
            runtime.persist(&config)?;
            inner.config = config;
            Ok(json!({"ok":true}))
        }
        "activation_token" => {
            let token = string(&body, "token")?.trim();
            anyhow::ensure!(
                !token.is_empty()
                    && token.len() < 4096
                    && token.bytes().all(|b| b.is_ascii_graphic()),
                "Enter a PAT without whitespace"
            );
            let mut inner = runtime.inner.lock().await;
            let journey = inner
                .config
                .activation
                .as_ref()
                .ok_or_else(|| anyhow::anyhow!("Start setup first"))?;
            let id = journey.server.clone();
            anyhow::ensure!(
                inner
                    .config
                    .servers
                    .iter()
                    .any(|s| s.id == id && s.url == activation::ENDPOINT && s.transport == "http"),
                "Integration changed; use advanced credentials"
            );
            secret_set(&format!("upstream:{id}:pat"), &format!("Bearer {token}"))?;
            if let Some(connection) = inner.connections.remove(&id) {
                let _ = connection.cancel().await;
            }
            inner.tools.retain(|n, _| !n.starts_with(&format!("{id}.")));
            inner
                .statuses
                .insert(id, "Credential saved — connect to verify access".into());
            Ok(json!({"ok":true}))
        }
        "client_preview" => {
            client_setup::preview(
                runtime,
                PathBuf::from(string(&body, "path")?),
                string(&body, "command")?,
            )
            .await
        }
        "client_apply" => {
            client_setup::apply(runtime, string(&body, "preview")?, body["consent"] == true).await
        }
        "client_undo" => client_setup::undo(runtime, body["consent"] == true).await,
        "activation_start" => {
            activation::start(runtime, body["diagnostics"].as_bool().unwrap_or(false)).await
        }
        "activation_approve" => {
            anyhow::ensure!(
                body["consent"] == true,
                "Explicit permission approval required"
            );
            let client = string(&body, "client")?;
            let server = string(&body, "server")?;
            let tools: Vec<String> = serde_json::from_value(body["tools"].clone())?;
            anyhow::ensure!(!tools.is_empty(), "Select at least one tool");
            let mut inner = runtime.inner.lock().await;
            anyhow::ensure!(
                inner.config.clients.iter().any(|c| c.id == client),
                "Client not found"
            );
            let journey = inner
                .config
                .activation
                .as_ref()
                .ok_or_else(|| anyhow::anyhow!("Start the curated integration first"))?;
            anyhow::ensure!(
                journey.client == client && journey.server == server,
                "Preset belongs to the selected integration and client"
            );
            let target = inner
                .config
                .servers
                .iter()
                .find(|s| s.id == server)
                .ok_or_else(|| anyhow::anyhow!("Integration removed"))?;
            anyhow::ensure!(
                (target.url == activation::ENDPOINT && target.transport == "http")
                    || (journey.fixture
                        && (target.transport == "stdio"
                            || validate_url(&target.url).is_ok_and(|u| matches!(
                                u.host_str(),
                                Some("127.0.0.1" | "localhost" | "[::1]")
                            )))),
                "Integration target changed. Review tools individually in Permissions."
            );
            for tool in &tools {
                anyhow::ensure!(
                    ["issue_read", "list_issues", "search_issues"].contains(&tool.as_str()),
                    "Tool is outside the reviewed issues preset"
                );
                anyhow::ensure!(
                    inner.tools.contains_key(&format!("{server}.{tool}")),
                    "Required tool missing; reconnect or review provider changes"
                );
            }
            let mut config = inner.config.clone();
            for tool in tools {
                config.grant(&format!("{server}.{tool}"), true);
            }
            config.diagnostics.event("permission_approval");
            runtime.persist(&config)?;
            inner.config = config;
            Ok(json!({"ok":true}))
        }
        "activation_catalog" => Ok(
            json!({"client":"Claude Desktop","integration":"GitHub issues","endpoint":"https://api.githubcopilot.com/mcp/x/issues/readonly","auth":"pat","tools":["issue_read","list_issues","search_issues"]}),
        ),
        "oauth_begin" => Ok(
            json!({"url":oauth::begin(runtime,string(&body,"id")?,body["client_id"].as_str().unwrap_or("")).await?}),
        ),
        "oauth_logout" => {
            oauth::logout(runtime, string(&body, "id")?).await?;
            Ok(json!({"ok":true}))
        }
        "oauth_refresh" => {
            oauth::refresh_connection(runtime, string(&body, "id")?).await?;
            Ok(json!({"ok":true}))
        }
        "status" => {
            let inner = runtime.inner.lock().await;
            Ok(
                json!({"activation":inner.config.activation,"client_setup":inner.config.client_setup,"diagnostics":inner.config.diagnostics,"tool_usage":inner.config.tool_usage,"daily_calls":inner.config.daily_calls,"daily_tracking_started":inner.config.daily_tracking_started,"servers":inner.config.servers,"allowed_tools":inner.config.allowed_tools,"tools":inner.tools.values().collect::<Vec<_>>(),"statuses":inner.statuses}),
            )
        }
        "server_save" => {
            let mut server: Server = serde_json::from_value(body["server"].clone())?;
            if server.id.is_empty() {
                server.id = uuid::Uuid::new_v4().simple().to_string();
            }
            anyhow::ensure!(
                server
                    .id
                    .chars()
                    .all(|c| c.is_ascii_alphanumeric() || c == '_'),
                "Invalid connector identifier"
            );
            anyhow::ensure!(!server.name.trim().is_empty(), "Give the connector a name");
            for reference in server.headers.values().chain(server.env.values()) {
                anyhow::ensure!(
                    reference.starts_with("upstream:") && !reference.starts_with("upstream:oauth:"),
                    "Use an upstream: credential reference, not a client or OAuth document"
                );
            }
            for header in server.headers.keys() {
                let name = http::HeaderName::from_bytes(header.as_bytes())?;
                anyhow::ensure!(
                    !matches!(
                        name.as_str(),
                        "host" | "origin" | "content-length" | "connection" | "transfer-encoding"
                    ),
                    "Reserved HTTP header"
                );
            }
            if server.transport == "stdio" {
                platform::validate_executable(std::path::Path::new(&server.command))?;
            }
            if server.transport == "http" {
                validate_url(&server.url)?;
            }
            anyhow::ensure!(
                matches!(server.transport.as_str(), "http" | "stdio" | "sse"),
                "Unknown transport"
            );
            let mut inner = runtime.inner.lock().await;
            let mut config = inner.config.clone();
            inner.oauth_pending.remove(&server.id);
            if config.servers.iter().any(|s| s.id == server.id && s.oauth) {
                secret_delete(&format!("upstream:oauth:{}", server.id))?;
            }
            server.oauth = false;
            config.servers.retain(|s| s.id != server.id);
            config.servers.push(server.clone());
            // Editing the target invalidates every previous grant to that target.
            config
                .allowed_tools
                .retain(|t| !t.starts_with(&format!("{}.", server.id)));
            runtime.persist(&config)?;
            inner.config = config;
            inner
                .tools
                .retain(|t, _| !t.starts_with(&format!("{}.", server.id)));
            if let Some(old) = inner.connections.remove(&server.id) {
                let _ = old.cancel().await;
            }
            inner.statuses.insert(
                server.id.clone(),
                "Disconnected — connect to discover tools".into(),
            );
            Ok(json!({"server":server}))
        }
        "server_remove" => {
            let id = string(&body, "id")?;
            let mut inner = runtime.inner.lock().await;
            inner.oauth_pending.remove(id);
            if inner.config.servers.iter().any(|s| s.id == id && s.oauth) {
                secret_delete(&format!("upstream:oauth:{id}"))?;
            }
            let mut config = inner.config.clone();
            inner.client_preview = None;
            if config.activation.as_ref().is_some_and(|j| j.server == id) {
                config.activation = None;
            }
            config.servers.retain(|s| s.id != id);
            config
                .allowed_tools
                .retain(|t| !t.starts_with(&format!("{id}.")));
            runtime.persist(&config)?;
            inner.config = config;
            inner.tools.retain(|t, _| !t.starts_with(&format!("{id}.")));
            inner.statuses.remove(id);
            if let Some(old) = inner.connections.remove(id) {
                let _ = old.cancel().await;
            }
            Ok(json!({"ok":true}))
        }
        "connect" => {
            retry_secret_access();
            runtime.connect(string(&body, "id")?).await?;
            Ok(json!({"ok":true}))
        }
        "grant" => {
            let tool = string(&body, "tool")?;
            {
                let inner = runtime.inner.lock().await;
                anyhow::ensure!(inner.tools.contains_key(tool), "Tool not found");
            }
            runtime
                .grant(
                    tool,
                    body["allow"]
                        .as_bool()
                        .ok_or_else(|| anyhow::anyhow!("Missing allow"))?,
                )
                .await?;
            Ok(json!({"ok":true}))
        }
        "connection_setup" => {
            retry_secret_access();
            let mut inner = runtime.inner.lock().await;
            if let Some(connection) = &inner.config.connection {
                return Ok(json!({"id":connection.id}));
            }
            let id = uuid::Uuid::new_v4().simple().to_string();
            let token = new_token();
            secret_set(&format!("client:{id}"), &token)?;
            let mut config = inner.config.clone();
            config.connection = Some(Client {
                id: id.clone(),
                name: "Umbod connection".into(),
                token_hash: token_hash(&token),
            });
            if let Err(error) = runtime.persist(&config) {
                let _ = secret_delete(&format!("client:{id}"));
                return Err(error);
            }
            inner.config = config;
            Ok(json!({"id":id}))
        }
        "connection_token" => {
            let inner = runtime.inner.lock().await;
            let connection = inner
                .config
                .connection
                .iter()
                .chain(inner.config.clients.iter())
                .find(|connection| {
                    body["id"].as_str().map_or(
                        inner
                            .config
                            .connection
                            .as_ref()
                            .is_some_and(|shared| shared.id == connection.id),
                        |id| id == connection.id,
                    )
                })
                .ok_or_else(|| anyhow::anyhow!("Set up the Umbod connection first"))?;
            Ok(json!({"token":secret_get(&format!("client:{}", connection.id))?}))
        }
        "secret_delete" => {
            let reference = string(&body, "reference")?;
            anyhow::ensure!(
                reference.starts_with("upstream:"),
                "Invalid credential reference"
            );
            secret_delete(reference)?;
            Ok(json!({"ok":true}))
        }
        "client_remove" => {
            let id = string(&body, "id")?;
            let mut inner = runtime.inner.lock().await;
            let mut config = inner.config.clone();
            inner.client_preview = None;
            config.clients.retain(|c| c.id != id);
            if config.activation.as_ref().is_some_and(|j| j.client == id) {
                config.activation = None;
            }
            if config
                .connection
                .as_ref()
                .is_some_and(|connection| connection.id == id)
            {
                config.connection = None;
            }
            runtime.persist(&config)?;
            inner.config = config;
            secret_delete(&format!("client:{id}"))?;
            Ok(json!({"ok":true}))
        }
        "secret_set" => {
            let reference = string(&body, "reference")?;
            anyhow::ensure!(
                reference.starts_with("upstream:") && reference.len() > 9,
                "Credential reference must start with upstream:"
            );
            secret_set(reference, string(&body, "value")?)?;
            Ok(json!({"ok":true}))
        }
        _ => anyhow::bail!("Unknown management action"),
    }
}
