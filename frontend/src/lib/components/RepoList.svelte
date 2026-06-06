<script lang="ts">
	import { deleteRepo, ingestRepo, type Repo } from '$lib/api';
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

	// id of the repo currently being ingested/deleted, so we can disable just that row.
	let busyId = $state<number | null>(null);
	let actionError = $state<string | null>(null);

	async function run(id: number, fn: (id: number) => Promise<unknown>, label: string) {
		busyId = id;
		actionError = null;
		try {
			await fn(id);
			onChanged();
		} catch (e) {
			actionError = e instanceof Error ? e.message : `${label} failed`;
		} finally {
			busyId = null;
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
		<ul class="divide-y divide-slate-100">
			{#each repos as repo (repo.id)}
				<li class="flex items-center justify-between gap-4 px-4 py-3">
					<div class="min-w-0">
						<p class="truncate font-medium text-slate-900">{repo.name}</p>
						<p class="truncate text-xs text-slate-400">{repo.path}</p>
					</div>
					<div class="flex shrink-0 items-center gap-3">
						<span class="text-xs text-slate-500">
							ingested {relativeTime(repo.last_ingested_at)}
						</span>
						<button
							onclick={() => run(repo.id, ingestRepo, 'Ingest')}
							disabled={busyId === repo.id}
							class="rounded-md bg-slate-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-slate-700 disabled:opacity-50"
						>
							{busyId === repo.id ? '…' : 'Ingest now'}
						</button>
						<button
							onclick={() => run(repo.id, deleteRepo, 'Delete')}
							disabled={busyId === repo.id}
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

	{#if actionError}
		<p class="border-t border-slate-100 px-4 py-2 text-xs text-red-600">{actionError}</p>
	{/if}
</div>
