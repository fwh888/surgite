import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const fetchCurrentUser = vi.fn();
const redirect = vi.fn((status: number, location: string) => {
	const err = new Error(`Redirect to ${location}`) as Error & { __redirect?: unknown };
	err.__redirect = { status, location };
	throw err;
});

vi.mock('$lib/api', () => ({ fetchCurrentUser }));
vi.mock('@sveltejs/kit', () => ({ redirect }));

const { load } = await import('./+layout');

const urlFor = (pathname: string) => ({ pathname }) as URL;

describe('root +layout.ts — client-side auth guard (issue #79)', () => {
	beforeEach(() => {
		fetchCurrentUser.mockReset();
		redirect.mockClear();
	});

	afterEach(() => {
		vi.clearAllMocks();
	});

	it('does not call fetchCurrentUser on a public path', async () => {
		await load({ url: urlFor('/login') });
		await load({ url: urlFor('/signup') });
		await load({ url: urlFor('/password-reset') });
		await load({ url: urlFor('/s/abc123') });
		await load({ url: urlFor('/health') });
		expect(fetchCurrentUser).not.toHaveBeenCalled();
	});

	it('returns the user on success without redirecting', async () => {
		const u = { id: 'u1', email: 'a@b.c', display_name: 'A', is_admin: false };
		fetchCurrentUser.mockResolvedValueOnce(u);
		const data = await load({ url: urlFor('/') });
		expect(data.user).toEqual(u);
		expect(redirect).not.toHaveBeenCalled();
	});

	it('redirects to /login on a 401 for a non-public path', async () => {
		const err = new Error('Not authenticated') as Error & { status?: number };
		err.status = 401;
		fetchCurrentUser.mockRejectedValueOnce(err);
		await expect(load({ url: urlFor('/') })).rejects.toThrow(/Redirect to \/login/);
		expect(redirect).toHaveBeenCalledWith(302, '/login?retry=1');
	});

	it('does NOT redirect on non-401 errors (e.g. 5xx, network blip)', async () => {
		const err = new Error('Server Error') as Error & { status?: number };
		err.status = 503;
		fetchCurrentUser.mockRejectedValueOnce(err);
		await expect(load({ url: urlFor('/') })).rejects.toBe(err);
		expect(redirect).not.toHaveBeenCalled();
	});

	it('treats legacy errors without a status field as non-redirects', async () => {
		fetchCurrentUser.mockRejectedValueOnce(new TypeError('network down'));
		await expect(load({ url: urlFor('/') })).rejects.toThrow(/network down/);
		expect(redirect).not.toHaveBeenCalled();
	});

	it('protects deep paths like /admin/users', async () => {
		const err = new Error('Not authenticated') as Error & { status?: number };
		err.status = 401;
		fetchCurrentUser.mockRejectedValueOnce(err);
		await expect(load({ url: urlFor('/admin/users') })).rejects.toThrow(/Redirect/);
	});
});
