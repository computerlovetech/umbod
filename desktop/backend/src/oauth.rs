//! OAuth for public native clients. Secrets persist only in Keychain.
use crate::*;
use axum::{Router, extract::Query, response::IntoResponse, routing::get};
use oauth2::{
    AuthType, AuthUrl, AuthorizationCode, ClientId, CsrfToken, PkceCodeChallenge, RedirectUrl,
    RefreshToken, TokenResponse, TokenUrl, basic::BasicClient,
};
use std::collections::HashMap;
use subtle::ConstantTimeEq;
#[derive(Clone, Serialize, Deserialize)]
struct Document {
    resource: String,
    client_id: String,
    token_endpoint: String,
    access: String,
    refresh: Option<String>,
    expires: u64,
}
fn now() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}
fn account(id: &str) -> String {
    format!("upstream:oauth:{id}")
}
fn token_client() -> anyhow::Result<oauth2::reqwest::Client> {
    Ok(oauth2::reqwest::Client::builder()
        .redirect(oauth2::reqwest::redirect::Policy::none())
        .timeout(Duration::from_secs(20))
        .build()?)
}
async fn metadata(http: &reqwest::Client, url: url::Url) -> anyhow::Result<Value> {
    let response = http
        .get(url)
        .send()
        .await
        .map_err(|_| anyhow::anyhow!("OAuth discovery request failed"))?;
    anyhow::ensure!(
        response.status().is_success(),
        "OAuth metadata unavailable. This provider must publish discovery metadata."
    );
    let bytes = response
        .bytes()
        .await
        .map_err(|_| anyhow::anyhow!("OAuth metadata response failed"))?;
    anyhow::ensure!(bytes.len() < 256 * 1024, "OAuth metadata too large");
    serde_json::from_slice(&bytes).map_err(|_| anyhow::anyhow!("Invalid OAuth metadata"))
}
fn field<'a>(value: &'a Value, key: &str) -> anyhow::Result<&'a str> {
    value[key]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("OAuth metadata missing {key}"))
}
pub async fn begin(runtime: &Runtime, id: &str, manual_client: &str) -> anyhow::Result<String> {
    let server = runtime
        .inner
        .lock()
        .await
        .config
        .servers
        .iter()
        .find(|s| s.id == id)
        .cloned()
        .ok_or_else(|| anyhow::anyhow!("Server not found"))?;
    anyhow::ensure!(
        server.transport == "http",
        "Browser sign-in requires a remote HTTP server"
    );
    let resource = validate_url(&server.url)?;
    let http = reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(Duration::from_secs(15))
        .build()?;
    let root = resource.join("/")?;
    let path = format!(
        "/.well-known/oauth-protected-resource{}",
        resource.path().trim_end_matches('/')
    );
    let protected = match metadata(&http, root.join(&path)?).await {
        Ok(value) => value,
        Err(_) => metadata(&http, root.join(".well-known/oauth-protected-resource")?).await?,
    };
    anyhow::ensure!(
        field(&protected, "resource")?.trim_end_matches('/') == server.url.trim_end_matches('/'),
        "OAuth resource metadata does not match the configured MCP endpoint"
    );
    let issuer = protected["authorization_servers"]
        .as_array()
        .and_then(|a| a.first())
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow::anyhow!("No OAuth authorization server advertised"))?;
    let issuer_url = validate_url(issuer)?;
    let metadata_path = format!(
        "/.well-known/oauth-authorization-server{}",
        issuer_url.path().trim_end_matches('/')
    );
    let meta = metadata(&http, issuer_url.join(&metadata_path)?).await?;
    anyhow::ensure!(field(&meta, "issuer")? == issuer, "OAuth issuer mismatch");
    anyhow::ensure!(
        meta["code_challenge_methods_supported"]
            .as_array()
            .is_some_and(|a| a.iter().any(|s| s == "S256")),
        "Provider does not advertise PKCE S256. Use a compatible provider."
    );
    let authorization = validate_url(field(&meta, "authorization_endpoint")?)?;
    let token_endpoint = validate_url(field(&meta, "token_endpoint")?)?;
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await?;
    let callback_host = listener.local_addr()?.to_string();
    let callback = format!("http://{}/oauth/callback", listener.local_addr()?);
    let client_id = if !manual_client.trim().is_empty() {
        manual_client.to_owned()
    } else {
        let registration=meta["registration_endpoint"].as_str().ok_or_else(||anyhow::anyhow!("This provider needs a manually registered public client ID. Register the loopback redirect URI and enter the client ID."))?;
        let response=http.post(validate_url(registration)?).json(&json!({"client_name":"Umbod Desktop","redirect_uris":[callback],"grant_types":["authorization_code","refresh_token"],"response_types":["code"],"token_endpoint_auth_method":"none"})).send().await.map_err(|_|anyhow::anyhow!("Dynamic registration failed; enter a manually registered public client ID"))?;
        anyhow::ensure!(
            response.status().is_success(),
            "Dynamic registration rejected; enter a manually registered public client ID"
        );
        let registration: Value = response
            .json()
            .await
            .map_err(|_| anyhow::anyhow!("Invalid registration response"))?;
        anyhow::ensure!(
            registration.get("client_secret").is_none(),
            "Confidential client registration is unsupported. Supply a public native client ID."
        );
        field(&registration, "client_id")?.to_owned()
    };
    let client = BasicClient::new(ClientId::new(client_id.clone()))
        .set_auth_type(AuthType::RequestBody)
        .set_auth_uri(AuthUrl::new(authorization.to_string())?)
        .set_token_uri(TokenUrl::new(token_endpoint.to_string())?)
        .set_redirect_uri(RedirectUrl::new(callback)?);
    let (challenge, verifier) = PkceCodeChallenge::new_random_sha256();
    let (auth_url, state) = client
        .authorize_url(CsrfToken::new_random)
        .set_pkce_challenge(challenge)
        .add_extra_param("resource", server.url.clone())
        .url();
    let pending = Arc::new(Mutex::new(Some((client, verifier))));
    let done = tokio_util::sync::CancellationToken::new();
    let generation = new_token();
    {
        let mut inner = runtime.inner.lock().await;
        inner.oauth_pending.insert(id.into(), generation.clone());
        inner.statuses.insert(
            id.into(),
            "Waiting for browser sign-in (3 minute timeout)".into(),
        );
    }
    let runtime = runtime.clone();
    let id = id.to_owned();
    let resource = server.url;
    let endpoint = token_endpoint.to_string();
    let done_handler = done.clone();
    let expiry_runtime = runtime.clone();
    let expiry_id = id.clone();
    let expiry_generation = generation.clone();
    let app=Router::new().route("/oauth/callback",get(move |headers:http::HeaderMap,Query(params):Query<HashMap<String,String>>| {
        let host_allowed=headers.get("host").and_then(|h|h.to_str().ok())==Some(callback_host.as_str()) && !headers.contains_key("origin");
        let (pending,done,runtime,id,generation,resource,endpoint,client_id,state)=(pending.clone(),done_handler.clone(),runtime.clone(),id.clone(),generation.clone(),resource.clone(),endpoint.clone(),client_id.clone(),state.secret().clone());
        async move {
            if !host_allowed {return (http::StatusCode::FORBIDDEN,"Invalid callback host or origin").into_response();}
            if !params.get("state").is_some_and(|s|bool::from(s.as_bytes().ct_eq(state.as_bytes()))) {return (http::StatusCode::BAD_REQUEST,"Invalid OAuth state").into_response();}
            if params.get("iss").is_some_and(|s|s!=issuer_url.as_str()) {return (http::StatusCode::BAD_REQUEST,"Invalid OAuth issuer").into_response();}
            let code=match params.get("code") {Some(code)=>code.clone(),None=>{
                let mut inner=runtime.inner.lock().await;
                if inner.oauth_pending.get(&id)==Some(&generation) {inner.oauth_pending.remove(&id);inner.statuses.insert(id,"Sign-in cancelled — retry browser sign-in".into());}
                done.cancel();return (http::StatusCode::BAD_REQUEST,"Authorization was denied or no code was returned").into_response();
            }};
            let mut pending=pending.lock().await;
            let Some((client,verifier))=pending.take() else {return (http::StatusCode::BAD_REQUEST,"Callback already used").into_response()};
            let result=async {
                let token=client.exchange_code(AuthorizationCode::new(code)).set_pkce_verifier(verifier).add_extra_param("resource",&resource).request_async(&token_client()?).await.map_err(|_|anyhow::anyhow!("OAuth code exchange failed. Reconnect and check provider registration."))?;
                let document=Document{resource,client_id,token_endpoint:endpoint,access:token.access_token().secret().clone(),refresh:token.refresh_token().map(|t|t.secret().clone()),expires:now()+token.expires_in().map(|d|d.as_secs()).unwrap_or(3600)};
                let mut inner=runtime.inner.lock().await;
                anyhow::ensure!(inner.oauth_pending.get(&id)==Some(&generation),"Sign-in was cancelled or superseded");
                secret_set(&account(&id),&serde_json::to_string(&document)?)?;
                let mut config=inner.config.clone();
                let server=config.servers.iter_mut().find(|s|s.id==id).ok_or_else(||anyhow::anyhow!("Server removed"))?;server.oauth=true;
                runtime.persist(&config)?;inner.config=config;inner.oauth_pending.remove(&id);inner.statuses.insert(id.clone(),"Signed in — Connect to discover tools".into());
                Ok::<_,anyhow::Error>(())
            }.await;
            if result.is_err() {
                let mut inner=runtime.inner.lock().await;
                if inner.oauth_pending.get(&id)==Some(&generation) {inner.oauth_pending.remove(&id);inner.statuses.insert(id,"Sign-in failed — retry and check provider registration".into());}
            }
            done.cancel();
            match result {Ok(())=>(http::StatusCode::OK,"Sign-in complete. Return to Umbod and Connect.").into_response(),Err(_)=>(http::StatusCode::BAD_REQUEST,"Sign-in failed. Return to Umbod and reconnect; verify provider registration and Keychain access.").into_response()}
        }
    }));
    tokio::spawn(async move {
        let _=axum::serve(listener,app).with_graceful_shutdown(async move {tokio::select! {_=done.cancelled()=>{},_=tokio::time::sleep(Duration::from_secs(180))=>{
            let mut inner=expiry_runtime.inner.lock().await;
            if inner.oauth_pending.get(&expiry_id)==Some(&expiry_generation) {inner.oauth_pending.remove(&expiry_id);inner.statuses.insert(expiry_id,"Sign-in expired — retry browser sign-in".into());}
        }}}).await;
    });
    Ok(auth_url.to_string())
}
pub async fn refresh(id: &str) -> anyhow::Result<String> {
    let mut document: Document = serde_json::from_str(&secret_get(&account(id))?)?;
    let refresh = document
        .refresh
        .clone()
        .ok_or_else(|| anyhow::anyhow!("No refresh token; sign in again"))?;
    let client = BasicClient::new(ClientId::new(document.client_id.clone()))
        .set_auth_type(AuthType::RequestBody)
        .set_token_uri(TokenUrl::new(document.token_endpoint.clone())?);
    let token = client
        .exchange_refresh_token(&RefreshToken::new(refresh))
        .add_extra_param("resource", &document.resource)
        .request_async(&token_client()?)
        .await
        .map_err(|_| anyhow::anyhow!("Refresh failed. Sign in again."))?;
    document.access = token.access_token().secret().clone();
    if let Some(refresh) = token.refresh_token() {
        document.refresh = Some(refresh.secret().clone());
    }
    document.expires = now() + token.expires_in().map(|d| d.as_secs()).unwrap_or(3600);
    secret_set(&account(id), &serde_json::to_string(&document)?)?;
    Ok(document.access)
}
pub fn needs_refresh(id: &str) -> anyhow::Result<bool> {
    let document: Document = serde_json::from_str(&secret_get(&account(id))?)?;
    Ok(document.expires <= now().saturating_add(30))
}
pub async fn refresh_connection(runtime: &Runtime, id: &str) -> anyhow::Result<()> {
    let mut inner = runtime.inner.lock().await;
    anyhow::ensure!(
        inner.config.servers.iter().any(|s| s.id == id && s.oauth),
        "Sign in before refreshing"
    );
    if let Some(connection) = inner.connections.remove(id) {
        let _ = connection.cancel().await;
    }
    inner.tools.retain(|n, _| !n.starts_with(&format!("{id}.")));
    if refresh(id).await.is_err() {
        inner
            .statuses
            .insert(id.into(), "Reconnect required — sign in again".into());
        anyhow::bail!("Refresh failed. Sign in again; no call was sent.");
    }
    runtime.connect_locked(&mut inner, id).await
}
pub async fn access_token(id: &str) -> anyhow::Result<String> {
    let document: Document = serde_json::from_str(&secret_get(&account(id))?)?;
    if document.expires <= now() + 30 {
        refresh(id).await
    } else {
        Ok(document.access)
    }
}
pub async fn logout(runtime: &Runtime, id: &str) -> anyhow::Result<()> {
    let mut inner = runtime.inner.lock().await;
    inner.oauth_pending.remove(id);
    secret_delete(&account(id))?;
    if let Some(connection) = inner.connections.remove(id) {
        let _ = connection.cancel().await;
    }
    inner.tools.retain(|n, _| !n.starts_with(&format!("{id}.")));
    inner.statuses.insert(id.into(), "Signed out".into());
    let mut config = inner.config.clone();
    if let Some(server) = config.servers.iter_mut().find(|s| s.id == id) {
        server.oauth = false;
    }
    runtime.persist(&config)?;
    inner.config = config;
    Ok(())
}
