import { describe, expect, it } from 'vitest';
import { renderMarkdown } from './markdown';

describe('renderMarkdown', () => {
	it('renders bullet lists', () => {
		const html = renderMarkdown('- one\n- two');
		expect(html).toContain('<ul');
		expect(html).toContain('<li>one</li>');
		expect(html).toContain('<li>two</li>');
	});

	it('renders headings and inline formatting', () => {
		expect(renderMarkdown('# Title')).toContain('<h4');
		expect(renderMarkdown('**bold**')).toContain('<strong');
		expect(renderMarkdown('`code`')).toContain('<code');
	});

	it('escapes HTML so {@html} output stays XSS-safe', () => {
		const html = renderMarkdown('<script>alert(1)</script>');
		expect(html).not.toContain('<script>');
		expect(html).toContain('&lt;script&gt;');
	});
});
