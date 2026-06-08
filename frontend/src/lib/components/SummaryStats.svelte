<script lang="ts">
	import { dailySeries, sparkChar } from '$lib/stats';

	let {
		totalCommits,
		byRepo,
		byDay
	}: {
		totalCommits: number;
		byRepo: Record<string, number>;
		byDay: Record<string, number>;
	} = $props();

	const series = $derived(dailySeries(byDay));
	const maxDay = $derived(series.reduce((m, s) => Math.max(m, s.count), 0));
	const activeDays = $derived(series.filter((s) => s.count > 0).length);

	const repoEntries = $derived(Object.entries(byRepo).sort((a, b) => b[1] - a[1]));
	const maxRepo = $derived(repoEntries.reduce((m, [, n]) => Math.max(m, n), 0));

	const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? '' : 's'}`;
</script>

<div class="mt-3 border border-border bg-surface px-4 py-3 text-xs">
	<p class="text-fg-muted">
		<span class="text-fg">{plural(totalCommits, 'commit')}</span>
		· {plural(repoEntries.length, 'repo')}
		· {plural(activeDays, 'active day')}
	</p>

	{#if repoEntries.length > 0}
		<ul class="mt-3 space-y-1">
			{#each repoEntries as [repo, count] (repo)}
				<li class="flex items-center gap-2">
					<span class="w-32 shrink-0 truncate text-fg-muted" title={repo}>{repo}</span>
					<span class="h-2 flex-1 bg-surface-2" aria-hidden="true">
						<span
							class="block h-full bg-accent"
							style="width: {maxRepo === 0 ? 0 : Math.round((count / maxRepo) * 100)}%"
						></span>
					</span>
					<span class="w-8 shrink-0 text-right text-fg-muted">{count}</span>
				</li>
			{/each}
		</ul>
	{/if}

	{#if series.length > 1}
		<div class="mt-3 flex items-baseline gap-2">
			<span class="shrink-0 text-fg-faint">activity</span>
			<span
				class="break-all tracking-widest text-accent"
				role="img"
				aria-label="Commits per day from {series[0].day} to {series[series.length - 1]
					.day}, peak {maxDay} in a day"
			>{#each series as s (s.day)}<span title="{s.day}: {plural(s.count, 'commit')}"
					>{sparkChar(s.count, maxDay)}</span
				>{/each}</span>
		</div>
	{/if}
</div>
