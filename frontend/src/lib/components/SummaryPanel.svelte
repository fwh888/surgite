<script lang="ts">
	import { onMount } from 'svelte';
	import {
		generateSummary,
		streamSummary,
		createShare,
		fetchProviders,
		type Repo,
		type ProviderInfo,
		type SummaryParams
	} from '$lib/api';
	import { renderMarkdown } from '$lib/markdown';
	import { toasts } from '$lib/toast.svelte';
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
	let sharing = $state(false);
	let error = $state<string | null>(null);

	// Result state. `stats` is set once (from the JSON body or the SSE `meta`
	// event); `summaries` fills in token-by-token while streaming; `logByRepo`
	// holds the non-AI formatted logs.
	type RepoSummary = { text: string; provider: string; model: string; error: boolean };
	let stats = $state<{
		total: number;
		byRepo: Record<string, number>;
		byDay: Record<string, number>;
	} | null>(null);
	let summaries = $state<Record<string, RepoSummary>>({});
	let logByRepo = $state<Record<string, string> | null>(null);
	let isAiResult = $state(false);
	let lastParams: SummaryParams | null = null;
	let controller: AbortController | undefined;

	const rangeInvalid = $derived(
		range === 'custom' && !!customSince && !!customUntil && customSince > customUntil
	);
	const hasResult = $derived(stats !== null);

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
		return () => {
			if (spinnerInterval) clearInterval(spinnerInterval);
		};
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

	function currentParams(): SummaryParams {
		const custom = range === 'custom';
		return {
			repo: repoName || undefined,
			since: custom ? customSince || undefined : sinceDate(Number(range)),
			until: custom ? customUntil || undefined : undefined,
			author: author.trim() || undefined,
			ai: useAi,
			provider: useAi ? selectedProvider || undefined : undefined
		};
	}

	async function generate() {
		controller?.abort();
		controller = new AbortController();
		generating = true;
		error = null;
		stats = null;
		summaries = {};
		logByRepo = null;
		isAiResult = useAi;
		const params = currentParams();
		lastParams = params;
		try {
			if (useAi) {
				await streamSummary(
					params,
					{
						onMeta: (m) => {
							stats = { total: m.total_commits, byRepo: m.by_repo, byDay: m.by_day };
							summaries = Object.fromEntries(
								m.repos.map((r) => [
									r,
									{ text: '', provider: m.provider, model: m.model, error: false }
								])
							);
						},
						onDelta: (repo, text) => {
							if (summaries[repo]) summaries[repo].text += text;
						},
						onRepoDone: (repo, provider, model) => {
							if (summaries[repo]) {
								summaries[repo].provider = provider;
								summaries[repo].model = model;
							}
						},
						onRepoError: (repo, detail) => {
							if (summaries[repo]) {
								summaries[repo].text = detail;
								summaries[repo].error = true;
							}
						}
					},
					controller.signal
				);
			} else {
				const r = await generateSummary(params, controller.signal);
				stats = { total: r.total_commits, byRepo: r.by_repo, byDay: r.by_day };
				logByRepo = r.log_by_repo;
			}
		} catch (e) {
			if (e instanceof DOMException && e.name === 'AbortError') return;
			error = e instanceof Error ? e.message : 'Failed to generate summary';
		} finally {
			generating = false;
		}
	}

	function asMarkdown(): string {
		const parts: string[] = [];
		if (isAiResult) {
			for (const [repo, s] of Object.entries(summaries)) parts.push(`## ${repo}\n\n${s.text}`);
		} else if (logByRepo) {
			for (const [repo, log] of Object.entries(logByRepo))
				parts.push(`## ${repo}\n\n\`\`\`\n${log}\n\`\`\``);
		}
		return parts.join('\n\n');
	}

	async function copyMarkdown() {
		try {
			await navigator.clipboard.writeText(asMarkdown());
			toasts.success('copied as markdown');
		} catch {
			toasts.error('could not copy — clipboard needs a secure (HTTPS) context');
		}
	}

	async function share() {
		if (!lastParams) return;
		sharing = true;
		try {
			const { slug, expires_at } = await createShare(lastParams);
			const url = `${location.origin}/s/${slug}`;
			await navigator.clipboard.writeText(url);
			const expires = new Date(expires_at).toLocaleDateString();
			toasts.success(`share link copied (expires ${expires})`);
		} catch (e) {
			toasts.error(e instanceof Error ? e.message : 'could not create share link');
		} finally {
			sharing = false;
		}
	}

	const inputCls = 'border border-border bg-bg px-2 py-1.5 text-sm text-fg';
	const actionCls =
		'inline-flex items-center gap-1 border border-border px-3 py-1 text-xs text-fg-muted transition hover:bg-surface hover:text-fg disabled:opacity-50';
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
			<input type="date" bind:value={customSince} max={customUntil || undefined} aria-label="From date" class={inputCls} />
			<span class="text-sm text-fg-muted">to</span>
			<input type="date" bind:value={customUntil} min={customSince || undefined} aria-label="To date" class={inputCls} />
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
			disabled={generating || rangeInvalid}
			class="border border-border bg-accent px-4 py-1.5 text-sm font-medium text-accent-contrast transition hover:bg-accent-hover disabled:opacity-50"
		>
			{#if generating}
				{spinnerFrame} generating…
			{:else}
				❯ generate
			{/if}
		</button>
	</div>

	{#if rangeInvalid}
		<p class="mt-3 text-sm text-err">"From" must be on or before "to".</p>
	{/if}

	{#if error}
		<p class="mt-3 text-sm text-err">{error}</p>
	{:else if hasResult && stats}
		{#if stats.total === 0}
			<p class="mt-4 text-sm text-fg-muted">No commits in this period.</p>
		{:else}
			<div class="mt-2 flex flex-wrap items-center justify-between gap-2">
				<span class="text-xs text-fg-faint">{buildCliEcho()}</span>
				<div class="flex items-center gap-2">
					<button onclick={copyMarkdown} disabled={generating} class={actionCls}>
						❯ copy markdown
					</button>
					<button onclick={share} disabled={generating || sharing} class={actionCls}>
						{sharing ? 'sharing…' : '❯ share link'}
					</button>
				</div>
			</div>
			<SummaryStats totalCommits={stats.total} byRepo={stats.byRepo} byDay={stats.byDay} />
			<div class="mt-3 space-y-3">
				{#if isAiResult}
					{#each Object.entries(summaries) as [repo, s] (repo)}
						<SummaryCard
							{repo}
							commits={stats.byRepo[repo]}
							provider={s.provider}
							model={s.model}
							copyText={s.text}
						>
							{#if s.error}
								<p class="text-sm text-err">{s.text}</p>
							{:else if s.text}
								<div class="space-y-2 text-sm leading-relaxed text-fg">
									{@html renderMarkdown(s.text)}
								</div>
							{:else}
								<p class="text-sm text-fg-muted">{spinnerFrame} waiting for tokens…</p>
							{/if}
						</SummaryCard>
					{/each}
				{:else if logByRepo}
					{#each Object.entries(logByRepo) as [repo, log] (repo)}
						<SummaryCard {repo} commits={stats.byRepo[repo]} copyText={log}>
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
