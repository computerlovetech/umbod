pub mod activation;
pub mod client_setup;
pub mod oauth;
pub mod platform;
pub mod profile;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

/// Local aggregate counts only; never retain tool arguments or responses.
#[derive(Clone, Default, Serialize, Deserialize)]
pub struct ToolUsage {
    pub succeeded: u64,
    pub failed: u64,
}

#[derive(Clone, Default, Serialize, Deserialize)]
#[serde(from = "ConfigDocument")]
pub struct Config {
    pub gateway_port: Option<u16>,
    pub activation: Option<activation::Journey>,
    pub client_setup: Option<client_setup::Receipt>,
    pub diagnostics: activation::Diagnostics,
    pub tool_usage: BTreeMap<String, ToolUsage>,
    pub daily_calls: BTreeMap<u64, u64>,
    pub daily_tracking_started: Option<u64>,
    pub allowed_tools: BTreeSet<String>,
    pub servers: Vec<Server>,
    /// Legacy identities remain valid so existing client configurations keep working.
    pub clients: Vec<Client>,
    pub connection: Option<Client>,
}

#[derive(Default, Deserialize)]
#[serde(default, deny_unknown_fields)]
struct ConfigDocument {
    gateway_port: Option<u16>,
    activation: Option<activation::Journey>,
    client_setup: Option<client_setup::Receipt>,
    diagnostics: activation::Diagnostics,
    tool_usage: BTreeMap<String, ToolUsage>,
    daily_calls: BTreeMap<u64, u64>,
    daily_tracking_started: Option<u64>,
    allowed_tools: Option<BTreeSet<String>>,
    servers: Vec<Server>,
    clients: Vec<Client>,
    connection: Option<Client>,
    grants: BTreeMap<String, BTreeSet<String>>,
    // Accept and discard removed API tool definitions when upgrading old configurations.
    #[serde(rename = "custom_tools")]
    _custom_tools: Vec<serde_json::Value>,
}
impl From<ConfigDocument> for Config {
    fn from(document: ConfigDocument) -> Self {
        let allowed_tools = document.allowed_tools.unwrap_or_else(|| {
            let mut shared = document
                .clients
                .first()
                .and_then(|client| document.grants.get(&client.id))
                .cloned()
                .unwrap_or_default();
            for client in &document.clients {
                shared.retain(|tool| {
                    document
                        .grants
                        .get(&client.id)
                        .is_some_and(|grants| grants.contains(tool))
                });
            }
            shared.retain(|tool| {
                document
                    .servers
                    .iter()
                    .any(|server| tool.starts_with(&format!("{}.", server.id)))
            });
            shared
        });
        Self {
            gateway_port: document.gateway_port,
            activation: document.activation,
            client_setup: document.client_setup,
            diagnostics: document.diagnostics,
            tool_usage: document.tool_usage,
            daily_calls: document.daily_calls,
            daily_tracking_started: document.daily_tracking_started,
            allowed_tools,
            servers: document.servers,
            clients: document.clients,
            connection: document.connection,
        }
    }
}
impl Config {
    pub fn record_call(&mut self, tool: &str, succeeded: bool, unix_seconds: u64) {
        let day = unix_seconds / 86_400;
        self.daily_tracking_started.get_or_insert(day);
        let count = self.daily_calls.entry(day).or_default();
        *count = count.saturating_add(1);
        let usage = self.tool_usage.entry(tool.to_owned()).or_default();
        if succeeded {
            usage.succeeded = usage.succeeded.saturating_add(1);
        } else {
            usage.failed = usage.failed.saturating_add(1);
        }
    }
    pub fn allowed(&self, tool: &str) -> bool {
        self.allowed_tools.contains(tool)
    }
    pub fn grant(&mut self, tool: &str, allow: bool) {
        if allow {
            self.allowed_tools.insert(tool.into());
        } else {
            self.allowed_tools.remove(tool);
        }
    }
}
impl Config {
    pub fn load(path: &std::path::Path) -> anyhow::Result<Self> {
        if !path.exists() {
            return Ok(Self::default());
        }
        let bytes = std::fs::read(path)?;
        let config = serde_json::from_slice(&bytes)?;
        let document: serde_json::Value = serde_json::from_slice(&bytes)?;
        if document.get("allowed_tools").is_none() {
            // Retain an owner-only migration backup before the next atomic save.
            use std::io::Write;
            match platform::private_file(
                &path.with_extension("before-shared-permissions.json"),
                true,
            ) {
                Ok(mut backup) => {
                    backup.write_all(&bytes)?;
                    backup.sync_all()?;
                }
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
                Err(error) => return Err(error.into()),
            }
        }
        Ok(config)
    }
    pub fn save(&self, path: &std::path::Path) -> anyhow::Result<()> {
        let parent = path
            .parent()
            .ok_or_else(|| anyhow::anyhow!("Missing configuration directory"))?;
        platform::private_dir(parent)?;
        platform::atomic_write(path, &serde_json::to_vec_pretty(self)?)?;
        Ok(())
    }
}

