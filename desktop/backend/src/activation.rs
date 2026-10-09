//! Local activation state. No prompts, arguments, result bodies, or credentials.
use crate::*;
pub const ENDPOINT: &str = "https://api.githubcopilot.com/mcp/x/issues/readonly";
#[derive(Clone, Default, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Journey {
    pub client: String,
    pub server: String,
    pub configured: bool,
    pub activated: bool,
    pub fixture: bool,
}
#[derive(Clone, Default, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Diagnostics {
    pub enabled: bool,
    pub events: BTreeMap<String, u64>,
    pub started_at: Option<u64>,
    pub first_call_seconds: Option<u64>,
    pub last_call_at: Option<u64>,
}
pub fn now() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}
impl Diagnostics {
    pub fn event(&mut self, event: &str) {
        if self.enabled {
            let n = self.events.entry(event.into()).or_default();
            *n = n.saturating_add(1);
        }
    }
}
pub async fn start(runtime: &Runtime, diagnostics: bool) -> anyhow::Result<Value> {
    let mut inner = runtime.inner.lock().await;
    if let Some(journey) = &inner.config.activation {
        return Ok(serde_json::to_value(journey)?);
    }
    let id = uuid::Uuid::new_v4().simple().to_string();
    let server = uuid::Uuid::new_v4().simple().to_string();
    let token = new_token();
    secret_set(&format!("client:{id}"), &token)?;
    let mut config = inner.config.clone();
    config.clients.push(Client {
        id: id.clone(),
        name: "Claude Desktop · GitHub issues".into(),
        token_hash: token_hash(&token),
    });
    config.servers.push(Server {
        id: server.clone(),
        name: "GitHub · read issues".into(),
        transport: "http".into(),
        url: ENDPOINT.into(),
        headers: BTreeMap::from([("Authorization".into(), format!("upstream:{server}:pat"))]),
        ..Default::default()
    });
    let journey = Journey {
        client: id.clone(),
        server,
        ..Default::default()
    };
    config.activation = Some(journey.clone());
    config.diagnostics.enabled = diagnostics;
    if diagnostics {
        config.diagnostics.started_at = Some(now());
    }
    for event in [
        "onboarding_start",
        "client_selection",
        "integration_selection",
    ] {
        config.diagnostics.event(event);
    }
    if let Err(error) = runtime.persist(&config) {
        let _ = secret_delete(&format!("client:{id}"));
        return Err(error);
    }
    inner.config = config;
    Ok(serde_json::to_value(journey)?)
}
/// Invoked only after a successful result has crossed the authenticated MCP handler.
/// Possession of this identity is evidence of its use, not proof of a client product's brand.
pub async fn downstream(runtime: &Runtime, client: &str, tool: &str) -> anyhow::Result<()> {
    let mut inner = runtime.inner.lock().await;
    let mut config = inner.config.clone();
    let Some(journey) = &mut config.activation else {
        return Ok(());
    };
    if !journey.configured
        || journey.client != client
        || !["issue_read", "list_issues", "search_issues"]
            .iter()
            .any(|t| tool == format!("{}.{t}", journey.server))
    {
        return Ok(());
    }
    let Some(server) = config.servers.iter().find(|s| s.id == journey.server) else {
        return Ok(());
    };
    journey.fixture |= server.url != ENDPOINT || server.transport != "http";
    journey.activated = true;
    let diagnostics = &mut config.diagnostics;
    diagnostics.event(if journey.fixture {
        "fixture_successful_call"
    } else {
        "downstream_successful_call"
    });
    if diagnostics.enabled {
        let now = now();
        diagnostics.last_call_at = Some(now);
        if diagnostics.first_call_seconds.is_none() {
            diagnostics.first_call_seconds = diagnostics
                .started_at
                .map(|start| now.saturating_sub(start));
        }
    }
    runtime.persist(&config)?;
    inner.config = config;
    Ok(())
}
