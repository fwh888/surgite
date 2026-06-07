<script lang="ts">
	import { deleteRepo, ingestAll, type Repo } from '$lib/api';
	import { relativeTime } from '$lib/time';
	import { toasts } from '$lib/toast.svelte';

	let {
		repos,
		loading,
		error,
		onChanged
	}: {
		repos: Repo[];
		loading: boolean;
		error: string | null;
		onChanged: () => void;
	} = $props();

	let ingesting = $state(false);
	let deletingId = $state<number | null>(null);

	async function handleIngestAll() {
		ingesting = true;
		try {
			const res = await ingestAll();
			if (res.errors.length > 0) {
				toasts.error(
					`ingest errors — ${res.errors.map((e) => `${e.repo}: ${e.error}`).join('; ')}`
				);
			} else {
				const added = res.results.reduce((n, r) => n + r.inserted, 0);
				toasts.success(
					added > 0
						? `ingested ${added} new commit${added === 1 ? '' : 's'}`
						: 'all repos already up to date'
				);
			}
			onChanged();
		} catch (e) {
			toasts.error(e instanceof Error ? e.message : 'ingest failed');
		} finally {
			ingesting = false;
		}
	}

	async function handleDelete(id: number) {
		deletingId = id;
		const name = repos.find((r) => r.id === id)?.name ?? 'repository';
		try {
			await deleteRepo(id);
			toasts.success(`removed ${name}`);
			onChanged();
		} catch (e) {
			toasts.error(e instanceof Error ? e.message : 'delete failed');
		} finally {
			deletingId = null;
		}
	}
</script>

<div class="mt-3 border border-border bg-bg">
	{#if loading}
		<p class="px-4 py-6 text-sm text-fg-muted">Loading…</p>
	{:else if error}
		<p class="px-4 py-6 text-sm text-err">{error}</p>
	{:else if repos.length === 0}
		<p class="px-4 py-6 text-sm text-fg-muted">No repos registered yet.</p>
	{:else}
		<div class="flex items-center justify-between border-b border-border-subtle px-4 py-2">
			<span class="text-xs text-fg-muted">{repos.length} repo{repos.length !== 1 ? 's' : ''}</span>
			<button
				onclick={handleIngestAll}
				disabled={ingesting}
				class="border border-border bg-surface px-3 py-1 text-xs text-fg transition hover:bg-surface-2 disabled:opacity-50"
			>
				{#if ingesting}
					<span class="text-fg-muted">⣾ ingesting…</span>
				{:else}
					<span class="text-accent">❯</span> ingest --all
				{/if}
			</button>
		</div>
		<ul class="divide-y divide-border-subtle">
			{#each repos as repo (repo.id)}
				<li class="flex items-center justify-between gap-4 px-4 py-3">
					<div class="min-w-0">
						<p class="truncate text-fg">{repo.name}</p>
						<p class="flex items-center gap-1 text-xs text-fg-muted">
							<span aria-hidden="true">↗</span>
							<span class="truncate">{repo.clone_url}</span>
						</p>
					</div>
					<div class="flex shrink-0 items-center gap-3">
						<span class="text-xs text-fg-faint">
							{relativeTime(repo.last_ingested_at)}
						</span>
						<button
							onclick={() => handleDelete(repo.id)}
							disabled={deletingId === repo.id}
							class="text-sm text-fg-faint transition hover:text-err disabled:opacity-50"
							aria-label="Delete {repo.name}"
						>
							✕
						</button>
					</div>
				</li>
			{/each}
		</ul>
	{/if}
</div>