#[derive(Clone, Default, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Server {
    pub id: String,
    pub name: String,
    pub transport: String,
    pub command: String,
    pub args: Vec<String>,
    pub url: String,
    pub oauth: bool,
    /// Header/env names map to Keychain account references; never values.
    pub headers: BTreeMap<String, String>,
    pub env: BTreeMap<String, String>,
}
#[derive(Clone, Default, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Client {
    pub id: String,
    pub name: String,
    pub token_hash: String,
}

// Process-local cache: never written to disk. Serialize loads so concurrent clients
// cannot trigger duplicate Keychain prompts. Failed mutations invalidate old values.
static SECRETS: std::sync::Mutex<BTreeMap<String, Option<String>>> =
    std::sync::Mutex::new(BTreeMap::new());
pub fn secret_get(reference: &str) -> anyhow::Result<String> {
    let mut cache = SECRETS
        .lock()
        .map_err(|_| anyhow::anyhow!("Credential cache unavailable"))?;
    let unavailable = || {
        anyhow::anyhow!(
            "Credential unavailable in the OS credential vault. Retry from Settings → MCP or reconnect the connector in Umbod."
        )
    };
    if let Some(value) = cache.get(reference) {
        return value.clone().ok_or_else(unavailable);
    }
    #[cfg(not(windows))]
    let value = keyring::Entry::new(profile::current().service(), reference)?
        .get_password()
        .ok();
    #[cfg(windows)]
    let value = platform::credential_get(profile::current().service(), reference).ok();
    cache.insert(reference.into(), value.clone());
    value.ok_or_else(unavailable)
}
/// Explicit UI operations can retry denied reads; background clients cannot.
pub fn retry_secret_access() {
    if let Ok(mut cache) = SECRETS.lock() {
        cache.retain(|_, value| value.is_some());
    }
}

pub fn secret_set(reference: &str, value: &str) -> anyhow::Result<()> {
    let mut cache = SECRETS
        .lock()
        .map_err(|_| anyhow::anyhow!("Credential cache unavailable"))?;
    cache.remove(reference);
    #[cfg(not(windows))]
    keyring::Entry::new(profile::current().service(), reference)?
        .set_password(value)
        .map_err(|_| {
            anyhow::anyhow!("Keychain write failed. Unlock your login Keychain and retry.")
        })?;
    #[cfg(windows)]
    platform::credential_set(profile::current().service(), reference, value)?;
    cache.insert(reference.into(), Some(value.into()));
    Ok(())
}
pub fn secret_delete(reference: &str) -> anyhow::Result<()> {
    let mut cache = SECRETS
        .lock()
        .map_err(|_| anyhow::anyhow!("Credential cache unavailable"))?;
    cache.remove(reference);
    #[cfg(windows)]
    {
        Ok(platform::credential_delete(
            profile::current().service(),
            reference,
        )?)
    }
    #[cfg(not(windows))]
    match keyring::Entry::new(profile::current().service(), reference)?.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(_) => anyhow::bail!("Keychain deletion failed"),
    }
}

