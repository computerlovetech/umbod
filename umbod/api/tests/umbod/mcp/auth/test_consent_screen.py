from umbod.mcp.auth.consent_screen import (
    create_umbod_consent_html,
    install_umbod_consent_screen,
)
from fastmcp.server.auth.oauth_proxy import consent as fastmcp_consent


def test_umbod_consent_screen_uses_umbod_visual_language() -> None:
    html = create_umbod_consent_html(
        client_id="client-1",
        redirect_uri="https://example.com/callback",
        scopes=["tools"],
        txn_id="txn-1",
        csrf_token="csrf-1",
        client_name="Test Client",
        server_name="Umbod MCP",
    )

    assert "Umbod" in html
    assert (
        "radial-gradient(circle at top left, rgb(59 130 246 / 35%), transparent 35rem), #111827"
        in html
    )
    assert "Allow access" in html
    assert "https://example.com/callback" in html
    assert "Permissions requested" in html
    assert "Discover and run tools made available through Umbod." in html
    assert 'class="shell"' in html
    assert "place-items: center" in html


def test_umbod_consent_screen_explains_each_requested_scope() -> None:
    html = create_umbod_consent_html(
        client_id="client-1",
        redirect_uri="https://example.com/callback",
        scopes=["prompts", "resources", "custom<scope>"],
        txn_id="txn-1",
        csrf_token="csrf-1",
    )

    assert "View and use prompt templates made available through Umbod." in html
    assert "View resources made available through Umbod." in html
    assert "Use the access represented by the “custom&lt;scope&gt;” scope." in html
    assert "<code>custom&lt;scope&gt;</code>" in html


def test_install_umbod_consent_screen_replaces_fastmcp_renderer() -> None:
    install_umbod_consent_screen()

    assert fastmcp_consent.create_consent_html is create_umbod_consent_html
