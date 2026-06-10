<script lang="ts">
	let { rows = 3 }: { rows?: number } = $props();
</script>

{#each Array(rows) as _}
	<div class="flex items-center justify-between px-4 py-3">
		<div class="h-4 w-40 animate-pulse rounded bg-surface-2"></div>
		<div class="h-3 w-16 animate-pulse rounded bg-surface-2"></div>
	</div>
{/each}
