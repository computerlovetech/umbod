<script lang="ts">
  type Props = {
    value: string;
  };

  let { value }: Props = $props();

  const formatter = new Intl.DateTimeFormat('en', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
    timeZone: 'UTC',
    timeZoneName: 'short'
  });

  const parsedDate = $derived(new Date(value));
  const isValid = $derived(!Number.isNaN(parsedDate.getTime()));
  const displayValue = $derived(isValid ? formatter.format(parsedDate) : value);
</script>

<time datetime={isValid ? parsedDate.toISOString() : value} title={isValid ? `Exact time: ${value}` : undefined}>
  {displayValue}
</time>

<style>
  time {
    font-variant-numeric: tabular-nums;
    overflow-wrap: anywhere;
    white-space: normal;
  }
</style>
