// Client-side text download helpers for exporting a standup summary.

/** Build a safe, descriptive filename for a repo's summary export. */
export function summaryFilename(repo: string, kind: 'summary' | 'log'): string {
	const safe = repo.replace(/[^a-z0-9-_]+/gi, '-').replace(/^-+|-+$/g, '').toLowerCase();
	const base = safe ? `${safe}-surgite` : 'surgite';
	const ext = kind === 'summary' ? 'md' : 'txt';
	return `${base}.${ext}`;
}

/** Trigger a browser download of `text` as `filename`. */
export function downloadText(filename: string, text: string): void {
	const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
	const a = document.createElement('a');
	a.href = url;
	a.download = filename;
	a.click();
	URL.revokeObjectURL(url);
}
