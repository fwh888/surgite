<script lang="ts">
	import { onMount } from 'svelte';
	import { listRepos, type Repo } from '$lib/api';

	let repos = $state<Repo[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	onMount(async () => {
		try {
			repos = await listRepos();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load repos';
		} finally {
			loading = false;
		}
	});

	function relativeTime(iso: string | null): string {
		if (!iso) return 'never';
		const secs = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
		if (secs < 60) return 'just now';
		const mins = Math.round(secs / 60);
		if (mins < 60) return `${mins}m ago`;
		const hours = Math.round(mins / 60);
		if (hours < 24) return `${hours}h ago`;
		return `${Math.round(hours / 24)}d ago`;
	}
</script>

<main class="mx-auto max-w-2xl px-6 py-12">
	<h1 class="text-2xl font-semibold tracking-tight text-slate-900">standup</h1>
	<p class="mt-1 text-sm text-slate-500">Generate standup summaries from your git history.</p>

	<section class="mt-10">
		<h2 class="text-sm font-medium tracking-wide text-slate-500 uppercase">Repos</h2>

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
						<li class="flex items-center justify-between px-4 py-3">
							<div class="min-w-0">
								<p class="truncate font-medium text-slate-900">{repo.name}</p>
								<p class="truncate text-xs text-slate-400">{repo.path}</p>
							</div>
							<span class="ml-4 shrink-0 text-xs text-slate-500">
								ingested {relativeTime(repo.last_ingested_at)}
							</span>
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	</section>
</main>
