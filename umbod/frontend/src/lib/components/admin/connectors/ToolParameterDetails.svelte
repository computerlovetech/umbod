<script lang="ts">
  import type { ConnectorToolParameter } from '$lib/admin/connectors';

  let { parameters }: { parameters: ConnectorToolParameter[] } = $props();

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
      <section aria-labelledby="required-parameters-title">
        <h4 id="required-parameters-title">Required parameters</h4>
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
      <section aria-labelledby="optional-parameters-title">
        <h4 id="optional-parameters-title">Optional parameters</h4>
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
</details>

<style>
  .parameter-details {
    border-top: 1px solid #e9e9e7;
    margin-top: 14px;
    padding-top: 14px;
  }

  summary {
    align-items: center;
    background: #f7f6f3;
    border: 1px solid #e9e9e7;
    border-radius: 999px;
    color: #37352f;
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
    border-color: #c9c8c4;
  }

  summary:focus-visible {
    border-radius: 8px;
    outline: 3px solid rgb(55 53 47 / 16%);
    outline-offset: 3px;
  }

  .schema-icon,
  .chevron {
    align-items: center;
    display: inline-flex;
    justify-content: center;
  }

  .schema-icon {
    background: #e9e9e7;
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
    color: #787774;
  }

  .overview {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 14px;
  }

  .overview span {
    background: #f7f6f3;
    border: 1px solid #e9e9e7;
  }

  section {
    margin-top: 14px;
  }

  h4 {
    color: #787774;
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
    background: #f7f6f3;
    border: 1px solid #e9e9e7;
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
    color: #37352f;
    font-size: 14px;
  }

  code {
    background: #fff;
    border: 1px solid #e3e2df;
    border-radius: 999px;
    color: #37352f;
    font-size: 12px;
    padding: 2px 7px;
  }

  p {
    color: #787774;
    font-size: 13px;
    line-height: 1.5;
    margin: 0;
  }

  .type-label {
    background: #f1faf3;
    border: 1px solid #cce9d2;
    color: #2f6b3f;
    justify-self: start;
  }

  .empty-state {
    margin-top: 14px;
  }
</style>
