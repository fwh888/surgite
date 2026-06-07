<script lang="ts">
	import { addRepo, ingestRepo } from '$lib/api';
	import { toasts } from '$lib/toast.svelte';

	let { onAdded }: { onAdded: () => void } = $props();

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
				toasts.success(`added ${repo.name}`);
				onAdded();
			} catch (e2) {
				ingestState = 'error';
				ingestError = e2 instanceof Error ? e2.message : 'ingest failed';
				onAdded();
			}
		} catch (e2) {
			error = e2 instanceof Error ? e2.message : 'failed to add repo';
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
				<span class="text-accent" aria-hidden="true">❯</span>
				<input
					bind:value={input}
					use:focusOnMount
					placeholder="https://github.com/user/repo.git"
					class="flex-1 border border-border bg-bg px-2 py-1.5 text-sm text-fg placeholder:text-fg-faint"
				/>
				<button
					type="submit"
					disabled={submitting || ingestState === 'ingesting'}
					class="border border-border bg-surface px-3 py-1.5 text-sm text-fg transition hover:bg-surface-2 disabled:opacity-50"
				>
					{submitting ? 'adding…' : ingestState === 'ingesting' ? '⣾ ingesting…' : 'add-repo'}
				</button>
				<button type="button" onclick={cancel} class="px-2 py-1.5 text-sm text-fg-muted transition hover:text-fg">
					cancel
				</button>
			</div>
		</form>
		{#if ingestState === 'ingesting'}
			<p class="mt-2 text-xs text-fg-muted">ingesting commits…</p>
		{/if}
		{#if ingestError}
			<p class="mt-2 text-xs text-warn">repo added but ingest failed: {ingestError}</p>
		{/if}
		{#if error}
			<p class="mt-2 text-xs text-err">{error}</p>
		{/if}
	{:else}
		<button
			onclick={() => (open = true)}
			class="border border-border bg-surface px-3 py-1.5 text-sm text-fg transition hover:bg-surface-2"
		>
			<span class="text-accent">❯</span> add-repo
		</button>
	{/if}
</div>
