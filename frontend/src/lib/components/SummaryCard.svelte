<script lang="ts">
	import type { Snippet } from 'svelte';
	import { toasts } from '$lib/toast.svelte';

	let {
		repo,
		commits,
		provider,
		model,
		copyText,
		children
	}: {
		repo: string;
		commits?: number;
		provider?: string;
		model?: string;
		copyText?: string;
		children: Snippet;
	} = $props();

	let copied = $state(false);

	async function copy() {
		if (!copyText) return;
		try {
			await navigator.clipboard.writeText(copyText);
			copied = true;
			setTimeout(() => (copied = false), 1500);
		} catch {
			// Clipboard unavailable (e.g. an insecure, non-localhost HTTP origin).
			toasts.error('Could not copy — clipboard needs a secure (HTTPS) context');
		}
	}
</script>

<div
	class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm transition hover:shadow-md dark:border-slate-800 dark:bg-slate-900"
>
	<div
		class="flex items-center justify-between gap-3 border-b border-slate-100 bg-slate-50/70 px-4 py-2.5 dark:border-slate-800 dark:bg-slate-800/40"
	>
		<div class="flex min-w-0 items-center gap-2">
			<svg
				xmlns="http://www.w3.org/2000/svg"
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				stroke-width="2"
				stroke-linecap="round"
				stroke-linejoin="round"
				class="h-4 w-4 shrink-0 text-slate-400"
			>
				<path d="M3 3v18h18" opacity="0" />
				<path d="M6 3v12a3 3 0 0 0 3 3h9" />
				<circle cx="6" cy="18" r="3" />
				<circle cx="18" cy="6" r="3" />
				<path d="M18 9v0a9 9 0 0 1-9 9" />
			</svg>
			<h3 class="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">{repo}</h3>
		</div>

		<div class="flex shrink-0 items-center gap-2">
			{#if commits != null}
				<span
					class="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300"
				>
					{commits} commit{commits === 1 ? '' : 's'}
				</span>
			{/if}
			{#if provider}
				<span
					class="inline-flex items-center rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300"
					title={model ? `${provider} · ${model}` : provider}
				>
					{provider}{model ? ` · ${model}` : ''}
				</span>
			{/if}
			{#if copyText}
				<button
					onclick={copy}
					class="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-xs text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
					aria-label="Copy to clipboard"
				>
					{#if copied}
						<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="h-3.5 w-3.5 text-green-600 dark:text-green-400"><path d="M20 6 9 17l-5-5" /></svg>
						<span class="text-green-600 dark:text-green-400">Copied</span>
					{:else}
						<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="h-3.5 w-3.5"><rect width="14" height="14" x="8" y="8" rx="2" /><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" /></svg>
						Copy
					{/if}
				</button>
			{/if}
		</div>
	</div>

	<div class="px-4 py-4">
		{@render children()}
	</div>
</div>
