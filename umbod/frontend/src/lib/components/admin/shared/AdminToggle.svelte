<script lang="ts">
  let {
    checked,
    ariaLabel,
    disabled = false,
    inputName,
    inputValue,
    onchange,
    submit = false
  }: {
    checked: boolean;
    ariaLabel: string;
    disabled?: boolean;
    inputName?: string;
    inputValue?: string;
    onchange?: (event: Event) => void;
    submit?: boolean;
  } = $props();
</script>

{#if submit}
  <button type="submit" class:checked role="switch" aria-checked={checked} aria-label={ariaLabel} {disabled}>
    <span class="track" aria-hidden="true"><span class="thumb"></span></span>
  </button>
{:else}
  <label class="toggle" aria-label={ariaLabel} class:disabled>
    <input type="checkbox" name={inputName} value={inputValue} {checked} {disabled} {onchange} />
    <span class="track" aria-hidden="true"><span class="thumb"></span></span>
  </label>
{/if}

<style>
  button,
  .toggle {
    align-items: center;
    background: transparent;
    border: 0;
    border-radius: 999px;
    cursor: pointer;
    display: inline-flex;
    flex-shrink: 0;
    height: 20px;
    padding: 0;
    position: relative;
    width: 34px;
  }

  input {
    opacity: 0;
    position: absolute;
  }

  .track {
    background: #e2e1de;
    border-radius: 10px;
    display: block;
    height: 20px;
    inset: 0;
    position: absolute;
    transition: background 0.15s;
    width: 34px;
  }

  .thumb {
    background: #fff;
    border-radius: 50%;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.15);
    height: 16px;
    left: 2px;
    position: absolute;
    top: 2px;
    transition: transform 0.15s;
    width: 16px;
  }

  input:checked + .track,
  button.checked .track {
    background: #37352f;
  }

  input:checked + .track .thumb,
  button.checked .thumb {
    transform: translateX(14px);
  }

  button:focus-visible,
  input:focus-visible + .track {
    outline: 3px solid rgb(55 53 47 / 16%);
    outline-offset: 3px;
  }

  button:disabled,
  .disabled {
    cursor: not-allowed;
    opacity: 0.72;
  }
</style>
