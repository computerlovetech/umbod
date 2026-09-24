<section class="hero">
  <p class="eyebrow">Umbod</p>
  <h1>Umbod</h1>
  <p class="lede">
    A SvelteKit app for publishing connector-backed tools through FastAPI, FastMCP, and Typer services.
  </p>
  <div class="links">
    <a href="/admin">Admin</a>
  </div>
</section>

<style>
  .hero {
    box-sizing: border-box;
    display: grid;
    align-content: center;
    min-height: 100vh;
    padding: clamp(2rem, 8vw, 6rem);
    background:
      radial-gradient(circle at top left, rgb(59 130 246 / 35%), transparent 35rem),
      #111827;
  }

  .eyebrow {
    color: #93c5fd;
    font-weight: 700;
    letter-spacing: 0.18em;
    margin: 0 0 1rem;
    text-transform: uppercase;
  }

  h1 {
    font-size: clamp(3rem, 9vw, 7rem);
    line-height: 0.95;
    margin: 0;
    max-width: 9ch;
  }

  .lede {
    color: #cbd5e1;
    font-size: clamp(1.125rem, 2vw, 1.4rem);
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
    border: 1px solid rgb(255 255 255 / 20%);
    border-radius: 999px;
    padding: 0.85rem 1.1rem;
    text-decoration: none;
  }

  a:hover {
    border-color: #93c5fd;
  }
</style>
