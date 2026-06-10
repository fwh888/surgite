// Minimal, dependency-free markdown → HTML for AI summary text.
//
// The output is consumed via {@html ...}, so it must be XSS-safe: we escape all HTML up front
// and only ever emit our own tags afterwards. Supports headings (#/##/###), bullet/ordered lists,
// fenced code blocks, links, bold, italic, and inline code.

function escapeHtml(s: string): string {
	return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function inline(s: string): string {
	return s
		.replace(/`([^`]+)`/g, '<code class="bg-surface-2 px-1 py-0.5 text-[0.85em]">$1</code>')
		.replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold text-fg">$1</strong>')
		.replace(/(^|[^*])\*([^*\s][^*]*?)\*/g, '$1<em>$2</em>')
		.replace(
			/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
			'<a href="$2" rel="noopener noreferrer" target="_blank" class="text-accent underline hover:text-accent-hover">$1</a>'
		);
}

type ListType = 'ul' | 'ol' | null;

export function renderMarkdown(src: string): string {
	const lines = escapeHtml(src.trim()).split('\n');
	const out: string[] = [];
	let listType: ListType = null;
	let inCode = false;
	let codeLines: string[] = [];

	const closeList = () => {
		if (listType) {
			out.push(`</${listType}>`);
			listType = null;
		}
	};

	for (const raw of lines) {
		const line = raw.trimEnd();

		if (line.trim() === '```') {
			if (inCode) {
				out.push(`<pre class="overflow-x-auto bg-surface-1 p-3 text-xs"><code>${codeLines.join('\n')}</code></pre>`);
				codeLines = [];
				inCode = false;
			} else {
				closeList();
				inCode = true;
			}
			continue;
		}

		if (inCode) {
			codeLines.push(line);
			continue;
		}

		const bullet = line.match(/^\s*[-*]\s+(.*)$/);
		const ordered = line.match(/^\s*\d+[.)]\s+(.*)$/);
		const heading = line.match(/^(#{1,3})\s+(.*)$/);

		if (bullet) {
			if (listType !== 'ul') {
				closeList();
				out.push('<ul class="list-disc space-y-1 pl-5 marker:text-fg-faint">');
				listType = 'ul';
			}
			out.push(`<li>${inline(bullet[1])}</li>`);
		} else if (ordered) {
			if (listType !== 'ol') {
				closeList();
				out.push('<ol class="list-decimal space-y-1 pl-5 marker:text-fg-faint">');
				listType = 'ol';
			}
			out.push(`<li>${inline(ordered[1])}</li>`);
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
