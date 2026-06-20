// SPA mode: FastAPI is the backend, so there's no SvelteKit server.
// ssr=false renders everything client-side; prerender=true emits the static shell at build.
export const ssr = false;
export const prerender = true;

// ponytail: client-side auth gate. The backend is the real boundary; this is
// a UX nicety so unauthenticated users land on /login instead of a 401/empty
// page. Runs on every navigation via the layout load.
import { redirect } from '@sveltejs/kit';
import { fetchCurrentUser } from '$lib/api';
import type { CurrentUser } from '$lib/api';

const PUBLIC = ['/login', '/signup', '/password-reset', '/health', '/s/'];

function isPublic(pathname: string): boolean {
	return PUBLIC.some((p) => pathname === p || pathname.startsWith(p));
}

export async function load({
	url
}: {
	url: URL;
}): Promise<{ user: CurrentUser | null }> {
	if (isPublic(url.pathname)) return { user: null };
	try {
		const user = await fetchCurrentUser();
		return { user };
	} catch (e) {
		// ponytail: only 401 is a redirect signal. 5xx / network blips should
		// render the page and let the user see a real error, not bounce them
		// to /login for a transient outage.
		if ((e as { status?: number }).status === 401) {
			throw redirect(302, '/login?retry=1');
		}
		throw e;
	}
}
