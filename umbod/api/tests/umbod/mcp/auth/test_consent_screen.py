import base64
import re
from pathlib import Path

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

    favicon = re.search(r'href="data:image/svg\+xml;base64,([^"]+)"', html)
    assert favicon is not None
    assert base64.b64decode(favicon.group(1)) == (
        Path(__file__).resolve().parents[6] / "website/public/umbod-logo.svg"
    ).read_bytes()
    assert "Umbod" in html
    assert "color-scheme: light" in html
    assert "radial-gradient" not in html
    assert 'aria-label="Application header"' in html
    assert '<svg class="logo-mark"' in html
    assert '>AC</span>' not in html
    assert "outline: 3px solid var(--admin-focus)" in html
    assert "Allow access" in html
    assert "https://example.com/callback" in html
    assert "Permissions requested" in html
    assert "Discover and run tools made available through Umbod." in html
    assert 'class="shell"' in html
    assert "place-items: center" in html


def test_umbod_consent_screen_theme_tokens_match_frontend() -> None:
    html = create_umbod_consent_html(
        client_id="client-1",
        redirect_uri="https://example.com/callback",
        scopes=[],
        txn_id="txn-1",
        csrf_token="csrf-1",
    )
    frontend_styles = (
        Path(__file__).resolve().parents[5] / "frontend/src/lib/styles/admin.css"
    ).read_text()
    palette = re.findall(r"--admin-[\w-]+: [^;]+;", html)

    assert palette
    assert all(token in frontend_styles for token in palette)


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


def test_umbod_consent_screen_preserves_consent_form_and_escapes_client_data() -> None:
    html = create_umbod_consent_html(
        client_id="client-1",
        redirect_uri='https://example.com/callback?value="unsafe"',
        scopes=[],
        txn_id='txn-"1',
        csrf_token='csrf-"1',
        client_name="<script>untrusted</script>",
    )

    assert "&lt;script&gt;untrusted&lt;/script&gt;" in html
    assert "No additional permissions" in html
    assert 'https://example.com/callback?value=&quot;unsafe&quot;' in html
    assert '<form method="POST" action="" class="actions">' in html
    assert 'name="txn_id" value="txn-&quot;1"' in html
    assert 'name="csrf_token" value="csrf-&quot;1"' in html
    assert 'name="submit" value="true"' in html
    assert 'name="action" value="approve"' in html
    assert 'name="action" value="deny"' in html
    assert "Content-Security-Policy" in html


def test_install_umbod_consent_screen_replaces_fastmcp_renderer() -> None:
    install_umbod_consent_screen()

    assert fastmcp_consent.create_consent_html is create_umbod_consent_html
