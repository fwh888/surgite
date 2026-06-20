// Thin typed client for the standup-gen API.
//
// In dev, the Vite server (:5173) calls FastAPI (:8000) cross-origin, so we point at the
// backend explicitly. In a production build the SPA is served same-origin by FastAPI, so the
// base is empty and requests are relative. Override either with VITE_API_BASE.
const BASE = import.meta.env.VITE_API_BASE ?? (import.meta.env.DEV ? 'http://localhost:8000' : '');

export interface Repo {
	id: number;
	name: string;
	clone_url: string;
	added_at: string | null;
	last_ingested_at: string | null;
}

export interface Commit {
	hash: string;
	short_hash: string;
	date: string;
	author: string;
	message: string;
	repo: string;
	ingested_at: string | null;
}

export interface Summary {
	period: { since: string | null; until: string | null };
	total_commits: number;
	by_repo: Record<string, number>;
	by_day: Record<string, number>;
	commits: Commit[];
	log_by_repo: Record<string, string> | null;
	ai_summary: string | null;
	ai_provider: string | null;
	ai_model: string | null;
	ai_summaries: Record<string, { summary: string; provider: string; model: string }> | null;
}

const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);
const CSRF_HEADER = 'X-Requested-With';
const CSRF_VALUE = 'standup-web';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	// The CSRF middleware in backend/api.py requires this header on every
	// non-safe method in multi_user mode. We send it unconditionally so
	// callers don't have to think about it; the server ignores it on safe
	// methods and in off/single_user mode.
	const method = (init?.method ?? 'GET').toUpperCase();
	const headers: Record<string, string> = {
		'Content-Type': 'application/json',
		...(init?.headers as Record<string, string> | undefined)
	};
	if (UNSAFE_METHODS.has(method)) headers[CSRF_HEADER] = CSRF_VALUE;
	const res = await fetch(`${BASE}${path}`, { ...init, headers });
	if (!res.ok) {
		// FastAPI errors carry a `detail` field; fall back to the status text.
		let detail: unknown = res.statusText;
		try {
			detail = (await res.json()).detail ?? res.statusText;
		} catch {
			/* non-JSON body */
		}
		const message = typeof detail === 'string' ? detail : JSON.stringify(detail);
		// ponytail: a single extra field on the Error is cheaper than a
		// custom error class. Callers that need it (e.g. the login page's
		// lockout countdown) can read it; everyone else ignores it.
		const err = new Error(message) as Error & { lockoutSeconds?: number };
		if (res.status === 423) {
			const retryAfter = Number(res.headers.get('Retry-After'));
			if (Number.isFinite(retryAfter) && retryAfter > 0) err.lockoutSeconds = retryAfter;
		}
		throw err;
	}
	// 204 No Content (e.g. DELETE) has no body to parse.
	return res.status === 204 ? (undefined as T) : res.json();
}

// --- auth (multi_user) -----------------------------------------------------

export interface CurrentUser {
	id: string;
	email: string;
	display_name: string;
	is_admin: boolean;
}

export const fetchCurrentUser = () => request<CurrentUser>('/auth/me');

export const login = (email: string, password: string) =>
	request<CurrentUser>('/auth/login', {
		method: 'POST',
		body: JSON.stringify({ email, password })
	});

export interface SignupRequest {
	token: string;
	password: string;
	email?: string;
	display_name?: string;
}

export const signup = (req: SignupRequest) =>
	request<CurrentUser>('/auth/redeem-invite', {
		method: 'POST',
		body: JSON.stringify(req)
	});

export const logout = () => request<void>('/auth/logout', { method: 'POST' });

export const listRepos = () => request<{ repos: Repo[] }>('/repos').then((r) => r.repos);

export const addRepo = (url: string) =>
	request<Repo>('/repos', { method: 'POST', body: JSON.stringify({ url }) });

export const deleteRepo = (id: number) => request<void>(`/repos/${id}`, { method: 'DELETE' });

export interface SummaryParams {
	repo?: string;
	since?: string;
	until?: string;
	author?: string;
	ai?: boolean;
	provider?: string;
}

export interface ProviderInfo {
	name: string;
	model: string;
	available: boolean;
	default: boolean;
}

export interface ProvidersResponse {
	default: string;
	providers: ProviderInfo[];
}

export function generateSummary(params: SummaryParams = {}, signal?: AbortSignal) {
	const q = new URLSearchParams();
	if (params.repo) q.set('repo', params.repo);
	if (params.since) q.set('since', params.since);
	if (params.until) q.set('until', params.until);
	if (params.author) q.set('author', params.author);
	if (params.ai) q.set('ai', 'true');
	if (params.provider) q.set('provider', params.provider);
	const qs = q.toString();
	return request<Summary>(`/summary${qs ? `?${qs}` : ''}`, { signal });
}

