<script lang="ts">
	import { deleteRepo, ingestAll, type Repo } from '$lib/api';
	import { relativeTime } from '$lib/time';

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
	let ingestError = $state<string | null>(null);
	let deletingId = $state<number | null>(null);
	let actionError = $state<string | null>(null);

	async function handleIngestAll() {
		ingesting = true;
		ingestError = null;
		try {
			const res = await ingestAll();
			if (res.errors.length > 0) {
				ingestError = res.errors.map((e) => `${e.repo}: ${e.error}`).join('; ');
			}
			onChanged();
		} catch (e) {
			ingestError = e instanceof Error ? e.message : 'Ingest failed';
		} finally {
			ingesting = false;
		}
	}

	async function handleDelete(id: number) {
		deletingId = id;
		actionError = null;
		try {
			await deleteRepo(id);
			onChanged();
		} catch (e) {
			actionError = e instanceof Error ? e.message : 'Delete failed';
		} finally {
			deletingId = null;
		}
	}
</script>

<div class="mt-3 rounded-lg border border-slate-200 bg-white">
	{#if loading}
		<p class="px-4 py-6 text-sm text-slate-400">Loading…</p>
	{:else if error}
		<p class="px-4 py-6 text-sm text-red-600">{error}</p>
	{:else if repos.length === 0}
		<p class="px-4 py-6 text-sm text-slate-400">No repos registered yet.</p>
	{:else}
		<div class="flex items-center justify-between px-4 py-2 border-b border-slate-100">
			<span class="text-xs text-slate-500">{repos.length} repo{repos.length !== 1 ? 's' : ''}</span>
			<button
				onclick={handleIngestAll}
				disabled={ingesting}
				class="rounded-md bg-slate-900 px-3 py-1 text-xs font-medium text-white hover:bg-slate-700 disabled:opacity-50"
			>
				{ingesting ? 'Ingesting…' : 'Ingest all'}
			</button>
		</div>
		<ul class="divide-y divide-slate-100">
			{#each repos as repo (repo.id)}
				<li class="flex items-center justify-between gap-4 px-4 py-3">
					<div class="min-w-0">
						<p class="truncate font-medium text-slate-900">{repo.name}</p>
						<p class="truncate text-xs text-slate-400">
							<span class="inline-block mr-1">🌐</span>
							{repo.clone_url}
						</p>
					</div>
					<div class="flex shrink-0 items-center gap-3">
						<span class="text-xs text-slate-500">
							ingested {relativeTime(repo.last_ingested_at)}
						</span>
						<button
							onclick={() => handleDelete(repo.id)}
							disabled={deletingId === repo.id}
							class="text-sm text-slate-400 hover:text-red-600 disabled:opacity-50"
							aria-label="Delete {repo.name}"
						>
							✕
						</button>
					</div>
				</li>
			{/each}
		</ul>
	{/if}

	{#if ingestError}
		<p class="border-t border-slate-100 px-4 py-2 text-xs text-red-600">{ingestError}</p>
	{/if}
	{#if actionError}
		<p class="border-t border-slate-100 px-4 py-2 text-xs text-red-600">{actionError}</p>
	{/if}
</div>
