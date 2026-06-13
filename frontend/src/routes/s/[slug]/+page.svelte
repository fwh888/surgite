<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { fetchShare, generateSummary, type Summary } from '$lib/api';
	import { renderMarkdown } from '$lib/markdown';
	import SummaryCard from '$lib/components/SummaryCard.svelte';
	import SummaryStats from '$lib/components/SummaryStats.svelte';

	let loading = $state(true);
	let error = $state<string | null>(null);
	let result = $state<Summary | null>(null);

	onMount(async () => {
		const slug = page.params.slug;
		if (!slug) {
			error = 'Missing share link';
			loading = false;
			return;
		}
		try {
			const shared = await fetchShare(slug);
			result = await generateSummary(shared.params);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load shared summary';
		} finally {
			loading = false;
		}
	});
</script>

<svelte:head>
	<title>shared summary — standup</title>
</svelte:head>

<main class="mx-auto min-h-screen max-w-2xl px-4 py-6 sm:px-6 sm:py-10">
	<div class="border border-border bg-surface">
		<div class="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
			<span class="flex-1 text-xs text-fg-muted">nick@standup: ~/shared</span>
		</div>

		<div class="px-4 py-6 sm:px-6">
			<div class="flex items-center gap-2">
				<span class="text-accent" aria-hidden="true">&gt;_</span>
				<h1 class="text-lg font-semibold text-fg">shared summary</h1>
			</div>
			<p class="mt-1 text-sm text-fg-muted">
				A read-only standup summary shared via link.
				<a href="/" class="text-accent underline hover:text-accent-hover">open standup ❯</a>
			</p>
			<div class="mt-1 border-b border-dashed border-border-subtle"></div>

			{#if loading}
				<p class="mt-4 text-sm text-fg-muted">⣾ loading shared summary…</p>
			{:else if error}
				<p class="mt-4 text-sm text-err">{error}</p>
			{:else if result}
				{#if result.total_commits === 0}
					<p class="mt-4 text-sm text-fg-muted">No commits in this period.</p>
				{:else}
					<SummaryStats
						totalCommits={result.total_commits}
						byRepo={result.by_repo}
						byDay={result.by_day}
					/>
					<div class="mt-3 space-y-3">
						{#if result.ai_summaries}
							{#each Object.entries(result.ai_summaries) as [repo, s] (repo)}
								<SummaryCard
									{repo}
									commits={result.by_repo[repo]}
									provider={s.provider}
									model={s.model}
									copyText={s.summary}
								>
									<div class="space-y-2 text-sm leading-relaxed text-fg">
										{@html renderMarkdown(s.summary)}
									</div>
								</SummaryCard>
							{/each}
						{:else if result.log_by_repo}
							{#each Object.entries(result.log_by_repo) as [repo, log] (repo)}
								<SummaryCard {repo} commits={result.by_repo[repo]} copyText={log}>
									<pre class="max-h-80 overflow-auto bg-bg p-3 text-xs leading-relaxed text-fg">{log}</pre>
								</SummaryCard>
							{/each}
						{/if}
					</div>
				{/if}
			{/if}
		</div>
	</div>
</main>
