<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { fetchCurrentUser, logout, type CurrentUser } from '$lib/api';

	// null = still loading or auth-disabled (off/single_user). We don't
	// render anything in that case so the header stays clean in the
	// common case where the deploy is single-user.
	let user = $state<CurrentUser | null>(null);

	onMount(async () => {
		try {
			user = await fetchCurrentUser();
		} catch {
			// 401 in multi_user without a session -> nothing to show.
			user = null;
		}
	});

	async function handleLogout() {
		try {
			await logout();
		} catch {
			// Cookie is already invalid; just bounce to the login page.
		}
		goto('/login');
	}
</script>

{#if user}
	<span class="text-xs text-fg-muted">
		<span class="text-fg-faint">user:</span>
		{user.display_name || user.email}
	</span>
	<button
		onclick={handleLogout}
		class="inline-flex items-center gap-1 border border-border bg-surface px-2 py-1.5 text-xs text-fg-muted transition hover:text-fg"
		aria-label="Log out"
	>
		logout
	</button>
{/if}
