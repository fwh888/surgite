<script lang="ts">
	import { theme, THEMES } from '$lib/theme.svelte';

	let open = $state(false);
	let root = $state<HTMLElement>();

	const current = $derived(THEMES.find((t) => t.id === theme.current) ?? THEMES[0]);

	function choose(id: string) {
		theme.set(id);
		open = false;
	}

	$effect(() => {
		if (!open) return;
		const onClick = (e: MouseEvent) => {
			if (root && !root.contains(e.target as Node)) open = false;
		};
		const onKey = (e: KeyboardEvent) => {
			if (e.key === 'Escape') open = false;
		};
		document.addEventListener('click', onClick);
		document.addEventListener('keydown', onKey);
		return () => {
			document.removeEventListener('click', onClick);
			document.removeEventListener('keydown', onKey);
		};
	});
</script>

<div class="relative" bind:this={root}>
	<button
		onclick={() => (open = !open)}
		aria-haspopup="listbox"
		aria-expanded={open}
		class="inline-flex items-center gap-2 border border-border bg-surface px-2.5 py-1.5 text-xs text-fg-muted transition hover:text-fg"
	>
		<span
			class="inline-block h-3 w-3 shrink-0 border border-border"
			style="background:{current.bg}"
			aria-hidden="true"
		>
			<span
				class="block h-full w-full"
				style="background:{current.accent}; clip-path: polygon(100% 0, 100% 100%, 0 100%)"
			></span>
		</span>
		<span class="hidden sm:inline">colorscheme:</span>
		<span class="text-fg">{theme.current}</span>
		<span aria-hidden="true">▾</span>
	</button>

	{#if open}
		<ul
			role="listbox"
			aria-label="Colorscheme"
			class="absolute right-0 z-30 mt-1 w-52 border border-border bg-surface py-1 shadow-lg"
		>
			{#each THEMES as t (t.id)}
				<li>
					<button
						role="option"
						aria-selected={theme.current === t.id}
						onclick={() => choose(t.id)}
						class="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-xs text-fg-muted transition hover:bg-surface-2 hover:text-fg"
					>
						<span
							class="inline-block h-3 w-3 shrink-0 border border-border"
							style="background:{t.bg}"
							aria-hidden="true"
						>
							<span
								class="block h-full w-full"
								style="background:{t.accent}; clip-path: polygon(100% 0, 100% 100%, 0 100%)"
							></span>
						</span>
						<span class="flex-1 {theme.current === t.id ? 'text-fg' : ''}">{t.label}</span>
						{#if theme.current === t.id}
							<span class="text-accent" aria-hidden="true">›</span>
						{/if}
					</button>
				</li>
			{/each}
		</ul>
	{/if}
</div>