pub fn validate_url(value: &str) -> anyhow::Result<url::Url> {
    let url = url::Url::parse(value)?;
    anyhow::ensure!(
        url.username().is_empty() && url.password().is_none() && url.fragment().is_none(),
        "URL must not contain credentials or a fragment"
    );
    anyhow::ensure!(
        url.scheme() == "https"
            || (url.scheme() == "http"
                && matches!(url.host_str(), Some("127.0.0.1" | "localhost" | "[::1]"))),
        "Use HTTPS (HTTP is only allowed for loopback fixtures)"
    );
    Ok(url)
}

use rmcp::{
    RoleClient, ServiceExt,
    service::RunningService,
    transport::{
        StreamableHttpClientTransport, TokioChildProcess,
        streamable_http_client::StreamableHttpClientTransportConfig,
    },
};
use serde_json::{Value, json};
use std::{path::PathBuf, sync::Arc, time::Duration};
use tokio::sync::Mutex;
type Upstream = RunningService<RoleClient, ()>;
#[derive(Clone)]
pub struct Runtime {
    pub inner: Arc<Mutex<Inner>>,
    pub path: Option<PathBuf>,
}
pub struct Inner {
    pub client_preview: Option<client_setup::Preview>,
    pub config: Config,
    connections: BTreeMap<String, Upstream>,
    tools: BTreeMap<String, Value>,
    pub statuses: BTreeMap<String, String>,
    pub oauth_pending: BTreeMap<String, String>,
}
impl Runtime {
    pub fn memory(mut config: Config) -> Self {
        config
            .daily_tracking_started
            .get_or_insert(unix_seconds() / 86_400);
        Self {
            inner: Arc::new(Mutex::new(Inner {
                client_preview: None,
                tools: BTreeMap::new(),
                config,
                connections: BTreeMap::new(),
                statuses: BTreeMap::new(),
                oauth_pending: BTreeMap::new(),
            })),
            path: None,
        }
    }
    pub fn persistent(path: PathBuf) -> anyhow::Result<Self> {
        let mut r = Self::memory(Config::load(&path)?);
        r.path = Some(path);
        Ok(r)
    }
    pub fn persist(&self, config: &Config) -> anyhow::Result<()> {
        if let Some(path) = &self.path {
            config.save(path)?;
        }
        Ok(())
    }
    pub async fn grant(&self, tool: &str, allow: bool) -> anyhow::Result<()> {
        let mut inner = self.inner.lock().await;
        let mut next = inner.config.clone();
        next.grant(tool, allow);
        self.persist(&next)?;
        inner.config = next;
        Ok(())
    }
    pub async fn connect(&self, id: &str) -> anyhow::Result<()> {
        let mut inner = self.inner.lock().await;
        self.connect_locked(&mut inner, id).await
    }
    async fn connect_locked(&self, inner: &mut Inner, id: &str) -> anyhow::Result<()> {
        let server = inner
            .config
            .servers
            .iter()
            .find(|s| s.id == id)
            .cloned()
            .ok_or_else(|| anyhow::anyhow!("Connector not found"))?;
        if let Some(old) = inner.connections.remove(id) {
            let _ = old.cancel().await;
        }
        inner
            .tools
            .retain(|name, _| !name.starts_with(&format!("{id}.")));
        let result = tokio::time::timeout(Duration::from_secs(20), async {
            let service = match server.transport.as_str() {
                "stdio" => {
                    platform::validate_executable(std::path::Path::new(&server.command))?;
                    let mut command = tokio::process::Command::new(&server.command);
                    command.args(&server.args).kill_on_drop(true);
                    platform::subprocess_environment(&mut command);
                    for (key, reference) in &server.env { command.env(key, secret_get(reference)?); }
                    let (transport, _) = TokioChildProcess::builder(command).stderr(std::process::Stdio::null()).spawn()?;
                    ().serve(transport).await.map_err(|_| anyhow::anyhow!("MCP initialization failed. Check executable, arguments and credentials."))?
                },
                "http" => {
                    validate_url(&server.url)?;
                    let mut headers = std::collections::HashMap::new();
                    for (key, reference) in &server.headers { headers.insert(http::HeaderName::from_bytes(key.as_bytes())?, http::HeaderValue::from_str(&secret_get(reference)?)?); }
                    if server.oauth {headers.insert(http::HeaderName::from_static("authorization"),http::HeaderValue::from_str(&format!("Bearer {}",oauth::access_token(id).await?))?);}
                    let http = reqwest::Client::builder().redirect(reqwest::redirect::Policy::none()).build()?;
                    let transport = StreamableHttpClientTransport::with_client(http, StreamableHttpClientTransportConfig::with_uri(server.url.clone()).custom_headers(headers));
                    ().serve(transport).await.map_err(|_| anyhow::anyhow!("MCP HTTP initialization failed. Check URL, authentication and Streamable HTTP support."))?
                },
                _ => anyhow::bail!("Legacy SSE is not supported by this SDK release. Choose a Streamable HTTP endpoint or local stdio server."),
            };
            let tools = service.list_all_tools().await.map_err(|_| anyhow::anyhow!("MCP discovery failed"))?;
            anyhow::ensure!(tools.len() <= 10000, "Too many tools");
            Ok::<_, anyhow::Error>((service, tools))
        }).await;
        match result {
            Ok(Ok((service, tools))) => {
                for tool in tools {
                    let name = format!("{}.{}", id, tool.name);
                    let mut tool = serde_json::to_value(tool)?;
                    tool["name"] = json!(name);
                    inner.tools.insert(name, tool);
                }
                inner.connections.insert(id.into(), service);
                inner.statuses.insert(id.into(), "Connected".into());
                if inner
                    .config
                    .activation
                    .as_ref()
                    .is_some_and(|j| j.server == id)
                {
                    let mut config = inner.config.clone();
                    config.diagnostics.event("auth_completion");
                    config.diagnostics.event("connection");
                    self.persist(&config)?;
                    inner.config = config;
                }
                Ok(())
            }
            other => {
                let message = match other {
                    Ok(Err(e)) => e.to_string(),
                    _ => "Connection timed out after 20 seconds".into(),
                };
                inner.statuses.insert(id.into(), message.clone());
                anyhow::bail!(message)
            }
        }
    }
    pub async fn catalog(&self) -> Vec<Value> {
        self.inner.lock().await.tools.values().cloned().collect()
    }
    pub async fn list(&self) -> Vec<Value> {
        let inner = self.inner.lock().await;
        inner
            .tools
            .iter()
            .filter(|(name, _)| inner.config.allowed(name))
            .map(|(_, tool)| tool.clone())
            .collect()
    }
    pub async fn call(&self, name: &str, args: Value) -> anyhow::Result<Value> {
        // The same lock serializes grants and call dispatch: no stale ACL cache.
        let mut inner = self.inner.lock().await;
        anyhow::ensure!(inner.config.allowed(name), "Tool not authorized");
        if let Some((server_id, _)) = name.split_once('.')
            && inner
                .config
                .servers
                .iter()
                .any(|s| s.id == server_id && s.oauth)
        {
            match oauth::needs_refresh(server_id) {
                Ok(false) => {}
                _ => {
                    self.connect_locked(&mut inner, server_id).await?;
                }
            }
        }
        let tool = inner
            .tools
            .get(name)
            .ok_or_else(|| anyhow::anyhow!("Tool unavailable; reconnect its connector"))?;
        jsonschema::validator_for(&tool["inputSchema"])
            .map_err(|_| anyhow::anyhow!("Invalid upstream schema"))?
            .validate(&args)
            .map_err(|_| anyhow::anyhow!("Arguments do not match tool schema"))?;
        let (server, original) = name
            .split_once('.')
            .ok_or_else(|| anyhow::anyhow!("Invalid tool name"))?;
        let upstream = inner
            .connections
            .get(server)
            .ok_or_else(|| anyhow::anyhow!("Connector disconnected"))?;
        let request = serde_json::from_value(json!({"name":original, "arguments":args}))?;
        let response =
            tokio::time::timeout(Duration::from_secs(30), upstream.call_tool(request)).await;
        // Count only dispatched calls, including upstream errors and timeouts.
        // Denied, unavailable, and invalid-argument requests never reach this point.
        let succeeded = matches!(&response, Ok(Ok(result)) if result.is_error != Some(true));
        inner.config.record_call(name, succeeded, unix_seconds());
        // A statistics write failure must never cause a completed mutation to be retried.
        let _ = self.persist(&inner.config);
        match response {
            Ok(Ok(response)) => Ok(serde_json::to_value(response)?),
            failed => {
                inner.statuses.insert(
                    server.into(),
                    "Reconnect required — check credentials and server availability".into(),
                );
                if let Some(connection) = inner.connections.remove(server) {
                    let _ = connection.cancel().await;
                }
                inner
                    .tools
                    .retain(|n, _| !n.starts_with(&format!("{server}.")));
                if failed.is_err() {
                    anyhow::bail!(
                        "Tool call timed out; it may have executed. Do not retry mutations blindly."
                    );
                }
                anyhow::bail!(
                    "Upstream tool call failed. Reconnect in Umbod; the call was not retried."
                )
            }
        }
    }

