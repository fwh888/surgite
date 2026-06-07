<script lang="ts">
	import { onMount } from 'svelte';
	import { generateSummary, fetchProviders, type Repo, type Summary, type ProviderInfo } from '$lib/api';
	import { renderMarkdown } from '$lib/markdown';
	import SummaryCard from './SummaryCard.svelte';

	let { repos }: { repos: Repo[] } = $props();

	let repoName = $state(''); // '' = all repos
	let days = $state(7);
	let useAi = $state(true);
	let selectedProvider = $state('');
	let providers = $state<ProviderInfo[]>([]);
	let generating = $state(false);
	let error = $state<string | null>(null);
	let result = $state<Summary | null>(null);

	onMount(async () => {
		try {
			const data = await fetchProviders();
			providers = data.providers;
			selectedProvider = data.default;
		} catch {
			// Providers endpoint unavailable — leave list empty, dropdown hidden.
		}
	});

	function sinceDate(n: number): string {
		const d = new Date();
		d.setDate(d.getDate() - n);
		return d.toISOString().slice(0, 10);
	}

	async function generate() {
		generating = true;
		error = null;
		result = null;
		try {
			result = await generateSummary({
				repo: repoName || undefined,
				since: sinceDate(days),
				ai: useAi,
				provider: useAi ? selectedProvider || undefined : undefined
			});
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to generate summary';
		} finally {
			generating = false;
		}
	}
</script>

<section class="mt-12">
	<h2 class="text-sm font-medium tracking-wide text-slate-500 uppercase dark:text-slate-400">Generate summary</h2>

	<div class="mt-3 flex flex-wrap items-center gap-3">
		<select
			bind:value={repoName}
			class="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
		>
			<option value="">All repos</option>
			{#each repos as r (r.id)}
				<option value={r.name}>{r.name}</option>
			{/each}
		</select>

		<select
			bind:value={days}
			class="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
		>
			<option value={7}>Last 7 days</option>
			<option value={14}>Last 14 days</option>
			<option value={30}>Last 30 days</option>
		</select>

		<label class="flex items-center gap-1.5 text-sm text-slate-600 dark:text-slate-300">
			<input type="checkbox" bind:checked={useAi} class="rounded border-slate-300 dark:border-slate-600" />
			AI summary
		</label>

		{#if useAi && providers.length > 0}
			<select
				bind:value={selectedProvider}
				class="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
			>
				{#each providers as p (p.name)}
					<option value={p.name}>
						{p.name} ({p.model}){p.available ? '' : ' — no key'}
					</option>
				{/each}
			</select>
		{/if}

		<button
			onclick={generate}
			disabled={generating}
			class="rounded-md bg-slate-900 px-4 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-indigo-600 dark:hover:bg-indigo-500"
		>
			{generating ? 'Generating…' : 'Generate'}
		</button>
	</div>

	{#if error}
		<p class="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>
	{:else if result}
		{#if result.total_commits === 0}
			<p class="mt-4 text-sm text-slate-400 dark:text-slate-500">No commits in this period.</p>
		{:else}
			<div class="mt-4 space-y-3">
				{#if result.ai_summaries}
					{#each Object.entries(result.ai_summaries) as [repo, s] (repo)}
						<SummaryCard
							{repo}
							commits={result.by_repo[repo]}
							provider={s.provider}
							model={s.model}
							copyText={s.summary}
						>
							<div class="space-y-2 text-sm leading-relaxed text-slate-700 dark:text-slate-300">
								{@html renderMarkdown(s.summary)}
							</div>
						</SummaryCard>
					{/each}
				{:else if result.log_by_repo}
					{#each Object.entries(result.log_by_repo) as [repo, log] (repo)}
						<SummaryCard {repo} commits={result.by_repo[repo]} copyText={log}>
							<pre class="max-h-80 overflow-auto rounded-md bg-slate-50 p-3 font-mono text-xs leading-relaxed text-slate-700 dark:bg-slate-950 dark:text-slate-300">{log}</pre>
						</SummaryCard>
					{/each}
				{/if}
			</div>
		{/if}
	{:else if !generating}
		<p class="mt-4 text-sm text-slate-400 dark:text-slate-500">
			Pick a range and generate a summary to see it here.
		</p>
	{/if}
</section>
