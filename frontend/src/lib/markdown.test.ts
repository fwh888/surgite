import { describe, expect, it } from 'vitest';
import { renderMarkdown } from './markdown';

describe('renderMarkdown', () => {
	it('renders bullet lists', () => {
		const html = renderMarkdown('- one\n- two');
		expect(html).toContain('<ul');
		expect(html).toContain('<li>one</li>');
		expect(html).toContain('<li>two</li>');
	});

	it('renders ordered lists', () => {
		const html = renderMarkdown('1. first\n2. second\n3. third');
		expect(html).toContain('<ol');
		expect(html).toContain('<li>first</li>');
		expect(html).toContain('<li>second</li>');
		expect(html).toContain('<li>third</li>');
	});

	it('closes and reopens list when type changes', () => {
		const html = renderMarkdown('- bullet\n1. ordered');
		expect(html).toContain('</ul>');
		expect(html).toContain('<ol');
	});

	it('renders headings and inline formatting', () => {
		expect(renderMarkdown('# Title')).toContain('<h4');
		expect(renderMarkdown('**bold**')).toContain('<strong');
		expect(renderMarkdown('`code`')).toContain('<code');
	});

	it('renders links with noopener noreferrer', () => {
		const html = renderMarkdown('See [docs](https://example.com) for details');
		expect(html).toContain('<a href="https://example.com"');
		expect(html).toContain('rel="noopener noreferrer"');
		expect(html).toContain('target="_blank"');
		expect(html).toContain('>docs</a>');
	});

	it('rejects non-http links', () => {
		const html = renderMarkdown('[click](javascript:alert(1))');
		expect(html).not.toContain('href="javascript:');
		expect(html).toContain('[click](javascript:alert(1))');
	});

	it('renders fenced code blocks', () => {
		const html = renderMarkdown('```\nconst x = 1;\nconst y = 2;\n```');
		expect(html).toContain('<pre');
		expect(html).toContain('<code>');
		expect(html).toContain('const x = 1;');
		expect(html).toContain('const y = 2;');
	});

	it('does not apply inline formatting inside code blocks', () => {
		const html = renderMarkdown('```\n**not bold** and `not code`\n```');
		expect(html).not.toContain('<strong');
		expect(html).toContain('**not bold**');
	});

	it('escapes HTML so {@html} output stays XSS-safe', () => {
		const html = renderMarkdown('<script>alert(1)</script>');
		expect(html).not.toContain('<script>');
		expect(html).toContain('&lt;script&gt;');
	});

	it('escapes HTML inside code blocks', () => {
		const html = renderMarkdown('```\n<img src=x onerror=alert(1)>\n```');
		expect(html).not.toContain('<img');
		expect(html).toContain('&lt;img');
	});
});
