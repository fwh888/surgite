// Lightweight toast notifications. A single store holds the active toasts;
// <Toaster /> (mounted once in the layout) renders them. Use `toasts.success(...)`
// / `toasts.error(...)` from anywhere to give the user feedback on an action.

type ToastKind = 'success' | 'error';

export interface Toast {
	id: number;
	kind: ToastKind;
	message: string;
}

class ToastStore {
	items = $state<Toast[]>([]);
	#nextId = 0;

	#push(kind: ToastKind, message: string, ttl: number): number {
		const id = this.#nextId++;
		this.items.push({ id, kind, message });
		if (ttl > 0) setTimeout(() => this.dismiss(id), ttl);
		return id;
	}

	success(message: string, ttl = 3500): number {
		return this.#push('success', message, ttl);
	}

	error(message: string, ttl = 6000): number {
		return this.#push('error', message, ttl);
	}

	dismiss(id: number): void {
		this.items = this.items.filter((t) => t.id !== id);
	}
}

export const toasts = new ToastStore();
