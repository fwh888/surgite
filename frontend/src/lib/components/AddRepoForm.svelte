<script lang="ts">
	import { addRepo, ingestRepo } from '$lib/api';
	import { toasts } from '$lib/toast.svelte';

	let { onAdded }: { onAdded: () => void } = $props();

	// Focus the field when the form opens, without the `autofocus` attribute
	// (which is an accessibility anti-pattern svelte-check flags).
	function focusOnMount(node: HTMLInputElement) {
		node.focus();
	}

	let open = $state(false);
	let input = $state('');
	let submitting = $state(false);
	let ingestState = $state<'idle' | 'ingesting' | 'error'>('idle');
	let ingestError = $state<string | null>(null);
	let error = $state<string | null>(null);

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		if (!input.trim()) return;
		submitting = true;
		error = null;
		ingestState = 'idle';
		ingestError = null;
		try {
			const repo = await addRepo(input.trim());
			submitting = false;
			ingestState = 'ingesting';
			input = '';
			try {
				await ingestRepo(repo.id);
				ingestState = 'idle';
				open = false;
				toasts.success(`Added ${repo.name}`);
				onAdded();
			} catch (e2) {
				ingestState = 'error';
				ingestError = e2 instanceof Error ? e2.message : 'Ingest failed';
				onAdded();
			}
		} catch (e2) {
			error = e2 instanceof Error ? e2.message : 'Failed to add repo';
			submitting = false;
		}
	}

	function cancel() {
		open = false;
		error = null;
		ingestError = null;
		input = '';
		submitting = false;
		ingestState = 'idle';
	}
</script>

<div class="mt-3">
	{#if open}
		<form onsubmit={submit} class="flex flex-col gap-2">
			<div class="flex items-center gap-2">
				<input
					bind:value={input}
					use:focusOnMount
					placeholder="https://github.com/user/repo.git"
					class="flex-1 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:placeholder:text-slate-500"
				/>
				<button
					type="submit"
					disabled={submitting || ingestState === 'ingesting'}
					class="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-indigo-600 dark:hover:bg-indigo-500"
				>
					{submitting ? 'Adding…' : ingestState === 'ingesting' ? 'Ingesting…' : 'Add'}
				</button>
				<button type="button" onclick={cancel} class="px-2 py-1.5 text-sm text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200">
					Cancel
				</button>
			</div>
		</form>
		{#if ingestState === 'ingesting'}
			<p class="mt-2 text-xs text-slate-500 dark:text-slate-400">Ingesting commits…</p>
		{/if}
		{#if ingestError}
			<p class="mt-2 text-xs text-amber-600 dark:text-amber-400">Repo added but ingest failed: {ingestError}</p>
		{/if}
		{#if error}
			<p class="mt-2 text-xs text-red-600 dark:text-red-400">{error}</p>
		{/if}
	{:else}
		<button
			onclick={() => (open = true)}
			class="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
		>
			+ Add repo
		</button>
	{/if}
</div>
