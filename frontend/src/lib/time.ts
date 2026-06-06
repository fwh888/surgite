/** Format an ISO timestamp as a short relative string: "just now", "5m ago", "3h ago", "2d ago". */
export function relativeTime(iso: string | null): string {
	if (!iso) return 'never';
	const secs = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
	if (secs < 60) return 'just now';
	const mins = Math.round(secs / 60);
	if (mins < 60) return `${mins}m ago`;
	const hours = Math.round(mins / 60);
	if (hours < 24) return `${hours}h ago`;
	return `${Math.round(hours / 24)}d ago`;
}
