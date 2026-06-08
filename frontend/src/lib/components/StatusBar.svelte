<script lang="ts">
	import { theme } from '$lib/theme.svelte';

	const VERSION = '0.2.0';
</script>

<div class="fixed right-0 bottom-0 left-0 z-40 flex items-center justify-between border-t border-border bg-surface-2 px-4 py-1 text-xs text-fg-faint">
	<span>[standup]</span>
	<span class="flex items-center gap-2">
		<a href="https://codeberg.org/ncoleman/standup-gen" class="text-fg-muted transition hover:text-accent" target="_blank" rel="noopener">codeberg</a>
		<span aria-hidden="true">│</span>
		<span>scheme: <span class="text-fg-muted">{theme.current}</span></span>
		<span aria-hidden="true">│</span>
		<span>v{VERSION}</span>
	</span>
</div>
