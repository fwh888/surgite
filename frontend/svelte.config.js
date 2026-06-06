import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	compilerOptions: {
		// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
		runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true)
	},
	kit: {
		// SPA: FastAPI is the backend, so we ship a static bundle it serves.
		// `fallback` is the entry point for any client-routed URL. See
		// docs/v2-svelte-plan.md and https://svelte.dev/docs/kit/single-page-apps
		adapter: adapter({ fallback: '200.html' })
	}
};

export default config;
