mod support;
use axum::{
    Json, Router,
    extract::{Form, State},
    routing::{get, post},
};
use serde_json::json;
use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
};
use umbod_gateway::{Config, Runtime, Server, oauth};
#[derive(Clone)]
struct Fixture {
    base: String,
    challenge: Arc<Mutex<String>>,
    refresh: Arc<Mutex<usize>>,
}
async fn token(
    State(f): State<Fixture>,
    Form(p): Form<HashMap<String, String>>,
) -> Json<serde_json::Value> {
    if p.get("grant_type").unwrap() == "refresh_token" {
        assert_eq!(p.get("refresh_token").unwrap(), "fixture-refresh");
        *f.refresh.lock().unwrap() += 1;
    } else {
        use base64::Engine;
        use sha2::Digest;
        let challenge = base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(
            sha2::Sha256::digest(p.get("code_verifier").unwrap().as_bytes()),
        );
        assert_eq!(&challenge, &*f.challenge.lock().unwrap());
        assert_eq!(p.get("code").unwrap(), "fixture-code");
    }
    Json(
        json!({"access_token":"fixture-access","refresh_token":"fixture-refresh","token_type":"Bearer","expires_in":1}),
    )
}
#[tokio::test]
async fn fixture_discovery_pkce_state_callback_refresh_logout() {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let base = format!("http://{}", listener.local_addr().unwrap());
    let fixture = Fixture {
        base: base.clone(),
        challenge: Default::default(),
        refresh: Default::default(),
    };
    let app=Router::new()
      .route("/.well-known/oauth-protected-resource",get(|State(f):State<Fixture>|async move {Json(json!({"resource":format!("{}/mcp",f.base),"authorization_servers":[f.base]}))}))
      .route("/.well-known/oauth-authorization-server",get(|State(f):State<Fixture>|async move {Json(json!({"issuer":f.base,"authorization_endpoint":format!("{}/authorize",f.base),"token_endpoint":format!("{}/token",f.base),"registration_endpoint":format!("{}/register",f.base),"code_challenge_methods_supported":["S256"]}))}))
      .route("/register",post(||async {Json(json!({"client_id":"fixture-client","token_endpoint_auth_method":"none"}))}))
      .route("/token",post(token)).with_state(fixture.clone());
    let task = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    let id = uuid::Uuid::new_v4().simple().to_string();
    let mut config = Config::default();
    config.servers.push(Server {
        id: id.clone(),
        name: "OAuth fixture".into(),
        transport: "http".into(),
        url: format!("{base}/mcp"),
        ..Default::default()
    });
    let runtime = Runtime::memory(config);
    let auth = oauth::begin(&runtime, &id, "").await.unwrap();
    let url = url::Url::parse(&auth).unwrap();
    let params: HashMap<_, _> = url.query_pairs().into_owned().collect();
    assert_eq!(params["code_challenge_method"], "S256");
    *fixture.challenge.lock().unwrap() = params["code_challenge"].clone();
    let callback = &params["redirect_uri"];
    let http = reqwest::Client::new();
    assert_eq!(
        http.get(callback)
            .header("Host", "evil.example")
            .query(&[("state", "wrong"), ("code", "fixture-code")])
            .send()
            .await
            .unwrap()
            .status(),
        403
    );
    assert_eq!(
        http.get(callback)
            .header("Origin", "https://evil.example")
            .query(&[("state", "wrong"), ("code", "fixture-code")])
            .send()
            .await
            .unwrap()
            .status(),
        403
    );
    assert_eq!(
        http.get(callback)
            .query(&[("state", "wrong"), ("code", "fixture-code")])
            .send()
            .await
            .unwrap()
            .status(),
        400
    );
    assert_eq!(
        http.get(callback)
            .query(&[
                ("state", params["state"].as_str()),
                ("code", "fixture-code")
            ])
            .send()
            .await
            .unwrap()
            .status(),
        200
    );
    assert_eq!(oauth::access_token(&id).await.unwrap(), "fixture-access");
    oauth::refresh(&id).await.unwrap();
    assert!(*fixture.refresh.lock().unwrap() >= 1);
    oauth::logout(&runtime, &id).await.unwrap();
    assert!(oauth::access_token(&id).await.is_err());
    let auth = oauth::begin(&runtime, &id, "").await.unwrap();
    let denied_url = url::Url::parse(&auth).unwrap();
    let params: HashMap<_, _> = denied_url.query_pairs().into_owned().collect();
    assert_eq!(
        http.get(&params["redirect_uri"])
            .query(&[
                ("state", params["state"].as_str()),
                ("error", "access_denied")
            ])
            .send()
            .await
            .unwrap()
            .status(),
        400
    );
    assert!(
        !runtime.inner.lock().await.oauth_pending.contains_key(&id),
        "denial must end pending sign-in"
    );
    assert!(runtime.inner.lock().await.statuses[&id].contains("cancelled"));
    task.abort();
}
#[tokio::test]
async fn expired_oauth_refreshes_and_replaces_live_transport_before_dispatch() {
    use umbod_gateway::{Client, http_api, secret_delete, secret_set, token_hash};
    let mut upstream_config = Config::default();
    upstream_config.clients.push(Client {
        id: "oauth-fixture".into(),
        token_hash: token_hash("old-fixture-access"),
        ..Default::default()
    });
    upstream_config.servers.push(Server {
        id: "source".into(),
        transport: "stdio".into(),
        command: support::python(),
        args: vec![format!(
            "{}/scripts/fixture_issues.py",
            env!("CARGO_MANIFEST_DIR")
        )],
        ..Default::default()
    });
    upstream_config.grant("source.search_issues", true);
    let upstream = Runtime::memory(upstream_config);
    upstream.connect("source").await.unwrap();
    let running = http_api::start(upstream.clone(), "fixture-admin".into())
        .await
        .unwrap();
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let endpoint = format!("http://{}/token", listener.local_addr().unwrap());
    let app=Router::new().route("/token",post(||async{Json(json!({"access_token":"new-fixture-access","refresh_token":"fixture-refresh","token_type":"Bearer","expires_in":3600}))}));
    let task = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    let id = uuid::Uuid::new_v4().simple().to_string();
    let reference = format!("upstream:oauth:{id}");
    let mut document = json!({"resource":format!("http://{}/mcp",running.gateway),"client_id":"fixture","token_endpoint":endpoint,"access":"old-fixture-access","refresh":"fixture-refresh","expires":u64::MAX});
    secret_set(&reference, &document.to_string()).unwrap();
    let mut config = Config::default();
    config.servers.push(Server {
        id: id.clone(),
        transport: "http".into(),
        url: format!("http://{}/mcp", running.gateway),
        oauth: true,
        ..Default::default()
    });
    let name = format!("{id}.source.search_issues");
    config.grant(&name, true);
    let runtime = Runtime::memory(config);
    runtime.connect(&id).await.unwrap();
    upstream.inner.lock().await.config.clients[0].token_hash = token_hash("new-fixture-access");
    document["expires"] = json!(0);
    secret_set(&reference, &document.to_string()).unwrap();
    assert!(
        runtime.call(&name, json!({})).await.is_ok(),
        "expired transport must refresh and reconnect before call"
    );
    assert_eq!(runtime.inner.lock().await.statuses[&id], "Connected");
    upstream.inner.lock().await.config.clients[0].token_hash = token_hash("revoked-fixture-access");
    assert!(runtime.call(&name, json!({})).await.is_err());
    assert_ne!(
        runtime.inner.lock().await.statuses[&id],
        "Connected",
        "transport errors must show reconnect state"
    );
    runtime.shutdown().await;
    upstream.shutdown().await;
    running.stop.cancel();
    task.abort();
    secret_delete(&reference).unwrap();
}
#[tokio::test]
async fn logout_persists_signed_out_state_for_restart() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("config.json");
    let id = uuid::Uuid::new_v4().simple().to_string();
    let mut config = Config::default();
    config.servers.push(Server {
        id: id.clone(),
        transport: "http".into(),
        url: "https://example.com/mcp".into(),
        oauth: true,
        ..Default::default()
    });
    config.save(&path).unwrap();
    let runtime = Runtime::persistent(path.clone()).unwrap();
    oauth::logout(&runtime, &id).await.unwrap();
    assert!(
        !Config::load(&path).unwrap().servers[0].oauth,
        "restart must not attempt to refresh deleted authorization"
    );
}
