// ponytail: tiny pure validators for the /password-reset page. Kept in
// their own module so they're importable from vitest without spinning up
// a Svelte component test framework for a two-rule check.
export function validateNewPassword(password: string, confirm: string): string | null {
	if (password.length < 8) return 'Password must be at least 8 characters.';
	if (password !== confirm) return 'Passwords do not match.';
	return null;
}
