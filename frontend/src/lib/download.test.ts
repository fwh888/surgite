import { describe, expect, it } from 'vitest';
import { summaryFilename } from './download';

describe('summaryFilename', () => {
	it('uses .md for AI summaries and .txt for logs', () => {
		expect(summaryFilename('myrepo', 'summary')).toBe('myrepo-surgite.md');
		expect(summaryFilename('myrepo', 'log')).toBe('myrepo-surgite.txt');
	});

	it('sanitizes unusual repo names', () => {
		expect(summaryFilename('My Repo!', 'summary')).toBe('my-repo-surgite.md');
		expect(summaryFilename('a/b.c', 'log')).toBe('a-b-c-surgite.txt');
	});

	it('falls back when the name has no usable characters', () => {
		expect(summaryFilename('!!!', 'summary')).toBe('surgite.md');
	});
});
