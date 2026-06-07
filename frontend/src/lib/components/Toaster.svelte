<script lang="ts">
	import { fly } from 'svelte/transition';
	import { toasts } from '$lib/toast.svelte';
</script>

<div
	class="pointer-events-none fixed right-4 bottom-4 z-50 flex w-full max-w-sm flex-col gap-2"
	aria-live="polite"
>
	{#each toasts.items as t (t.id)}
		<div
			role="status"
			transition:fly={{ y: 8, duration: 200 }}
			class="pointer-events-auto flex items-start gap-2 rounded-lg border px-3 py-2 text-sm shadow-lg {t.kind ===
			'success'
				? 'border-green-200 bg-green-50 text-green-800 dark:border-green-500/30 dark:bg-green-500/10 dark:text-green-300'
				: 'border-red-200 bg-red-50 text-red-800 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300'}"
		>
			<span class="flex-1">{t.message}</span>
			<button
				onclick={() => toasts.dismiss(t.id)}
				aria-label="Dismiss notification"
				class="shrink-0 opacity-60 transition hover:opacity-100"
			>
				✕
			</button>
		</div>
	{/each}
</div>