    pub async fn shutdown(&self) {
        let mut inner = self.inner.lock().await;
        for (_, connection) in std::mem::take(&mut inner.connections) {
            let _ = connection.cancel().await;
        }
        inner.tools.clear();
    }
}
pub mod http_api;
pub fn token_hash(token: &str) -> String {
    use sha2::Digest;
    format!("{:x}", sha2::Sha256::digest(token.as_bytes()))
}
pub fn new_token() -> String {
    format!(
        "{}{}",
        uuid::Uuid::new_v4().simple(),
        uuid::Uuid::new_v4().simple()
    )
}

fn unix_seconds() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

#[cfg(test)]
mod usage_tests {
    use super::*;
    #[test]
    fn daily_usage_preserves_legacy_totals_and_buckets_utc_days() {
        let mut config: Config = serde_json::from_value(serde_json::json!({
            "tool_usage":{"a.search":{"succeeded":7,"failed":1}}
        }))
        .unwrap();
        assert!(config.daily_calls.is_empty());
        config.record_call("a.search", true, 86_399);
        config.record_call("b.search", false, 86_400);
        config.record_call("a.search", true, 86_401);
        assert_eq!(config.daily_tracking_started, Some(0));
        assert_eq!(config.daily_calls, BTreeMap::from([(0, 1), (1, 2)]));
        assert_eq!(config.tool_usage["a.search"].succeeded, 9);
        let restored: Config =
            serde_json::from_slice(&serde_json::to_vec(&config).unwrap()).unwrap();
        assert_eq!(restored.daily_calls, config.daily_calls);
        assert_eq!(restored.daily_tracking_started, Some(0));
    }
}

#[cfg(test)]
mod credential_cache_tests {
    use super::*;
    #[test]
    fn cached_reads_do_not_need_a_keychain_item_and_delete_invalidates() {
        let reference = format!("upstream:cache-only:{}", uuid::Uuid::new_v4());
        // No Keychain item is created. Any attempted disk lookup would fail.
        SECRETS
            .lock()
            .unwrap()
            .insert(reference.clone(), Some("fixture".into()));
        for _ in 0..5 {
            assert_eq!(secret_get(&reference).unwrap(), "fixture");
        }
        secret_delete(&reference).unwrap();
        assert!(secret_get(&reference).is_err());
        assert_eq!(SECRETS.lock().unwrap().get(&reference), Some(&None));
        retry_secret_access();
        assert!(!SECRETS.lock().unwrap().contains_key(&reference));
    }
}
