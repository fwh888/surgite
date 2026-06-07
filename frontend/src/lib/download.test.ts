import { describe, expect, it } from 'vitest';
import { summaryFilename } from './download';

describe('summaryFilename', () => {
	it('uses .md for AI summaries and .txt for logs', () => {
		expect(summaryFilename('myrepo', 'summary')).toBe('myrepo-standup.md');
		expect(summaryFilename('myrepo', 'log')).toBe('myrepo-standup.txt');
	});

	it('sanitizes unusual repo names', () => {
		expect(summaryFilename('My Repo!', 'summary')).toBe('my-repo-standup.md');
		expect(summaryFilename('a/b.c', 'log')).toBe('a-b-c-standup.txt');
	});

	it('falls back when the name has no usable characters', () => {
		expect(summaryFilename('!!!', 'summary')).toBe('standup.md');
	});
});