export const fetchProviders = () =>
	request<ProvidersResponse>('/providers');

export interface PromptSettings {
	// null = the global default row; a number = a repo-specific override.
	repo_id: number | null;
	user_name: string;
	user_role: string;
	tone: string;
	group_count: string;
	output_format: string;
	custom_instructions: string;
	updated_at: string | null;
}

export type PromptSettingsUpdate = Partial<Omit<PromptSettings, 'updated_at' | 'repo_id'>>;

const repoQuery = (repoId?: number | null) =>
	repoId == null ? '' : `?repo_id=${repoId}`;

export const fetchPromptSettings = (repoId?: number | null) =>
	request<PromptSettings>(`/settings/prompt${repoQuery(repoId)}`);

export const updatePromptSettings = (update: PromptSettingsUpdate, repoId?: number | null) =>
	request<PromptSettings>(`/settings/prompt${repoQuery(repoId)}`, {
		method: 'PUT',
		body: JSON.stringify(update)
	});

// --- shareable summary links ---

export interface ShareResponse {
	slug: string;
	expires_at: string;
}

export interface SharedSummary {
	slug: string;
	params: SummaryParams;
	created_at: string | null;
	expires_at: string | null;
}

export const createShare = (params: SummaryParams) =>
	request<ShareResponse>('/summaries', { method: 'POST', body: JSON.stringify(params) });

export const fetchShare = (slug: string) =>
	request<SharedSummary>(`/summaries/${encodeURIComponent(slug)}`);

// --- streaming AI summaries (SSE) ---

export interface StreamMeta {
	period: { since: string | null; until: string | null };
	total_commits: number;
	by_repo: Record<string, number>;
	by_day: Record<string, number>;
	repos: string[];
	provider: string;
	model: string;
}

export interface StreamHandlers {
	onMeta: (meta: StreamMeta) => void;
	onDelta: (repo: string, text: string) => void;
	onRepoDone: (repo: string, provider: string, model: string) => void;
	onRepoError: (repo: string, detail: string) => void;
}

function summaryQuery(params: SummaryParams): string {
	const q = new URLSearchParams();
	if (params.repo) q.set('repo', params.repo);
	if (params.since) q.set('since', params.since);
	if (params.until) q.set('until', params.until);
	if (params.author) q.set('author', params.author);
	if (params.provider) q.set('provider', params.provider);
	return q.toString();
}

/**
 * Stream an AI summary over SSE, invoking handlers as events arrive. Resolves
 * when the stream completes; rejects on a transport error or an HTTP error
 * status (so the caller can surface it like any other failure). Honour the
 * passed AbortSignal to cancel mid-stream.
 */
export async function streamSummary(
	params: SummaryParams,
	handlers: StreamHandlers,
	signal?: AbortSignal
): Promise<void> {
	const qs = summaryQuery(params);
	const res = await fetch(`${BASE}/summary/stream${qs ? `?${qs}` : ''}`, {
		headers: { Accept: 'text/event-stream' },
		signal
	});
	if (!res.ok || !res.body) {
		let detail: unknown = res.statusText;
		try {
			detail = (await res.json()).detail ?? res.statusText;
		} catch {
			/* non-JSON body */
		}
		throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
	}

	const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
	let buffer = '';
	for (;;) {
		const { value, done } = await reader.read();
		if (done) break;
		buffer += value;
		// SSE frames are separated by a blank line.
		let sep: number;
		while ((sep = buffer.indexOf('\n\n')) !== -1) {
			const frame = buffer.slice(0, sep);
			buffer = buffer.slice(sep + 2);
			dispatchFrame(frame, handlers);
		}
	}
}

function dispatchFrame(frame: string, handlers: StreamHandlers): void {
	let event = 'message';
	let data = '';
	for (const line of frame.split('\n')) {
		if (line.startsWith('event:')) event = line.slice(6).trim();
		else if (line.startsWith('data:')) data += line.slice(5).trim();
	}
	if (!data) return;
	const payload = JSON.parse(data);
	if (event === 'meta') handlers.onMeta(payload);
	else if (event === 'delta') handlers.onDelta(payload.repo, payload.text);
	else if (event === 'repo_done') handlers.onRepoDone(payload.repo, payload.provider, payload.model);
	else if (event === 'repo_error') handlers.onRepoError(payload.repo, payload.detail);
}
