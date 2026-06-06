<script lang="ts">
	import { addRepo } from '$lib/api';

	let { onAdded }: { onAdded: () => void } = $props();

	let open = $state(false);
	let path = $state('');
	let submitting = $state(false);
	let error = $state<string | null>(null);

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		if (!path.trim()) return;
		submitting = true;
		error = null;
		try {
			await addRepo(path.trim());
			path = '';
			open = false;
			onAdded();
		} catch (e2) {
			error = e2 instanceof Error ? e2.message : 'Failed to add repo';
		} finally {
			submitting = false;
		}
	}

	function cancel() {
		open = false;
		error = null;
		path = '';
	}
</script>

<div class="mt-3">
	{#if open}
		<form onsubmit={submit} class="flex items-center gap-2">
			<!-- svelte-ignore a11y_autofocus -->
			<input
				bind:value={path}
				autofocus
				placeholder="/path/to/local/repo"
				class="flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
			/>
			<button
				type="submit"
				disabled={submitting}
				class="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
			>
				{submitting ? 'Adding…' : 'Add'}
			</button>
			<button type="button" onclick={cancel} class="px-2 py-1.5 text-sm text-slate-500 hover:text-slate-800">
				Cancel
			</button>
		</form>
		{#if error}
			<p class="mt-2 text-xs text-red-600">{error}</p>
		{/if}
	{:else}
		<button
			onclick={() => (open = true)}
			class="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
		>
			+ Add repo
		</button>
	{/if}
</div>
