from __future__ import annotations

from dataclasses import dataclass
import html

from fastmcp.server.auth.oauth_proxy import consent as fastmcp_consent
from fastmcp.server.auth.oauth_proxy import ui as fastmcp_ui


_REQUIRED_OPTION_KEYS = ("client_id", "redirect_uri", "scopes", "txn_id", "csrf_token")
_DEFAULT_CSP_POLICY = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src https: data:; base-uri 'none'"
)


@dataclass(frozen=True)
class ConsentInputs:
    client_id: str
    redirect_uri: str
    scopes: list[str]
    txn_id: str
    csrf_token: str


@dataclass(frozen=True)
class ConsentDisplay:
    client_display: str
    client_id_display: str
    redirect_uri_display: str
    server_display: str
    title_display: str
    scope_display: str
    scope_items: str
    client_website_display: str
    logo: str
    cimd_badge: str
    csp_meta: str
    txn_id_display: str
    csrf_token_display: str


def create_umbod_consent_html(*args: object, **options: object) -> str:
    consent_inputs, display_options = _consent_arguments(args, options)
    display = _consent_display(consent_inputs, display_options)
    return _consent_document(display)


def install_umbod_consent_screen() -> None:
    fastmcp_ui.create_consent_html = create_umbod_consent_html
    fastmcp_consent.create_consent_html = create_umbod_consent_html


def _consent_arguments(
    args: tuple[object, ...],
    options: dict[str, object],
) -> tuple[ConsentInputs, dict[str, object]]:
    display_options = dict(options)
    if args:
        values = args
    else:
        values = tuple(display_options.pop(key, None) for key in _REQUIRED_OPTION_KEYS)
    if len(values) != 5:
        raise TypeError("create_umbod_consent_html requires 5 arguments")
    client_id, redirect_uri, scopes, txn_id, csrf_token = values
    if not isinstance(client_id, str) or not isinstance(redirect_uri, str):
        raise TypeError("client_id and redirect_uri must be strings")
    if not isinstance(txn_id, str) or not isinstance(csrf_token, str):
        raise TypeError("txn_id and csrf_token must be strings")
    if not isinstance(scopes, list) or not all(isinstance(scope, str) for scope in scopes):
        raise TypeError("scopes must be a list of strings")
    return ConsentInputs(client_id, redirect_uri, scopes, txn_id, csrf_token), display_options


def _consent_display(consent_inputs: ConsentInputs, options: dict[str, object]) -> ConsentDisplay:
    server_name = _string_option(options, "server_name")
    server_display_name = html.escape(server_name or "Umbod")
    server_website_url = _string_option(options, "server_website_url")
    server_display = (
        _server_display(server_display_name, server_website_url)
        if server_website_url
        else server_display_name
    )
    server_icon_url = _string_option(options, "server_icon_url")
    logo = (
        _logo(server_icon_url, server_name or "Umbod")
        if server_icon_url
        else '<span class="logo-mark">AC</span>'
    )
    cimd_domain = _string_option(options, "cimd_domain")
    cimd_badge = (
        _cimd_badge(cimd_domain)
        if _bool_option(options, "is_cimd_client") and cimd_domain
        else ""
    )
    csp_policy = _string_option(options, "csp_policy")
    csp_meta = "" if csp_policy == "" else _csp_meta(csp_policy or _DEFAULT_CSP_POLICY)
    return ConsentDisplay(
        client_display=html.escape(
            _string_option(options, "client_name") or consent_inputs.client_id
        ),
        client_id_display=html.escape(consent_inputs.client_id),
        redirect_uri_display=html.escape(consent_inputs.redirect_uri),
        server_display=server_display,
        title_display=html.escape(
            _string_option(options, "title") or "Umbod Access Request"
        ),
        scope_display=", ".join(html.escape(scope) for scope in consent_inputs.scopes)
        if consent_inputs.scopes
        else "None",
        scope_items=_scope_items(consent_inputs.scopes),
        client_website_display=html.escape(_string_option(options, "client_website_url") or "N/A"),
        logo=logo,
        cimd_badge=cimd_badge,
        csp_meta=csp_meta,
        txn_id_display=html.escape(consent_inputs.txn_id),
        csrf_token_display=html.escape(consent_inputs.csrf_token),
    )


