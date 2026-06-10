<script lang="ts">
	import { onMount } from 'svelte';
	import {
		fetchPromptSettings,
		updatePromptSettings,
		type PromptSettings as Settings
	} from '$lib/api';
	import { toasts } from '$lib/toast.svelte';
	import Skeleton from './Skeleton.svelte';

	let expanded = $state(false);
	let saving = $state(false);
	let loading = $state(false);

	let user_name = $state('');
	let user_role = $state('');
	let tone = $state('neutral');
	let group_count = $state('2-5');
	let output_format = $state('markdown');
	let custom_instructions = $state('');

	const TONES = [
		{ value: 'neutral', label: 'Neutral' },
		{ value: 'first-person', label: 'First person' },
		{ value: 'formal', label: 'Formal' },
		{ value: 'casual', label: 'Casual' }
	];

	const FORMATS = [
		{ value: 'markdown', label: 'Markdown' },
		{ value: 'plain', label: 'Plain text' }
	];

	const GROUP_COUNTS = ['1-3', '2-5', '3-7', '4-8'];

	onMount(async () => {
		try {
			const s = await fetchPromptSettings();
			applySettings(s);
		} catch {
			// endpoint unavailable
		}
	});

	function applySettings(s: Settings) {
		user_name = s.user_name;
		user_role = s.user_role;
		tone = s.tone;
		group_count = s.group_count;
		output_format = s.output_format;
		custom_instructions = s.custom_instructions;
	}

	async function toggle() {
		expanded = !expanded;
		if (expanded) {
			loading = true;
			try {
				const s = await fetchPromptSettings();
				applySettings(s);
			} catch {
				toasts.error('Failed to load prompt settings');
			} finally {
				loading = false;
			}
		}
	}

	async function save() {
		saving = true;
		try {
			const s = await updatePromptSettings({
				user_name,
				user_role,
				tone,
				group_count,
				output_format,
				custom_instructions
			});
			applySettings(s);
			toasts.success('Prompt settings saved');
		} catch {
			toasts.error('Failed to save prompt settings');
		} finally {
			saving = false;
		}
	}

	const inputCls = 'border border-border bg-bg px-2 py-1.5 text-sm text-fg w-full';
	const labelCls = 'text-xs text-fg-muted';
</script>

<section class="mt-6">
	<button
		onclick={toggle}
		class="flex w-full items-center gap-1 text-sm text-fg-muted hover:text-fg transition"
	>
		<span class="text-accent">~/config</span>
		<span aria-hidden="true">❯</span>
		<span class="ml-auto text-xs">{expanded ? '▼' : '▶'}</span>
	</button>

	{#if expanded}
		{#if loading}
			<div class="mt-3">
				<Skeleton rows={4} />
			</div>
		{:else}
			<div class="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
				<div>
					<label class={labelCls} for="ps-name">Name</label>
					<input
						id="ps-name"
						type="text"
						bind:value={user_name}
						placeholder="e.g. Alice"
						class={inputCls}
					/>
				</div>

				<div>
					<label class={labelCls} for="ps-role">Role</label>
					<input
						id="ps-role"
						type="text"
						bind:value={user_role}
						placeholder="e.g. backend engineer"
						class={inputCls}
					/>
				</div>

				<div>
					<label class={labelCls} for="ps-tone">Tone</label>
					<select id="ps-tone" bind:value={tone} class={inputCls}>
						{#each TONES as t (t.value)}
							<option value={t.value}>{t.label}</option>
						{/each}
					</select>
				</div>

				<div>
					<label class={labelCls} for="ps-groups">Groups</label>
					<select id="ps-groups" bind:value={group_count} class={inputCls}>
						{#each GROUP_COUNTS as g}
							<option value={g}>{g}</option>
						{/each}
					</select>
				</div>

				<div>
					<label class={labelCls} for="ps-format">Output format</label>
					<select id="ps-format" bind:value={output_format} class={inputCls}>
						{#each FORMATS as f (f.value)}
							<option value={f.value}>{f.label}</option>
						{/each}
					</select>
				</div>

				<div class="sm:col-span-2">
					<label class={labelCls} for="ps-custom">Custom instructions</label>
					<textarea
						id="ps-custom"
						bind:value={custom_instructions}
						placeholder="Additional instructions appended to the prompt…"
						rows="3"
						class="{inputCls} resize-y"
					></textarea>
				</div>
			</div>

			<button
				onclick={save}
				disabled={saving}
				class="mt-4 border border-border bg-accent px-4 py-1.5 text-sm font-medium text-accent-contrast transition hover:bg-accent-hover disabled:opacity-50"
			>
				{saving ? 'Saving…' : '❯ save'}
			</button>
		{/if}
	{/if}
</section>
