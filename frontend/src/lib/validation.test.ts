import { describe, expect, it } from 'vitest';
import { validateNewPassword } from './validation';

describe('validateNewPassword', () => {
	it('returns null for a valid matching pair', () => {
		expect(validateNewPassword('correct-horse', 'correct-horse')).toBeNull();
	});

	it('rejects a too-short password', () => {
		expect(validateNewPassword('short', 'short')).toMatch(/at least 8/);
	});

	it('rejects mismatched passwords', () => {
		expect(validateNewPassword('aaaaaaaa', 'bbbbbbbb')).toBe('Passwords do not match.');
	});

	it('checks length before mismatch (length is the more common typo)', () => {
		expect(validateNewPassword('a', 'aaaaaaaa')).toMatch(/at least 8/);
	});
});