def _consent_document(display: ConsentDisplay) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
{display.csp_meta}
<title>{display.title_display}</title>
<style>{_styles()}</style>
</head>
<body>
<main class="shell">
<section class="card" aria-labelledby="consent-title">
<div class="brand">{display.logo}<span>Umbod</span></div>
<p class="eyebrow">Application access</p>
<h1 id="consent-title">Allow this client to connect?</h1>
<p class="lede"><strong>{display.client_display}</strong> wants to access <strong>{display.server_display}</strong>.</p>
{display.cimd_badge}
{_permissions_panel(display.scope_items)}
{_redirect_panel(display.redirect_uri_display)}
{_advanced_details(display)}
{_consent_form(display.txn_id_display, display.csrf_token_display)}
<p class="help">Only continue if you trust the client and recognize the callback address.</p>
</section>
</main>
</body>
</html>"""


def _permissions_panel(scope_items: str) -> str:
    return f"""<section class="permissions" aria-labelledby="permissions-title">
<p class="section-label">Permissions requested</p>
<h2 id="permissions-title">This application will be able to</h2>
<ul>{scope_items}</ul>
</section>"""


def _scope_items(scopes: list[str]) -> str:
    if not scopes:
        return '<li><div><strong>No additional permissions</strong><span>This application did not request access to Umbod capabilities.</span></div></li>'
    return "".join(_scope_item(scope) for scope in scopes)


def _scope_item(scope: str) -> str:
    labels = {
        "tools": ("Use tools", "Discover and run tools made available through Umbod."),
        "prompts": ("Use prompts", "View and use prompt templates made available through Umbod."),
        "resources": ("Read resources", "View resources made available through Umbod."),
        "openid": ("Confirm your identity", "Verify your identity for this connection."),
        "profile": ("View your profile", "View your basic profile information."),
        "email": ("View your email address", "View the email address associated with your account."),
        "offline_access": ("Maintain access", "Remain connected when you are not actively using the application."),
    }
    label, description = labels.get(
        scope.lower(),
        ("Additional access", f'Use the access represented by the “{scope}” scope.'),
    )
    return f"""<li>
<span class="permission-check" aria-hidden="true">✓</span>
<div><strong>{html.escape(label)}</strong><span>{html.escape(description)}</span><code>{html.escape(scope)}</code></div>
</li>"""


def _redirect_panel(redirect_uri_display: str) -> str:
    return f"""<div class="redirect-panel">
<span>After approval, you will return to</span>
<code>{redirect_uri_display}</code>
</div>"""


def _advanced_details(display: ConsentDisplay) -> str:
    return f"""<details>
<summary>Advanced details</summary>
<div class="details-grid">
<div><span>Application name</span><strong>{display.client_display}</strong></div>
<div><span>Application website</span><strong>{display.client_website_display}</strong></div>
<div><span>Application ID</span><strong>{display.client_id_display}</strong></div>
<div><span>Redirect URI</span><strong>{display.redirect_uri_display}</strong></div>
<div><span>Requested scopes</span><strong>{display.scope_display}</strong></div>
</div>
</details>"""


def _consent_form(txn_id_display: str, csrf_token_display: str) -> str:
    return f"""<form method="POST" action="" class="actions">
