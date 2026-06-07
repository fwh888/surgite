import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toasts } from './toast.svelte';

beforeEach(() => {
	for (const t of [...toasts.items]) toasts.dismiss(t.id);
});

describe('toasts', () => {
	it('adds a success toast', () => {
		toasts.success('done', 0);
		expect(toasts.items.at(-1)).toMatchObject({ kind: 'success', message: 'done' });
	});

	it('dismiss removes a toast by id', () => {
		const id = toasts.error('boom', 0);
		toasts.dismiss(id);
		expect(toasts.items.find((t) => t.id === id)).toBeUndefined();
	});

	it('auto-dismisses after the ttl', () => {
		vi.useFakeTimers();
		const id = toasts.success('temp', 1000);
		expect(toasts.items.find((t) => t.id === id)).toBeDefined();
		vi.advanceTimersByTime(1000);
		expect(toasts.items.find((t) => t.id === id)).toBeUndefined();
		vi.useRealTimers();
	});
});
