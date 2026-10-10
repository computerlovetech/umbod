//! Explicit, optimistic client configuration transaction. Backups stay local, mode 0600.
use crate::*;
use std::{io::Write, path::Path};
#[derive(Clone, Serialize, Deserialize)]
pub struct Receipt {
    pub path: PathBuf,
    pub backup: PathBuf,
    pub before_hash: String,
    pub after_hash: String,
    pub existed: bool,
}
pub struct Preview {
    pub id: String,
    pub receipt: Receipt,
    pub before: Vec<u8>,
    pub after: Vec<u8>,
}
fn safe_path(path: &Path) -> anyhow::Result<()> {
    anyhow::ensure!(path.is_absolute(), "Configuration path must be absolute");
    anyhow::ensure!(
        !path
            .components()
            .any(|c| c == std::path::Component::ParentDir),
        "Invalid path"
    );
    for part in path.ancestors() {
        if let Ok(meta) = std::fs::symlink_metadata(part) {
            anyhow::ensure!(
                !meta.file_type().is_symlink(),
                "Symbolic links are not supported for client configuration"
            );
        }
    }
    Ok(())
}
fn read(path: &Path) -> anyhow::Result<Option<Vec<u8>>> {
    safe_path(path)?;
    match std::fs::read(path) {
        Ok(bytes) => {
            anyhow::ensure!(
                bytes.len() <= 1024 * 1024,
                "Client configuration is too large"
            );
            Ok(Some(bytes))
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(_) => anyhow::bail!("Cannot read client configuration"),
    }
}
fn hash(bytes: &[u8]) -> String {
    use sha2::Digest;
    format!("{:x}", sha2::Sha256::digest(bytes))
}
fn write_new(path: &Path, bytes: &[u8]) -> anyhow::Result<()> {
    let mut file = platform::private_file(path, true)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    Ok(())
}
fn replace(path: &Path, bytes: &[u8]) -> anyhow::Result<()> {
    safe_path(path)?;
    let temp = path.with_file_name(format!(".umbod-{}.tmp", uuid::Uuid::new_v4()));
    let result = (|| {
        write_new(&temp, bytes)?;
        platform::replace(&temp, path)?;
        Ok(())
    })();
    let _ = std::fs::remove_file(temp);
    result
}
pub async fn preview(runtime: &Runtime, path: PathBuf, command: &str) -> anyhow::Result<Value> {
    anyhow::ensure!(
        Path::new(command).is_absolute() && Path::new(command).is_file(),
        "Bundled bridge executable is missing"
    );
    let mut inner = runtime.inner.lock().await;
    anyhow::ensure!(
        inner.config.client_setup.is_none(),
        "Undo the existing Umbod configuration before replacing it"
    );
    let journey = inner
        .config
        .activation
        .as_ref()
        .ok_or_else(|| anyhow::anyhow!("Start setup first"))?;
    let old = read(&path)?;
    let before = old.clone().unwrap_or_default();
    let mut doc: Value = if old.is_none() {
        json!({})
    } else {
        serde_json::from_slice(&before).map_err(|_| {
            anyhow::anyhow!("Client configuration is invalid JSON; repair it before setup")
        })?
    };
    let object = doc
        .as_object_mut()
        .ok_or_else(|| anyhow::anyhow!("Client configuration must be an object"))?;
    let servers = object
        .entry("mcpServers")
        .or_insert(json!({}))
        .as_object_mut()
        .ok_or_else(|| anyhow::anyhow!("mcpServers must be an object"))?;
    let key = format!("umbod-{}", journey.client);
    anyhow::ensure!(
        !servers.contains_key(&key),
        "Umbod entry already exists; review it in the client configuration"
    );
    let mut args = vec![json!("bridge"), json!(journey.client)];
    if let Some(config) = &runtime.path {
        args.push(json!("--data-dir"));
        args.push(json!(config.parent().unwrap()));
    }
    let entry = json!({"command":command,"args":args});
    servers.insert(key.clone(), entry.clone());
    let after = serde_json::to_vec_pretty(&doc)?;
    let id = uuid::Uuid::new_v4().to_string();
    let receipt = Receipt {
        path: path.clone(),
        backup: path.with_file_name(format!(".umbod-{id}.backup")),
        before_hash: hash(&before),
        after_hash: hash(&after),
        existed: old.is_some(),
    };
    let response =
        json!({"id":id,"path":path,"entry_name":key,"entry":entry,"backup":receipt.backup});
    inner.client_preview = Some(Preview {
        id,
        receipt,
        before,
        after,
    });
    Ok(response)
}
pub async fn apply(runtime: &Runtime, id: &str, consent: bool) -> anyhow::Result<Value> {
    anyhow::ensure!(consent, "Explicit client configuration consent required");
    let mut inner = runtime.inner.lock().await;
    let p = inner
        .client_preview
        .as_ref()
        .ok_or_else(|| anyhow::anyhow!("Preview configuration first"))?;
    anyhow::ensure!(p.id == id, "Preview expired; preview again");
    let current = read(&p.receipt.path)?;
    anyhow::ensure!(
        current.is_some() == p.receipt.existed && current.unwrap_or_default() == p.before,
        "Client configuration changed; preview again"
    );
    let parent = p.receipt.path.parent().unwrap();
    if !parent.exists() {
        std::fs::create_dir_all(parent)?;
    }
    safe_path(&p.receipt.backup)?;
    write_new(&p.receipt.backup, &p.before)?;
    replace(&p.receipt.path, &p.after)?;
    let result = (|| {
        anyhow::ensure!(
            read(&p.receipt.path)? == Some(p.after.clone()),
            "Configuration verification failed"
        );
        let mut config = inner.config.clone();
        config.client_setup = Some(p.receipt.clone());
        config
            .activation
            .as_mut()
            .ok_or_else(|| anyhow::anyhow!("Setup cancelled"))?
            .configured = true;
        config.diagnostics.event("client_configuration");
        runtime.persist(&config)?;
        Ok::<_, anyhow::Error>(config)
    })();
    match result {
        Ok(config) => {
            let response = json!({"backup":p.receipt.backup});
            inner.config = config;
            inner.client_preview = None;
            Ok(response)
        }
        Err(error) => {
            if p.receipt.existed {
                replace(&p.receipt.path, &p.before)?;
            } else {
                std::fs::remove_file(&p.receipt.path)?;
            }
            Err(error)
        }
    }
}
pub async fn undo(runtime: &Runtime, consent: bool) -> anyhow::Result<Value> {
    anyhow::ensure!(consent, "Explicit restore consent required");
    let mut inner = runtime.inner.lock().await;
    let receipt = inner
        .config
        .client_setup
        .as_ref()
        .ok_or_else(|| anyhow::anyhow!("No client configuration to undo"))?;
    let after =
        read(&receipt.path)?.ok_or_else(|| anyhow::anyhow!("Client configuration was removed"))?;
    anyhow::ensure!(
        hash(&after) == receipt.after_hash,
        "Client configuration changed since setup. Restore manually from the backup to preserve later edits."
    );
    let before = read(&receipt.backup)?.ok_or_else(|| anyhow::anyhow!("Backup is missing"))?;
    anyhow::ensure!(
        hash(&before) == receipt.before_hash,
        "Backup changed; automatic restore refused"
    );
    if receipt.existed {
        replace(&receipt.path, &before)?;
    } else {
        std::fs::remove_file(&receipt.path)?;
    }
    let mut config = inner.config.clone();
    config.client_setup = None;
    if let Some(journey) = &mut config.activation {
        journey.configured = false;
    }
    if let Err(error) = runtime.persist(&config) {
        replace(&receipt.path, &after)?;
        return Err(error);
    }
    inner.config = config;
    inner.client_preview = None;
    Ok(json!({"ok":true}))
}