<input type="hidden" name="txn_id" value="{txn_id_display}" />
<input type="hidden" name="csrf_token" value="{csrf_token_display}" />
<input type="hidden" name="submit" value="true" />
<button type="submit" name="action" value="approve" class="primary">Allow access</button>
<button type="submit" name="action" value="deny" class="secondary">Deny</button>
</form>"""


def _string_option(options: dict[str, object], key: str) -> str | None:
    value = options.get(key)
    return value if isinstance(value, str) else None


def _bool_option(options: dict[str, object], key: str) -> bool:
    value = options.get(key)
    return value if isinstance(value, bool) else False


def _server_display(server_name: str, server_website_url: str) -> str:
    return f'<a href="{html.escape(server_website_url)}" target="_blank" rel="noopener noreferrer">{server_name}</a>'


def _logo(server_icon_url: str, alt_text: str) -> str:
    return f'<img src="{html.escape(server_icon_url)}" alt="{html.escape(alt_text)}" />'


def _cimd_badge(cimd_domain: str) -> str:
    return f'<div class="verified">✓ Verified domain: <strong>{html.escape(cimd_domain)}</strong></div>'


def _csp_meta(csp_policy: str) -> str:
    return f'<meta http-equiv="Content-Security-Policy" content="{html.escape(csp_policy, quote=True)}" />'


def _styles() -> str:
    return STYLES


STYLES = """
:root { color: #f5f7fb; background: #111827; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; }
a { color: #93c5fd; text-decoration: none; }
a:hover { text-decoration: underline; text-underline-offset: 3px; }
.shell { background: radial-gradient(circle at top left, rgb(59 130 246 / 35%), transparent 35rem), #111827; display: grid; min-height: 100vh; padding: clamp(1.5rem, 6vw, 5rem); place-items: center; }
.card { background: rgb(17 24 39 / 82%); border: 1px solid rgb(255 255 255 / 14%); border-radius: 24px; box-shadow: 0 24px 80px rgb(0 0 0 / 35%); max-width: 680px; padding: clamp(1.5rem, 4vw, 2.5rem); width: 100%; }
.brand { align-items: center; color: #cbd5e1; display: flex; font-size: 0.95rem; font-weight: 700; gap: 0.75rem; margin-bottom: 2rem; }
.brand img, .logo-mark { align-items: center; background: #f5f7fb; border-radius: 12px; color: #111827; display: inline-flex; font-weight: 800; height: 2.5rem; justify-content: center; width: 2.5rem; }
.brand img { object-fit: contain; padding: 0.3rem; }
.eyebrow { color: #93c5fd; font-size: 0.78rem; font-weight: 800; letter-spacing: 0.18em; margin: 0 0 0.85rem; text-transform: uppercase; }
h1 { font-size: clamp(2rem, 5vw, 3.5rem); letter-spacing: -0.05em; line-height: 0.98; margin: 0; max-width: 11ch; }
.lede { color: #cbd5e1; font-size: 1.1rem; line-height: 1.6; margin: 1.25rem 0 0; }
.redirect-panel, .verified { border-radius: 16px; margin-top: 1.25rem; padding: 1rem; }
.redirect-panel { background: rgb(147 197 253 / 12%); border: 1px solid rgb(147 197 253 / 30%); }
.redirect-panel > span, .details-grid span, .section-label { color: #93c5fd; display: block; font-size: 0.75rem; font-weight: 800; letter-spacing: 0.12em; margin-bottom: 0.45rem; text-transform: uppercase; }
code { color: #f5f7fb; overflow-wrap: anywhere; }
.permissions { background: rgb(255 255 255 / 4%); border: 1px solid rgb(255 255 255 / 12%); border-radius: 16px; margin-top: 1.25rem; padding: 1rem; }
.permissions h2 { font-size: 1.05rem; margin: 0; }
.permissions ul { display: grid; gap: 0.9rem; list-style: none; margin: 1rem 0 0; padding: 0; }
.permissions li { align-items: flex-start; display: flex; gap: 0.75rem; }
.permissions li div { display: grid; gap: 0.2rem; min-width: 0; }
.permissions li strong { color: #f5f7fb; }
.permissions li span:not(.permission-check) { color: #cbd5e1; line-height: 1.45; }
.permissions li code { color: #94a3b8; font-size: 0.75rem; }
.permission-check { align-items: center; background: rgb(16 185 129 / 14%); border-radius: 999px; color: #a7f3d0; display: inline-flex; flex: 0 0 auto; height: 1.5rem; justify-content: center; width: 1.5rem; }
.verified { background: rgb(16 185 129 / 12%); border: 1px solid rgb(110 231 183 / 30%); color: #a7f3d0; }
details { border-top: 1px solid rgb(255 255 255 / 12%); margin-top: 1.5rem; padding-top: 1rem; }
summary { color: #f5f7fb; cursor: pointer; font-weight: 700; }
.details-grid { display: grid; gap: 1rem; margin-top: 1rem; }
.details-grid div { background: rgb(255 255 255 / 5%); border: 1px solid rgb(255 255 255 / 10%); border-radius: 14px; padding: 0.9rem; }
.details-grid strong { color: #f5f7fb; display: block; font-weight: 650; overflow-wrap: anywhere; }
.actions { display: flex; flex-wrap: wrap; gap: 0.85rem; margin-top: 1.5rem; }
button { border-radius: 999px; cursor: pointer; font: inherit; font-weight: 800; padding: 0.85rem 1.15rem; }
.primary { background: #f5f7fb; border: 1px solid #f5f7fb; color: #111827; }
.secondary { background: transparent; border: 1px solid rgb(255 255 255 / 22%); color: #f5f7fb; }
.primary:hover { background: #dbeafe; border-color: #dbeafe; }
.secondary:hover { border-color: #93c5fd; color: #93c5fd; }
.help { color: #94a3b8; font-size: 0.92rem; line-height: 1.5; margin: 1.25rem 0 0; }
"""
