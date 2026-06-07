// Minimal, dependency-free markdown → HTML for AI summary text.
//
// The output is consumed via {@html ...}, so it must be XSS-safe: we escape all HTML up front
// and only ever emit our own tags afterwards. Supports headings (#/##/###), bullet lists,
// bold, italic, and inline code — enough to render a typical model-written standup nicely.

function escapeHtml(s: string): string {
	return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function inline(s: string): string {
	return s
		.replace(/`([^`]+)`/g, '<code class="bg-surface-2 px-1 py-0.5 text-[0.85em]">$1</code>')
		.replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold text-fg">$1</strong>')
		.replace(/(^|[^*])\*([^*\s][^*]*?)\*/g, '$1<em>$2</em>');
}

export function renderMarkdown(src: string): string {
	const lines = escapeHtml(src.trim()).split('\n');
	const out: string[] = [];
	let inList = false;

	const closeList = () => {
		if (inList) {
			out.push('</ul>');
			inList = false;
		}
	};

	for (const raw of lines) {
		const line = raw.trimEnd();
		const bullet = line.match(/^\s*[-*]\s+(.*)$/);
		const heading = line.match(/^(#{1,3})\s+(.*)$/);

		if (bullet) {
			if (!inList) {
				out.push('<ul class="list-disc space-y-1 pl-5 marker:text-fg-faint">');
				inList = true;
			}
			out.push(`<li>${inline(bullet[1])}</li>`);
		} else if (heading) {
			closeList();
			const size = heading[1].length === 1 ? 'text-base' : 'text-sm';
			out.push(`<h4 class="${size} font-semibold text-fg">${inline(heading[2])}</h4>`);
		} else if (line.trim() === '') {
			closeList();
		} else {
			closeList();
			out.push(`<p>${inline(line)}</p>`);
		}
	}
	closeList();
	return out.join('\n');
}
