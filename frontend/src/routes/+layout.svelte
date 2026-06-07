<script lang="ts">
	import '@fontsource-variable/jetbrains-mono';
	import './layout.css';
	import favicon from '$lib/assets/favicon.svg';
	import Toaster from '$lib/components/Toaster.svelte';
	import StatusBar from '$lib/components/StatusBar.svelte';

	let { children } = $props();
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>
{@render children()}
<Toaster />
<StatusBar />
