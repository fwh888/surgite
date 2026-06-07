<script lang="ts">
	let { onclose }: { onclose: () => void } = $props();

	function handleKey(e: KeyboardEvent) {
		if (e.key === 'Escape' || e.key === 'q') onclose();
	}

	function handleBgClick(e: MouseEvent) {
		if (e.target === e.currentTarget) onclose();
	}
</script>

<svelte:window onkeydown={handleKey} />

<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_noninteractive_element_interactions -->
<div
	class="fixed inset-0 z-50 flex items-center justify-center bg-bg/80 p-4"
	onclick={handleBgClick}
	role="dialog"
	aria-modal="true"
	aria-label="Help"
	tabindex="-1"
>
	<div class="w-full max-w-lg border border-border bg-surface p-6 text-sm text-fg">
		<div class="mb-4 flex items-center justify-between">
			<h2 class="text-base font-semibold text-fg">:help</h2>
			<button onclick={onclose} class="text-fg-muted hover:text-fg">✕</button>
		</div>
		<div class="space-y-3 text-fg-muted">
			<p><span class="text-fg">standup</span> generates standup summaries from your git commit history.</p>
			<div>
				<p class="text-fg">Commands:</p>
				<p>  <span class="text-accent">❯ add-repo</span>        — register a git repository</p>
				<p>  <span class="text-accent">❯ ingest --all</span>    — fetch latest commits from all repos</p>
				<p>  <span class="text-accent">❯ generate</span>        — produce a summary for the selected range</p>
			</div>
			<div>
				<p class="text-fg">Keyboard:</p>
				<p>  <span class="text-accent">F1</span>               — toggle this help</p>
				<p>  <span class="text-accent">↑↑↓↓←→←→BA</span>    — ???</p>
			</div>
			<p class="text-fg-faint">Press <span class="text-fg-muted">Esc</span> or <span class="text-fg-muted">q</span> to close.</p>
		</div>
	</div>
</div>
