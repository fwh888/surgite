<script lang="ts">
	import type { Snippet } from 'svelte';
	import { toasts } from '$lib/toast.svelte';
	import { downloadText, summaryFilename } from '$lib/download';

	let {
		repo,
		commits,
		provider,
		model,
		copyText,
		typewriter = false,
		children
	}: {
		repo: string;
		commits?: number;
		provider?: string;
		model?: string;
		copyText?: string;
		typewriter?: boolean;
		children: Snippet;
	} = $props();

	let copied = $state(false);
	let revealed = $state(false);
	let container: HTMLDivElement | undefined = $state();

	$effect(() => {
		if (!typewriter) { revealed = true; return; }
		if (revealed) return;
		const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
		if (prefersReduced) { revealed = true; return; }
		const el = container;
		if (!el) return;
		el.style.opacity = '0';
		const timer = setTimeout(() => {
			el.style.transition = 'opacity 0.6s ease';
			el.style.opacity = '1';
			revealed = true;
		}, 150);
		return () => clearTimeout(timer);
	});

	async function copy() {
		if (!copyText) return;
		try {
			await navigator.clipboard.writeText(copyText);
			copied = true;
			setTimeout(() => (copied = false), 1500);
		} catch {
			toasts.error('could not copy — clipboard needs a secure (HTTPS) context');
		}
	}

	function download() {
		if (!copyText) return;
		downloadText(summaryFilename(repo, provider ? 'summary' : 'log'), copyText);
	}
</script>

<div class="overflow-hidden border border-border bg-surface">
	<div class="flex items-center justify-between gap-3 border-b border-border-subtle bg-surface-2 px-4 py-2.5">
		<div class="flex min-w-0 items-center gap-2">
			<span class="text-fg-faint" aria-hidden="true">⎔</span>
			<h3 class="truncate text-sm font-semibold text-fg">{repo}</h3>
		</div>

		<div class="flex shrink-0 items-center gap-2">
			{#if commits != null}
				<span class="inline-flex items-center border border-border-subtle px-2 py-0.5 text-xs text-fg-muted">
					{commits} commit{commits === 1 ? '' : 's'}
				</span>
			{/if}
			{#if provider}
				<span
					class="inline-flex items-center border border-border-subtle px-2 py-0.5 text-xs text-accent"
					title={model ? `${provider} · ${model}` : provider}
				>
					{provider}{model ? ` · ${model}` : ''}
				</span>
			{/if}
			{#if copyText}
				<button
					onclick={copy}
					class="inline-flex items-center gap-1 px-1.5 py-1 text-xs text-fg-muted transition hover:bg-surface hover:text-fg"
					aria-label="Copy to clipboard"
				>
					{#if copied}
						<span class="text-ok">✓ copied</span>
					{:else}
						copy
					{/if}
				</button>
				<button
					onclick={download}
					class="inline-flex items-center px-1.5 py-1 text-xs text-fg-muted transition hover:bg-surface hover:text-fg"
					aria-label="Download as file"
					title="Download as file"
				>
					↓ download
				</button>
			{/if}
		</div>
	</div>

	<div class="px-4 py-4" bind:this={container}>
		{@render children()}
	</div>
</div>
