// SPA mode: FastAPI is the backend, so there's no SvelteKit server.
// ssr=false renders everything client-side; prerender=true emits the static shell at build.
export const ssr = false;
export const prerender = true;
