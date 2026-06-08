// Derived views over a summary's `by_day` / `by_repo` count maps, used by
// SummaryStats. Kept pure (and timezone-stable) so the date logic is testable.

export interface DayCount {
	day: string;
	count: number;
}

// `byDay` only carries days that had commits. Fill the gaps between the first
// and last active day so a sparkline shows quiet days too, not a misleading run
// of solid bars. Dates are walked in UTC so a 'YYYY-MM-DD' key never shifts a
// day under the viewer's local timezone.
export function dailySeries(byDay: Record<string, number>): DayCount[] {
	const days = Object.keys(byDay).sort();
	if (days.length === 0) return [];

	const series: DayCount[] = [];
	const cur = new Date(days[0] + 'T00:00:00Z');
	const end = new Date(days[days.length - 1] + 'T00:00:00Z');
	while (cur <= end) {
		const key = cur.toISOString().slice(0, 10);
		series.push({ day: key, count: byDay[key] ?? 0 });
		cur.setUTCDate(cur.getUTCDate() + 1);
	}
	return series;
}

const BLOCKS = ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█'];

// Map a count to one of eight block glyphs, scaled against the period's peak.
// Any non-zero count gets at least the smallest visible block.
export function sparkChar(count: number, max: number): string {
	if (max === 0 || count === 0) return BLOCKS[0];
	const idx = Math.ceil((count / max) * BLOCKS.length) - 1;
	return BLOCKS[Math.min(BLOCKS.length - 1, Math.max(0, idx))];
}
