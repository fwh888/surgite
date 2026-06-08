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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	const res = await fetch(`${BASE}${path}`, {
		headers: { 'Content-Type': 'application/json' },
		...init
	});
	if (!res.ok) {
		// FastAPI errors carry a `detail` field; fall back to the status text.
		let detail: unknown = res.statusText;
		try {
			detail = (await res.json()).detail ?? res.statusText;
		} catch {
			/* non-JSON body */
		}
		throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
	}
	// 204 No Content (e.g. DELETE) has no body to parse.
	return res.status === 204 ? (undefined as T) : res.json();
}

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

export function generateSummary(params: SummaryParams = {}) {
	const q = new URLSearchParams();
	if (params.repo) q.set('repo', params.repo);
	if (params.since) q.set('since', params.since);
	if (params.until) q.set('until', params.until);
	if (params.author) q.set('author', params.author);
	if (params.ai) q.set('ai', 'true');
	if (params.provider) q.set('provider', params.provider);
	const qs = q.toString();
	return request<Summary>(`/summary${qs ? `?${qs}` : ''}`);
}

export const fetchProviders = () =>
	request<ProvidersResponse>('/providers');
