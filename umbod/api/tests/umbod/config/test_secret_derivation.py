from cryptography.fernet import Fernet

from umbod.config.secret_derivation import derive_secret


def test_root_secret_derives_stable_purpose_specific_keys() -> None:
    first = derive_secret("root-secret", "connector-configuration")
    repeated = derive_secret("root-secret", "connector-configuration")
    approval = derive_secret("root-secret", "connector-approval-state")

    assert first == repeated
    assert first != approval
    assert len(Fernet(first.encode()).encrypt(b"value")) > 0
