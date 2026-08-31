<script lang="ts">
	import { onMount } from 'svelte';
	import { fetchMySummaries, type MySummary, type SummaryParams } from '$lib/api';
	import { relativeTime } from '$lib/time';

	let tab = $state<'mine' | 'shared'>('mine');
	let summaries = $state<MySummary[]>([]);
	let total = $state(0);
	let loading = $state(true);
	let error = $state<string | null>(null);

	async function load() {
		loading = true;
		error = null;
		try {
			const out = await fetchMySummaries();
			summaries = out.summaries;
			total = out.total;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load summaries';
		} finally {
			loading = false;
		}
	}

	onMount(load);

	function describeParams(p: SummaryParams): string {
		const bits: string[] = [];
		if (p.repo) bits.push(`repo=${p.repo}`);
		if (p.since) bits.push(`since=${p.since}`);
		if (p.until) bits.push(`until=${p.until}`);
		if (p.author) bits.push(`author=${p.author}`);
		if (p.ai) bits.push('ai');
		return bits.length ? bits.join(' · ') : 'all';
	}
</script>

<svelte:head>
	<title>summaries — surgite</title>
</svelte:head>

<main class="mx-auto min-h-screen max-w-2xl px-4 py-6 sm:px-6 sm:py-10">
	<div class="border border-border bg-surface">
		<div class="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
			<span class="flex-1 text-xs text-fg-muted">surgite</span>
			<a href="/" class="text-xs text-fg-muted transition hover:text-fg"> ← home </a>
		</div>

		<div class="px-4 py-6 sm:px-6">
			<div class="flex items-center gap-2">
				<span class="text-accent" aria-hidden="true">&gt;_</span>
				<h1 class="text-lg font-semibold text-fg">summaries</h1>
				<span class="cursor" aria-hidden="true"></span>
			</div>
			<p class="mt-1 text-sm text-fg-muted">Saved, shareable summary links.</p>
			<div class="mt-1 border-b border-dashed border-border-subtle"></div>

			<div class="mt-3 flex gap-1 border-b border-border-subtle text-sm">
				<button
					onclick={() => (tab = 'mine')}
					class="border-b-2 px-3 py-1.5 transition {tab === 'mine'
						? 'border-accent text-fg'
						: 'border-transparent text-fg-muted hover:text-fg'}"
				>
					Created by me <span class="text-fg-faint">({total})</span>
				</button>
				<button
					onclick={() => (tab = 'shared')}
					class="border-b-2 px-3 py-1.5 transition {tab === 'shared'
						? 'border-accent text-fg'
						: 'border-transparent text-fg-muted hover:text-fg'}"
				>
					Shared with me
				</button>
			</div>
		</div>

		{#if tab === 'mine'}
			<section class="px-4 pb-6 sm:px-6">
				{#if loading}
					<p class="text-sm text-fg-muted">⣾ loading…</p>
				{:else if error}
					<p class="text-sm text-err">{error}</p>
				{:else if summaries.length === 0}
					<p class="text-sm text-fg-muted">No shared summaries yet.</p>
				{:else}
					<ul class="divide-y divide-border-subtle border border-border bg-bg">
						{#each summaries as s (s.slug)}
							<li class="flex items-center justify-between gap-4 px-3 py-2.5">
								<div class="min-w-0 flex-1">
									<p class="truncate font-mono text-sm text-fg">{s.slug}</p>
									<p class="truncate text-xs text-fg-muted">
										{describeParams(s.params)}
									</p>
								</div>
								<div class="flex shrink-0 items-center gap-3 text-xs text-fg-faint">
									<span>created {relativeTime(s.created_at)}</span>
									<span>expires {relativeTime(s.expires_at)}</span>
									<a
										href={'/s/' + encodeURIComponent(s.slug)}
										class="text-accent underline transition hover:text-accent-hover"
									>
										open
									</a>
								</div>
							</li>
						{/each}
					</ul>
				{/if}
			</section>
		{:else}
			<!-- TODO slice 4: cross-user share isn't a thing yet — that page exists for the 0.6.0 feature. -->
			<section class="px-4 pb-6 sm:px-6">
				<p class="text-sm text-fg-muted">No shared-with-me summaries yet.</p>
			</section>
		{/if}
	</div>
</main>
