<script lang="ts">
	import { onMount } from 'svelte';
	import { listRepos, type Repo } from '$lib/api';
	import RepoList from '$lib/components/RepoList.svelte';
	import AddRepoForm from '$lib/components/AddRepoForm.svelte';
	import SummaryPanel from '$lib/components/SummaryPanel.svelte';

	let repos = $state<Repo[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	async function loadRepos() {
		loading = true;
		error = null;
		try {
			repos = await listRepos();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load repos';
		} finally {
			loading = false;
		}
	}

	onMount(loadRepos);
</script>

<main class="mx-auto max-w-2xl px-6 py-12">
	<h1 class="text-2xl font-semibold tracking-tight text-slate-900">standup</h1>
	<p class="mt-1 text-sm text-slate-500">Generate standup summaries from your git history.</p>

	<section class="mt-10">
		<h2 class="text-sm font-medium tracking-wide text-slate-500 uppercase">Repos</h2>
		<AddRepoForm onAdded={loadRepos} />
		<RepoList {repos} {loading} {error} onChanged={loadRepos} />
	</section>

	<SummaryPanel {repos} />
</main>
