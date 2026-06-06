<script lang="ts">
	import { onMount } from 'svelte';
	import { generateSummary, fetchProviders, type Repo, type Summary, type ProviderInfo } from '$lib/api';

	let { repos }: { repos: Repo[] } = $props();

	let repoName = $state(''); // '' = all repos
	let days = $state(7);
	let useAi = $state(true);
	let selectedProvider = $state('');
	let providers = $state<ProviderInfo[]>([]);
	let generating = $state(false);
	let error = $state<string | null>(null);
	let result = $state<Summary | null>(null);
	let copied = $state(false);

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
		copied = false;
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

	async function copy() {
		if (!result?.ai_summary) return;
		await navigator.clipboard.writeText(result.ai_summary);
		copied = true;
		setTimeout(() => (copied = false), 1500);
	}
</script>

<section class="mt-12">
	<h2 class="text-sm font-medium tracking-wide text-slate-500 uppercase">Generate summary</h2>

	<div class="mt-3 flex flex-wrap items-center gap-3">
		<select
			bind:value={repoName}
			class="rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
		>
			<option value="">All repos</option>
			{#each repos as r (r.id)}
				<option value={r.name}>{r.name}</option>
			{/each}
		</select>

		<select
			bind:value={days}
			class="rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
		>
			<option value={7}>Last 7 days</option>
			<option value={14}>Last 14 days</option>
			<option value={30}>Last 30 days</option>
		</select>

		<label class="flex items-center gap-1.5 text-sm text-slate-600">
			<input type="checkbox" bind:checked={useAi} class="rounded border-slate-300" />
			AI summary
		</label>

		{#if useAi && providers.length > 0}
			<select
				bind:value={selectedProvider}
				class="rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
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
			class="rounded-md bg-slate-900 px-4 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
		>
			{generating ? 'Generating…' : 'Generate'}
		</button>
	</div>

	{#if error}
		<p class="mt-3 text-sm text-red-600">{error}</p>
	{/if}

	{#if result}
		<div class="mt-4">
			{#if result.ai_summary}
				<div class="relative">
					<textarea
						readonly
						rows="10"
						value={result.ai_summary}
						class="w-full rounded-lg border border-slate-200 bg-slate-50 p-4 font-mono text-sm text-slate-800 focus:outline-none"
					></textarea>
					<button
						onclick={copy}
						class="absolute top-2 right-2 rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
					>
						{copied ? 'Copied!' : 'Copy'}
					</button>
				</div>
			{:else}
				<div class="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700">
					<p class="font-medium">{result.total_commits} commits</p>
					{#if Object.keys(result.by_day).length > 0}
						<ul class="mt-2 space-y-0.5 text-slate-500">
							{#each Object.entries(result.by_day) as [day, n] (day)}
								<li>{day} — {n}</li>
							{/each}
						</ul>
					{/if}
				</div>
			{/if}
		</div>
	{/if}
</section>
