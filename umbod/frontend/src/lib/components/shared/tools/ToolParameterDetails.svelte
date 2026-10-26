<script lang="ts">
  import type { ToolParameter } from './presentation';

  let { parameters, inputSchema }: { parameters: ToolParameter[]; inputSchema?: Record<string, unknown> } = $props();
  const headingId = $props.id();

  const requiredParameters = $derived(parameters.filter((parameter) => parameter.required));
  const optionalParameters = $derived(parameters.filter((parameter) => !parameter.required));
  const summary = $derived(
    parameters.length === 0
      ? 'No parameters'
      : `${parameters.length} parameter${parameters.length === 1 ? '' : 's'} · ${requiredParameters.length} required`
  );
</script>

<details class="parameter-details">
  <summary aria-label="Toggle parameter schema details">
    <span class="schema-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" focusable="false">
        <path d="M4 7.5A2.5 2.5 0 0 1 6.5 5h11A2.5 2.5 0 0 1 20 7.5v9a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 16.5v-9Z" />
        <path d="M8 9h8M8 12h5M8 15h7" />
      </svg>
    </span>
    <small>{summary}</small>
    <span class="chevron" aria-hidden="true">
      <svg viewBox="0 0 20 20" focusable="false">
        <path d="m6 8 4 4 4-4" />
      </svg>
    </span>
  </summary>

  {#if parameters.length === 0}
    <p class="empty-state">This tool does not need any input from the user.</p>
  {:else}
    <div class="overview" aria-label="Parameter overview">
      <span>{parameters.length} total</span>
      <span>{requiredParameters.length} required</span>
      <span>{optionalParameters.length} optional</span>
    </div>

    {#if requiredParameters.length > 0}
      <section aria-labelledby={headingId + "-required"}>
        <h4 id={headingId + "-required"}>Required parameters</h4>
        <ul>
          {#each requiredParameters as parameter (parameter.name)}
            <li>
              <div class="parameter-heading">
                <strong>{parameter.label}</strong>
                <code>{parameter.name}</code>
              </div>
              <p>{parameter.description || 'No description provided.'}</p>
              <span class="type-label">{parameter.type}</span>
            </li>
          {/each}
        </ul>
      </section>
    {/if}

    {#if optionalParameters.length > 0}
      <section aria-labelledby={headingId + "-optional"}>
        <h4 id={headingId + "-optional"}>Optional parameters</h4>
        <ul>
          {#each optionalParameters as parameter (parameter.name)}
            <li>
              <div class="parameter-heading">
                <strong>{parameter.label}</strong>
                <code>{parameter.name}</code>
              </div>
              <p>{parameter.description || 'No description provided.'}</p>
              <span class="type-label">{parameter.type}</span>
            </li>
          {/each}
        </ul>
      </section>
    {/if}
  {/if}
  {#if inputSchema}
    <details class="raw-schema">
      <summary>Full input schema</summary>
      <textarea readonly aria-label="Full input schema (read-only)" value={JSON.stringify(inputSchema, null, 2)}></textarea>
    </details>
  {/if}
</details>

<style>
  .parameter-details {
    border-top: 1px solid var(--admin-border);
    margin-top: 14px;
    padding-top: 14px;
  }

  summary {
    align-items: center;
    background: var(--admin-soft);
    border: 1px solid var(--admin-border);
    border-radius: 999px;
    color: var(--admin-ink);
    cursor: pointer;
    display: inline-flex;
    gap: 6px;
    list-style: none;
    padding: 3px 8px 3px 4px;
  }

  summary::-webkit-details-marker {
    display: none;
  }

  summary:hover {
    border-color: var(--admin-border-strong);
  }

  summary:focus-visible {
    border-radius: 8px;
    outline: 3px solid var(--admin-focus);
    outline-offset: 3px;
  }

  .schema-icon,
  .chevron {
    align-items: center;
    display: inline-flex;
    justify-content: center;
  }

  .schema-icon {
    background: var(--admin-border);
    border-radius: 999px;
    height: 24px;
    width: 24px;
  }

  svg {
    fill: none;
    height: 14px;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.8;
    width: 14px;
  }

  .chevron {
    transition: transform 140ms ease;
  }

  details[open] .chevron {
    transform: rotate(180deg);
  }

  summary small,
  .overview span,
  .type-label {
    border-radius: 999px;
    font-size: 12px;
    font-weight: 650;
    line-height: 1.4;
    padding: 2px 7px;
  }

  summary small,
  .overview span {
    color: var(--admin-muted);
  }

  .overview {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 14px;
  }

  .overview span {
    background: var(--admin-soft);
    border: 1px solid var(--admin-border);
  }

  section {
    margin-top: 14px;
  }

  h4 {
    color: var(--admin-muted);
    font-size: 12px;
    font-weight: 650;
    letter-spacing: 0.12em;
    line-height: 1.4;
    margin: 0 0 10px;
    text-transform: uppercase;
  }

  ul {
    display: grid;
    gap: 8px;
    list-style: none;
    margin: 0;
    padding: 0;
  }

  li {
    background: var(--admin-soft);
    border: 1px solid var(--admin-border);
    border-radius: 8px;
    display: grid;
    gap: 6px;
    padding: 10px;
  }

  .parameter-heading {
    align-items: baseline;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  strong {
    color: var(--admin-ink);
    font-size: 14px;
  }

  code {
    background: var(--admin-panel);
    border: 1px solid var(--admin-border);
    border-radius: 999px;
    color: var(--admin-ink);
    font-size: 12px;
    padding: 2px 7px;
  }

  p {
    color: var(--admin-muted);
    font-size: 13px;
    line-height: 1.5;
    margin: 0;
  }

  .type-label {
    background: var(--admin-success-bg);
    border: 1px solid var(--admin-success-border);
    color: var(--admin-success-text);
    justify-self: start;
  }

  .empty-state {
    margin-top: 14px;
  }

  .raw-schema { margin-top: 14px; min-width: 0; }
  .raw-schema > summary { background: transparent; border: 0; border-radius: 0; color: var(--admin-accent); font-size: 0.8rem; padding: 0; text-decoration: underline; text-underline-offset: 3px; }
  textarea { background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: 6px; box-sizing: border-box; color: var(--admin-ink); display: block; font-family: var(--admin-mono); font-size: 0.75rem; height: 16rem; line-height: 1.5; margin: 0.6rem 0 0; max-width: 100%; padding: 0.65rem; resize: vertical; width: 100%; }
  textarea:focus-visible { outline: 3px solid var(--admin-focus); outline-offset: 3px; }
</style>
