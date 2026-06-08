import { describe, expect, it } from 'vitest';
import { dailySeries, sparkChar } from './stats';

describe('dailySeries', () => {
	it('returns an empty series for no days', () => {
		expect(dailySeries({})).toEqual([]);
	});

	it('fills gaps between the first and last active day with zeros', () => {
		const series = dailySeries({ '2026-06-01': 3, '2026-06-04': 1 });
		expect(series).toEqual([
			{ day: '2026-06-01', count: 3 },
			{ day: '2026-06-02', count: 0 },
			{ day: '2026-06-03', count: 0 },
			{ day: '2026-06-04', count: 1 }
		]);
	});

	it('does not pad before the first or after the last active day', () => {
		const series = dailySeries({ '2026-06-10': 5 });
		expect(series).toEqual([{ day: '2026-06-10', count: 5 }]);
	});

	it('keeps day keys stable regardless of local timezone', () => {
		// Across a month boundary, where a naive local->UTC round-trip would slip a day.
		const series = dailySeries({ '2026-06-30': 1, '2026-07-01': 2 });
		expect(series.map((s) => s.day)).toEqual(['2026-06-30', '2026-07-01']);
	});
});

describe('sparkChar', () => {
	it('uses the lowest block for zero or an empty period', () => {
		expect(sparkChar(0, 10)).toBe('▁');
		expect(sparkChar(5, 0)).toBe('▁');
	});

	it('uses the highest block at the peak', () => {
		expect(sparkChar(10, 10)).toBe('█');
	});

	it('gives any non-zero count at least the smallest visible block', () => {
		expect(sparkChar(1, 100)).toBe('▁');
	});
});
