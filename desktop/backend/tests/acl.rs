use umbod_gateway::Config;
#[test]
fn shared_grants_are_explicit_and_revocable() {
    let mut config = Config::default();
    assert!(!config.allowed("server.echo"));
    config.grant("server.echo", true);
    assert!(config.allowed("server.echo"));
    assert!(!config.allowed("server.new"));
    config.grant("server.echo", false);
    assert!(!config.allowed("server.echo"));
}
#[test]
fn protected_configuration_survives_restart() {
    #[cfg(unix)]
    use std::os::unix::fs::PermissionsExt;
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("private/config.json");
    let mut config = Config::default();
    config.grant("echo", true);
    config.save(&path).unwrap();
    let loaded = Config::load(&path).unwrap();
    assert!(loaded.allowed("echo"));
    #[cfg(unix)]
    assert_eq!(
        std::fs::metadata(&path).unwrap().permissions().mode() & 0o777,
        0o600
    );
    #[cfg(unix)]
    assert_eq!(
        std::fs::metadata(path.parent().unwrap())
            .unwrap()
            .permissions()
            .mode()
            & 0o777,
        0o700
    );
}

#[test]
fn legacy_permissions_migrate_conservatively_and_removed_api_tools_disappear() {
    let config: Config = serde_json::from_value(serde_json::json!({
        "servers":[{"id":"local","name":"Local"}],
        "clients":[{"id":"alice"},{"id":"bob"}],
        "grants":{"alice":["local.echo","local.private","api.old"],"bob":["local.echo","api.old"]},
        "custom_tools":[{"id":"api.old"}]
    }))
    .unwrap();
    assert!(config.allowed("local.echo"));
    assert!(!config.allowed("local.private"));
    assert!(!config.allowed("api.old"));
    assert_eq!(config.clients.len(), 2);
    let saved = serde_json::to_value(&config).unwrap();
    assert!(saved.get("grants").is_none());
    assert!(saved.get("custom_tools").is_none());
    let restored: Config = serde_json::from_value(saved).unwrap();
    assert!(restored.allowed("local.echo"));
}

#[test]
fn missing_legacy_grants_and_explicit_empty_shared_permissions_stay_denied() {
    for allowed in [None, Some(serde_json::json!([]))] {
        let mut value = serde_json::json!({"servers":[{"id":"local"}],"clients":[{"id":"alice"},{"id":"bob"}],"grants":{"alice":["local.echo"]}});
        if let Some(allowed) = allowed {
            value["allowed_tools"] = allowed;
        }
        let config: Config = serde_json::from_value(value).unwrap();
        assert!(!config.allowed("local.echo"));
    }
}

#[test]
fn migrating_a_file_keeps_an_owner_only_backup_and_preserves_revocation() {
    #[cfg(unix)]
    use std::os::unix::fs::PermissionsExt;
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("config.json");
    let original = serde_json::json!({"servers":[{"id":"local"}],"clients":[{"id":"alice"}],"grants":{"alice":["local.echo"]}});
    std::fs::write(&path, serde_json::to_vec(&original).unwrap()).unwrap();
    let mut config = Config::load(&path).unwrap();
    assert!(config.allowed("local.echo"));
    let backup = path.with_extension("before-shared-permissions.json");
    assert_eq!(
        serde_json::from_slice::<serde_json::Value>(&std::fs::read(&backup).unwrap()).unwrap(),
        original
    );
    #[cfg(unix)]
    assert_eq!(
        std::fs::metadata(&backup).unwrap().permissions().mode() & 0o777,
        0o600
    );
    config.grant("local.echo", false);
    config.save(&path).unwrap();
    assert!(!Config::load(&path).unwrap().allowed("local.echo"));
    assert_eq!(
        serde_json::from_slice::<serde_json::Value>(&std::fs::read(&backup).unwrap()).unwrap(),
        original
    );
}

#[test]
fn shared_permission_migration_preserves_activation_and_gateway_state() {
    let original = serde_json::json!({
        "gateway_port": 12345,
        "activation": {"client":"claude","server":"github","configured":true},
        "diagnostics": {"enabled":true,"events":{"connection":1}},
        "servers":[{"id":"github"}],
        "clients":[{"id":"claude"}],
        "grants":{"claude":["github.search_issues"]}
    });
    let migrated: Config = serde_json::from_value(original).unwrap();
    let restored: Config =
        serde_json::from_value(serde_json::to_value(&migrated).unwrap()).unwrap();
    assert_eq!(restored.gateway_port, Some(12345));
    assert!(restored.activation.unwrap().configured);
    assert_eq!(restored.diagnostics.events["connection"], 1);
    assert!(restored.allowed_tools.contains("github.search_issues"));
}
