<script lang="ts">
  import { AdminFileUploadState } from './admin-file-upload-state.svelte';

  let {
    id,
    name,
    label,
    accept,
    required = false,
    disabled = false,
    optionalText = '',
    buttonText = 'Choose file',
    replaceText = 'Replace',
    helperText = '',
    maxBytes
  }: {
    id: string;
    name: string;
    label: string;
    accept?: string;
    required?: boolean;
    disabled?: boolean;
    optionalText?: string;
    buttonText?: string;
    replaceText?: string;
    helperText?: string;
    maxBytes?: number;
  } = $props();

  const state = new AdminFileUploadState();
</script>

<div class="file-upload" data-file-upload>
  <span class="label" id={`${id}-label`}>{label}{#if optionalText}<span class="optional"> {optionalText}</span>{/if}</span>
  <div
    class:dragging={state.dragging}
    class:disabled
    class:populated={state.selectedFileName}
    class="drop-zone"
    role="group"
    aria-labelledby={`${id}-label`}
    ondragover={state.dragOver}
    ondragleave={state.dragLeave}
    ondrop={(event) => state.drop(event, { accept, maxBytes })}
  >
    <input
      class="native-input"
      type="file"
      {id}
      {name}
      {accept}
      {required}
      {disabled}
      aria-labelledby={`${id}-label ${id}-button`}
      aria-describedby={`${id}-helper ${id}-error`}
      onchange={(event) => state.select(event, { accept, maxBytes })}
    />
    {#if state.selectedFileName}
      <div class="selected-file">
        <span class="file-icon" aria-hidden="true">JSON</span>
        <span class="file-details">
          <strong>{state.selectedFileName}</strong>
          <span>{state.selectedFileSize}</span>
        </span>
        <label class="text-action" id={`${id}-button`} for={id}>{replaceText}</label>
        <button class="text-action remove" type="button" onclick={state.remove}>Remove</button>
      </div>
    {:else}
      <div class="empty-state">
        <span class="upload-icon" aria-hidden="true">↑</span>
        <span><strong>Drop a file here</strong> or <label class="browse" id={`${id}-button`} for={id}>{buttonText}</label></span>
        {#if helperText}<span class="constraints" id={`${id}-helper`}>{helperText}</span>{/if}
      </div>
    {/if}
  </div>
  {#if state.error}<p class="error" id={`${id}-error`} role="alert">{state.error}</p>{/if}
</div>

<style>
  .file-upload { display: grid; gap: 7px; }
  .label { color: #37352f; font-size: 13px; font-weight: 650; line-height: 1.4; }
  .optional { color: #787774; font-weight: 500; }
  .drop-zone { background: #fbfbfa; border: 1px dashed #c7c6c2; border-radius: 9px; min-height: 104px; position: relative; transition: background 120ms ease, border-color 120ms ease; }
  .drop-zone:hover, .drop-zone:focus-within, .drop-zone.dragging { background: #f5f5f3; border-color: #787774; }
  .drop-zone:focus-within { outline: 3px solid rgb(55 53 47 / 12%); }
  .drop-zone.disabled { opacity: .6; }
  .drop-zone.populated { min-height: auto; }
  .native-input { height: 1px; margin: -1px; opacity: 0; overflow: hidden; padding: 0; position: absolute; width: 1px; }
  .empty-state { align-items: center; color: #787774; display: flex; flex-direction: column; font-size: 13px; gap: 5px; justify-content: center; min-height: 104px; padding: 12px; text-align: center; }
  .empty-state strong { color: #37352f; }
  .upload-icon { align-items: center; background: #efefed; border-radius: 50%; color: #37352f; display: inline-flex; font-size: 19px; height: 30px; justify-content: center; width: 30px; }
  .browse, .text-action { color: #2769a8; cursor: pointer; font-size: 13px; font-weight: 650; text-decoration: none; }
  .browse:hover, .text-action:hover { text-decoration: underline; }
  .constraints { color: #9b9a97; font-size: 12px; }
  .selected-file { align-items: center; display: flex; gap: 10px; padding: 10px; }
  .file-icon { align-items: center; background: #efefed; border-radius: 6px; color: #55534e; display: inline-flex; flex: 0 0 auto; font-size: 9px; font-weight: 750; height: 34px; justify-content: center; width: 34px; }
  .file-details { display: grid; flex: 1; min-width: 0; }
  .file-details strong { color: #37352f; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .file-details span { color: #787774; font-size: 12px; }
  .remove { background: transparent; border: 0; padding: 0; }
  .error { color: #9f2d20; font-size: 13px; margin: 0; }
</style>
