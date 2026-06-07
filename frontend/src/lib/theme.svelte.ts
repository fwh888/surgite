// Reactive colorscheme, persisted to localStorage and reflected as `data-theme`
// on <html>. The pre-paint script in app.html applies the saved scheme flash-free;
// this store reads the same source so the UI starts in agreement.
import { browser } from '$app/environment';

export interface ThemeDef {
	id: string;
	label: string;
	// Swatch colors for the picker preview (kept in sync with layout.css).
	bg: string;
	accent: string;
}

// Order shown in the picker. GitHub Dark is the default.
export const THEMES: ThemeDef[] = [
	{ id: 'github-dark', label: 'GitHub Dark', bg: '#0d1117', accent: '#2f81f7' },
	{ id: 'light', label: 'Light', bg: '#ffffff', accent: '#0969da' },
	{ id: 'nord', label: 'Nord', bg: '#2e3440', accent: '#88c0d0' },
	{ id: 'catppuccin', label: 'Catppuccin Mocha', bg: '#1e1e2e', accent: '#89b4fa' },
	{ id: 'solarized', label: 'Solarized Dark', bg: '#002b36', accent: '#268bd2' },
	{ id: 'terminal', label: 'Terminal', bg: '#0c0c0c', accent: '#ffb000' }
];

const DEFAULT = 'github-dark';
const IDS = new Set(THEMES.map((t) => t.id));

function initial(): string {
	if (!browser) return DEFAULT;
	const stored = localStorage.getItem('theme');
	return stored && IDS.has(stored) ? stored : DEFAULT;
}

class ThemeState {
	current = $state<string>(initial());

	get label(): string {
		return THEMES.find((t) => t.id === this.current)?.label ?? this.current;
	}

	set(id: string) {
		if (!IDS.has(id)) return;
		this.current = id;
		if (!browser) return;
		document.documentElement.setAttribute('data-theme', id);
		localStorage.setItem('theme', id);
	}
}

export const theme = new ThemeState();
