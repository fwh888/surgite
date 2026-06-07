// Reactive light/dark theme, persisted to localStorage and reflected as `.dark` on <html>.
// The initial class is set by the inline script in app.html (flash-free); this store reads
// the same source so the UI starts in agreement with what was already painted.
import { browser } from '$app/environment';

type Theme = 'light' | 'dark';

function initial(): Theme {
	if (!browser) return 'light';
	const stored = localStorage.getItem('theme');
	if (stored === 'light' || stored === 'dark') return stored;
	return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

class ThemeState {
	current = $state<Theme>(initial());

	get isDark() {
		return this.current === 'dark';
	}

	toggle() {
		this.current = this.current === 'dark' ? 'light' : 'dark';
		if (!browser) return;
		document.documentElement.classList.toggle('dark', this.current === 'dark');
		localStorage.setItem('theme', this.current);
	}
}

export const theme = new ThemeState();
