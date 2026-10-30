<script lang="ts">
  import Select from './Select.svelte';
  import type { SelectTestModel } from './select.test-support.svelte';

  let { model, searchable = true }: { model: SelectTestModel; searchable?: boolean } = $props();
</script>

<dialog open>
  <form>
    <fieldset disabled={model.fieldsetDisabled}>
      <Select options={model.options} label="Choice" id="test-choice" name="choice" value={model.value} onchange={model.select} disabled={model.disabled} search={searchable ? model.search : undefined} emptyMessage="Nothing matches" />
    </fieldset>
    <button type="button">Outside</button>
  </form>
</dialog>
