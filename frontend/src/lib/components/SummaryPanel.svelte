<script lang="ts">
	import { onMount } from 'svelte';
	import { generateSummary, fetchProviders, type Repo, type Summary, type ProviderInfo } from '$lib/api';
	import { renderMarkdown } from '$lib/markdown';
	import SummaryCard from './SummaryCard.svelte';
	import SummaryStats from './SummaryStats.svelte';

	let { repos }: { repos: Repo[] } = $props();

	let repoName = $state('');
	let range = $state('7');
	let customSince = $state('');
	let customUntil = $state('');
	let author = $state('');
	let useAi = $state(true);
	let selectedProvider = $state('');
	let providers = $state<ProviderInfo[]>([]);
	let generating = $state(false);
	let error = $state<string | null>(null);
	let result = $state<Summary | null>(null);

	const BRAILLE = ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷'];
	let spinnerIdx = 0;
	let spinnerFrame = $state(BRAILLE[0]);
	let spinnerInterval: ReturnType<typeof setInterval> | undefined;

	$effect(() => {
		if (generating) {
			spinnerIdx = 0;
			spinnerInterval = setInterval(() => {
				spinnerIdx = (spinnerIdx + 1) % BRAILLE.length;
				spinnerFrame = BRAILLE[spinnerIdx];
			}, 100);
		} else {
			if (spinnerInterval) clearInterval(spinnerInterval);
		}
		return () => { if (spinnerInterval) clearInterval(spinnerInterval); };
	});

	onMount(async () => {
		try {
			const data = await fetchProviders();
			providers = data.providers;
			selectedProvider = data.default;
		} catch {
			// Providers endpoint unavailable
		}
	});

	function sinceDate(n: number): string {
		const d = new Date();
		d.setDate(d.getDate() - n);
		return d.toISOString().slice(0, 10);
	}

	function buildCliEcho(): string {
		const parts = ['standup'];
		if (repoName) parts.push(`--repo ${repoName}`);
		const custom = range === 'custom';
		if (custom && customSince) {
			parts.push(`--since ${customSince}`);
		} else if (!custom) {
			parts.push(`--since ${range}.days.ago`);
		}
		if (custom && customUntil) parts.push(`--until ${customUntil}`);
		if (author.trim()) parts.push(`--author "${author.trim()}"`);
		if (useAi) {
			parts.push('--summarize');
			if (selectedProvider) parts.push(`--provider ${selectedProvider}`);
		}
		return `$ ${parts.join(' ')}`;
	}

	async function generate() {
		generating = true;
		error = null;
		result = null;
		try {
			const custom = range === 'custom';
			const since = custom ? customSince || undefined : sinceDate(Number(range));
			const until = custom ? customUntil || undefined : undefined;
			result = await generateSummary({
				repo: repoName || undefined,
				since,
				until,
				author: author.trim() || undefined,
				ai: useAi,
				provider: useAi ? selectedProvider || undefined : undefined
			});
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to generate summary';
		} finally {
			generating = false;
		}
	}

	const inputCls = 'border border-border bg-bg px-2 py-1.5 text-sm text-fg';
</script>

<section class="mt-8">
	<h2 class="text-sm text-fg-muted">
		<span class="text-accent">~/summary</span> <span aria-hidden="true">❯</span>
	</h2>

	<div class="mt-3 flex flex-wrap items-center gap-3">
		<select bind:value={repoName} class={inputCls}>
			<option value="">All repos</option>
			{#each repos as r (r.id)}
				<option value={r.name}>{r.name}</option>
			{/each}
		</select>

		<select bind:value={range} class={inputCls}>
			<option value="7">Last 7 days</option>
			<option value="14">Last 14 days</option>
			<option value="30">Last 30 days</option>
			<option value="custom">Custom range</option>
		</select>

		{#if range === 'custom'}
			<input type="date" bind:value={customSince} aria-label="From date" class={inputCls} />
			<span class="text-sm text-fg-muted">to</span>
			<input type="date" bind:value={customUntil} aria-label="To date" class={inputCls} />
		{/if}

		<input
			type="text"
			bind:value={author}
			placeholder="Author (optional)"
			aria-label="Filter by author"
			class="{inputCls} w-44"
		/>

		<label class="flex items-center gap-1.5 text-sm text-fg-muted">
			<input type="checkbox" bind:checked={useAi} class="accent-accent" />
			AI summary
		</label>

		{#if useAi && providers.length > 0}
			<select bind:value={selectedProvider} class={inputCls}>
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
			class="border border-border bg-accent px-4 py-1.5 text-sm font-medium text-accent-contrast transition hover:bg-accent-hover disabled:opacity-50"
		>
			{#if generating}
				{spinnerFrame} generating…
			{:else}
				❯ generate
			{/if}
		</button>
	</div>

	{#if error}
		<p class="mt-3 text-sm text-err">{error}</p>
	{:else if result}
		{#if result.total_commits === 0}
			<p class="mt-4 text-sm text-fg-muted">No commits in this period.</p>
		{:else}
			<div class="mt-2 text-xs text-fg-faint">{buildCliEcho()}</div>
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
							typewriter
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
	{:else if !generating}
		<p class="mt-4 text-sm text-fg-muted">
			Pick a range and generate a summary to see it here.
		</p>
	{/if}
</section>
