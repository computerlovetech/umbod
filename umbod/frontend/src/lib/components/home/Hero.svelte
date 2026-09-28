<section class="hero">
  <p class="eyebrow">Umbod</p>
  <h1>Welcome to Umbod.</h1>
  <p class="lede">
    Umbod makes tools from your internal APIs and MCP servers available to compatible agents, with access controlled by group. Open administration to configure a connector, publish its tools, and choose who can use them.
  </p>
  <div class="links">
    <a href="/admin">Open administration</a>
  </div>
</section>

<style>
  .hero {
    box-sizing: border-box;
    display: grid;
    align-content: center;
    min-height: calc(100svh - 4.5rem);
    padding: clamp(2rem, 8vw, 6rem);
    color: var(--admin-ink);
    background: var(--admin-canvas);
  }

  .eyebrow {
    color: var(--admin-accent);
    font-family: var(--admin-mono);
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.08em;
    margin: 0 0 1rem;
    text-transform: uppercase;
  }

  h1 {
    font-size: clamp(3rem, 6vw, 4.5rem);
    font-weight: 600;
    letter-spacing: -0.05em;
    line-height: 1.1;
    margin: 0;
    max-width: 9ch;
  }

  .lede {
    color: var(--admin-muted);
    font-size: clamp(1rem, 2vw, 1.125rem);
    line-height: 1.6;
    max-width: 42rem;
  }

  .links {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    margin-top: 1.5rem;
  }

  a {
    background: var(--admin-action);
    border: 1px solid var(--admin-action);
    border-radius: var(--admin-radius);
    color: var(--admin-on-action);
    font-size: 14px;
    font-weight: 600;
    padding: 0.85rem 1.1rem;
    text-decoration: none;
  }

  a:hover {
    background: var(--admin-action-hover);
    border-color: var(--admin-action-hover);
  }
</style>
