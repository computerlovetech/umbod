use rmcp::{
    ErrorData, RoleClient, RoleServer, ServerHandler, ServiceExt,
    model::*,
    service::{RequestContext, RunningService},
    transport::{
        StreamableHttpClientTransport, streamable_http_client::StreamableHttpClientTransportConfig,
    },
};
use serde_json::{Value, json};
use std::{path::PathBuf, sync::Arc};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt};
use umbod_gateway::*;
fn data_dir() -> anyhow::Result<PathBuf> {
    profile::current().directory()
}
#[tokio::main]
async fn main() {
    if let Err(error) = run().await {
        if std::env::args().nth(1).as_deref() == Some("serve") {
            println!("{}", json!({"error":error.to_string()}));
        }
        eprintln!("Umbod: {error}");
        std::process::exit(1);
    }
}
async fn run() -> anyhow::Result<()> {
    let args: Vec<String> = std::env::args().collect();
    let executable = std::env::current_exe()?;
    let adjacent = executable.with_file_name("umbod-profile");
    let marker = if adjacent.exists() {
        adjacent
    } else {
        executable
            .parent()
            .unwrap()
            .join("../Resources/umbod-profile")
    };
    let selected = if let Some(index) = args.iter().position(|arg| arg == "--profile") {
        profile::Profile::parse(
            args.get(index + 1)
                .ok_or_else(|| anyhow::anyhow!("Missing profile"))?,
        )?
    } else if marker.exists() {
        profile::Profile::parse(&std::fs::read_to_string(marker)?)?
    } else {
        // Unbundled cargo builds are development tools, never the release profile.
        profile::Profile::Dev
    };
    profile::initialize(selected)?;
    match args.get(1).map(String::as_str) {
        Some("serve") => {
            let directory = if let Some(index) = args.iter().position(|arg| arg == "--data-dir") {
                PathBuf::from(
                    args.get(index + 1)
                        .ok_or_else(|| anyhow::anyhow!("Missing data directory"))?,
                )
            } else {
                data_dir()?
            };
            let mut lines = tokio::io::BufReader::new(tokio::io::stdin()).lines();
            let startup: Value = serde_json::from_str(
                &lines
                    .next_line()
                    .await?
                    .ok_or_else(|| anyhow::anyhow!("Owner startup input missing"))?,
            )?;
            let token = startup["admin_token"]
                .as_str()
                .filter(|s| s.len() >= 16)
                .ok_or_else(|| anyhow::anyhow!("Missing owner token"))?;
            platform::private_dir(&directory)?;
            let _owner_lock = platform::owner_lock(&directory)?;
            let runtime = Runtime::persistent(directory.join("config.json"))?;
            {
                runtime.persist(&runtime.inner.lock().await.config)?;
            }
            let running = http_api::start(runtime.clone(), token.into()).await?;
            let ready = json!({"gateway":running.gateway.to_string(),"management":running.management.to_string(),"pid":std::process::id()});
            let mut record = ready.clone();
            if args.iter().any(|arg| arg == "--persistent") {
                record["admin_token"] = json!(token);
                record["profile"] = json!(selected.name());
            }
            platform::atomic_write(
                &directory.join("runtime.json"),
                serde_json::to_string(&record)?.as_bytes(),
            )?;
            let mut stdout = tokio::io::stdout();
            stdout.write_all(format!("{ready}\n").as_bytes()).await?;
            stdout.flush().await?;
            let reconnect = runtime.clone();
            tokio::spawn(async move {
                let ids: Vec<_> = reconnect
                    .inner
                    .lock()
                    .await
                    .config
                    .servers
                    .iter()
                    .map(|s| s.id.clone())
                    .collect();
                for id in ids {
                    let _ = reconnect.connect(&id).await;
                }
            });
            let persistent = args.iter().any(|arg| arg == "--persistent");

            tokio::select! {
                _=async { if persistent { std::future::pending::<()>().await; } else { while let Ok(Some(_))=lines.next_line().await {} } }=>{},
                _=tokio::signal::ctrl_c()=>{},
                _=terminate_signal()=>{},
                _=running.stop.cancelled()=>{},
            }
            running.stop.cancel();
            let _ =
                tokio::time::timeout(std::time::Duration::from_secs(3), runtime.shutdown()).await;
            // Only remove our runtime record; another owner may have started.
            if std::fs::read_to_string(directory.join("runtime.json"))
                .ok()
                .and_then(|s| serde_json::from_str::<Value>(&s).ok())
                .is_some_and(|v| v["pid"] == std::process::id())
            {
                let _ = std::fs::remove_file(directory.join("runtime.json"));
            }
            Ok(())
        }
        Some("bridge") => {
            // New configurations need no client ID. Accept old bridge IDs for compatibility.
            let legacy_id = args.get(2).filter(|arg| !arg.starts_with("--"));
            let directory = if let Some(index) = args.iter().position(|arg| arg == "--data-dir") {
                PathBuf::from(
                    args.get(index + 1)
                        .ok_or_else(|| anyhow::anyhow!("Missing data directory"))?,
                )
            } else {
                data_dir()?
            };
            let config = Config::load(&directory.join("config.json"))?;
            let id = legacy_id
                .map(String::as_str)
                .or_else(|| {
                    config
                        .connection
                        .as_ref()
                        .map(|connection| connection.id.as_str())
                })
                .ok_or_else(|| {
                    anyhow::anyhow!(
                        "Open Umbod and copy its connection configuration from Settings → MCP"
                    )
                })?;
            let ready: Value = serde_json::from_slice(
                &std::fs::read(directory.join("runtime.json"))
                    .map_err(|_| anyhow::anyhow!("Open Umbod Desktop before using this client"))?,
            )?;
            let address = ready["gateway"]
                .as_str()
                .ok_or_else(|| anyhow::anyhow!("Invalid runtime address"))?;
            let parsed: std::net::SocketAddr = address.parse()?;
            anyhow::ensure!(parsed.ip().is_loopback(), "Gateway must be loopback");
            let http = reqwest::Client::builder()
                .redirect(reqwest::redirect::Policy::none())
                .build()?;
            let token = if let Some(admin) = ready["admin_token"].as_str() {
                let management: std::net::SocketAddr = ready["management"]
                    .as_str()
                    .ok_or_else(|| anyhow::anyhow!("Invalid management address"))?
                    .parse()?;
                anyhow::ensure!(
                    management.ip() == std::net::Ipv4Addr::LOCALHOST,
                    "Management must be loopback"
                );
                let response = http
                    .post(format!("http://{management}/manage"))
                    .bearer_auth(admin)
                    .json(&json!({"action":"connection_token","id":id}))
                    .send()
                    .await?
                    .error_for_status()?;
                let body: Value = response.json().await?;
                body["token"]
                    .as_str()
                    .ok_or_else(|| anyhow::anyhow!("Connection credential unavailable"))?
                    .to_owned()
            } else {
                // Compatibility for owned test gateways and older releases.
                secret_get(&format!("client:{id}"))?
            };
            let transport = StreamableHttpClientTransport::with_client(
                http,
                StreamableHttpClientTransportConfig::with_uri(format!("http://{address}/mcp"))
                    .auth_header(token),
            );
            let upstream = ().serve(transport).await.map_err(|_| {
                anyhow::anyhow!(
                    "Cannot connect to Umbod. Open the app and copy its connection configuration again."
                )
            })?;
            let bridge = Bridge(Arc::new(upstream));
            let service = bridge.serve(rmcp::transport::stdio()).await?;
            service.waiting().await?;
            Ok(())
        }
        _ => anyhow::bail!("Usage: umbod-gateway serve | bridge [LEGACY_CLIENT_ID]"),
    }
}
#[derive(Clone)]
struct Bridge(Arc<RunningService<RoleClient, ()>>);
impl ServerHandler for Bridge {
    fn get_info(&self) -> ServerConfig {
        ServerConfig::new(ServerCapabilities::builder().enable_tools().build())
    }
    async fn list_tools(
        &self,
        _: Option<PaginatedRequestParams>,
        _: RequestContext<RoleServer>,
    ) -> Result<ListToolsResult, ErrorData> {
        let tools = self
            .0
            .list_all_tools()
            .await
            .map_err(|_| ErrorData::internal_error("Gateway discovery failed", None))?;
        serde_json::from_value(json!({"tools":tools}))
            .map_err(|_| ErrorData::internal_error("Invalid catalog", None))
    }
    async fn call_tool(
        &self,
        request: CallToolRequestParams,
        _: RequestContext<RoleServer>,
    ) -> Result<CallToolResponse, ErrorData> {
        self.0
            .call_tool(request)
            .await
            .map(Into::into)
            .map_err(|_| ErrorData::invalid_request("Gateway denied or failed the tool call", None))
    }
}

async fn terminate_signal() {
    #[cfg(unix)]
    {
        if let Ok(mut signal) =
            tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
        {
            signal.recv().await;
        }
    }
    #[cfg(windows)]
    {
        std::future::pending::<()>().await;
    }
}
