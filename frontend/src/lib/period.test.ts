import { describe, expect, test } from 'vitest';
import {
  boundedRange,
  customPeriod,
  decodePeriod,
  formatDataStart,
  PERIOD_OPTIONS,
  toStatsPeriod,
  encodePeriod,
  isValidDate,
  periodLabel,
  presetRange,
  resolvePeriod,
  todayInShanghai,
} from './period';

// 2026-09-17 10:00 Asia/Shanghai
const MID_SEPT = new Date('2026-09-17T02:00:00Z');

describe('todayInShanghai', () => {
  test('uses Shanghai calendar date even when UTC is still the previous day', () => {
    expect(todayInShanghai(new Date('2026-12-31T16:30:00Z'))).toBe('2027-01-01');
    expect(todayInShanghai(MID_SEPT)).toBe('2026-09-17');
  });
});

describe('presetRange', () => {
  test('this month / quarter / year', () => {
    expect(presetRange('this_month', MID_SEPT)).toEqual({ start: '2026-09-01', end: '2026-09-30' });
    expect(presetRange('this_quarter', MID_SEPT)).toEqual({ start: '2026-07-01', end: '2026-09-30' });
    expect(presetRange('this_year', MID_SEPT)).toEqual({ start: '2026-01-01', end: '2026-12-31' });
  });

  test('last month crosses year boundary in January', () => {
    const jan = new Date('2027-01-10T04:00:00Z');
    expect(presetRange('last_month', jan)).toEqual({ start: '2026-12-01', end: '2026-12-31' });
  });

  test('last quarter crosses year boundary in Q1', () => {
    const feb = new Date('2027-02-10T04:00:00Z');
    expect(presetRange('last_quarter', feb)).toEqual({ start: '2026-10-01', end: '2026-12-31' });
    expect(presetRange('last_quarter', MID_SEPT)).toEqual({ start: '2026-04-01', end: '2026-06-30' });
  });

  test('handles leap-year February', () => {
    const leap = new Date('2028-02-15T04:00:00Z');
    expect(presetRange('this_month', leap)).toEqual({ start: '2028-02-01', end: '2028-02-29' });
    expect(presetRange('last_month', new Date('2028-03-02T04:00:00Z'))).toEqual({ start: '2028-02-01', end: '2028-02-29' });
  });

  test('New Year eve UTC evening already counts as next year in Shanghai', () => {
    const utcEve = new Date('2026-12-31T17:00:00Z');
    expect(presetRange('this_quarter', utcEve)).toEqual({ start: '2027-01-01', end: '2027-03-31' });
  });

  test('last N years spans N*12 months ending with the current month', () => {
    expect(presetRange('last_3_years', MID_SEPT)).toEqual({ start: '2023-10-01', end: '2026-09-30' });
    expect(presetRange('last_5_years', MID_SEPT)).toEqual({ start: '2021-10-01', end: '2026-09-30' });
    expect(presetRange('last_10_years', MID_SEPT)).toEqual({ start: '2016-10-01', end: '2026-09-30' });
  });

  test('last N years in January starts in February N years back', () => {
    const jan = new Date('2027-01-10T04:00:00Z');
    expect(presetRange('last_3_years', jan)).toEqual({ start: '2024-02-01', end: '2027-01-31' });
    expect(presetRange('last_10_years', jan)).toEqual({ start: '2017-02-01', end: '2027-01-31' });
  });

  test('last N years ending in a leap February and on Shanghai New Year', () => {
    const leap = new Date('2028-02-15T04:00:00Z');
    expect(presetRange('last_5_years', leap)).toEqual({ start: '2023-03-01', end: '2028-02-29' });
    const utcEve = new Date('2026-12-31T17:00:00Z');
    expect(presetRange('last_3_years', utcEve)).toEqual({ start: '2024-02-01', end: '2027-01-31' });
  });

  test('all and custom return null', () => {
    expect(presetRange('all', MID_SEPT)).toBeNull();
    expect(presetRange('custom', MID_SEPT)).toBeNull();
  });
});

describe('resolvePeriod', () => {
  test('custom keeps only valid bounds', () => {
    expect(resolvePeriod({ preset: 'custom', start: '2026-01-05', end: 'bad' })).toEqual({ start: '2026-01-05' });
    expect(resolvePeriod({ preset: 'all' })).toEqual({});
    expect(resolvePeriod({ preset: 'this_month' }, MID_SEPT)).toEqual({ start: '2026-09-01', end: '2026-09-30' });
  });
});

describe('isValidDate', () => {
  test('rejects impossible dates', () => {
    expect(isValidDate('2026-02-29')).toBe(false);
    expect(isValidDate('2028-02-29')).toBe(true);
    expect(isValidDate('2026-13-01')).toBe(false);
    expect(isValidDate('20260101')).toBe(false);
    expect(isValidDate(null)).toBe(false);
  });
});

describe('URL encoding', () => {
  test('round-trips presets and custom ranges', () => {
    const preset = encodePeriod(new URLSearchParams('q=x&start=2026-01-01'), { preset: 'last_month' });
    expect(preset.toString()).toBe('q=x&period=last_month');
    expect(decodePeriod(preset)).toEqual({ preset: 'last_month' });

    const custom = encodePeriod(new URLSearchParams(), { preset: 'custom', start: '2026-01-01', end: '2026-02-01' });
    expect(decodePeriod(custom)).toEqual({ preset: 'custom', start: '2026-01-01', end: '2026-02-01' });
  });

  test('does not mutate input params', () => {
    const original = new URLSearchParams('a=1');
    encodePeriod(original, { preset: 'this_year' });
    expect(original.toString()).toBe('a=1');
  });

  test('bare start/end implies custom; invalid preset falls back', () => {
    expect(decodePeriod(new URLSearchParams('start=2026-03-01'))).toEqual({ preset: 'custom', start: '2026-03-01', end: undefined });
    expect(decodePeriod(new URLSearchParams('period=bogus'), 'this_month')).toEqual({ preset: 'this_month' });
  });

  test('legacy period=all still decodes; custom with dates keeps working', () => {
    expect(decodePeriod(new URLSearchParams('period=all'))).toEqual({ preset: 'all' });
    expect(encodePeriod(new URLSearchParams(), { preset: 'all' }).toString()).toBe('period=all');
    expect(decodePeriod(new URLSearchParams('period=last_5_years'))).toEqual({ preset: 'last_5_years' });
  });

  test('periodLabel', () => {
    expect(periodLabel({ preset: 'this_quarter' })).toBe('本季度');
    expect(periodLabel({ preset: 'last_3_years' })).toBe('近3年');
    expect(periodLabel({ preset: 'all' })).toBe('全部日期');
    expect(periodLabel({ preset: 'custom', start: '2026-01-01' })).toBe('2026-01-01 至 …');
  });
});

describe('selectable presets', () => {
  test('offers quick ranges only, without all/custom', () => {
    expect(PERIOD_OPTIONS.map((option) => option.label)).toEqual(['本月', '本季度', '本年', '上月', '上季度', '近3年', '近5年', '近10年']);
  });
});

describe('customPeriod', () => {
  test('swaps reversed bounds', () => {
    expect(customPeriod('2026-05-01', '2026-02-01')).toEqual({ preset: 'custom', start: '2026-02-01', end: '2026-05-01' });
  });

  test('keeps ordered or partial bounds and drops invalid ones', () => {
    expect(customPeriod('2026-02-01', '2026-02-01')).toEqual({ preset: 'custom', start: '2026-02-01', end: '2026-02-01' });
    expect(customPeriod(null, '2026-02-01')).toEqual({ preset: 'custom', start: undefined, end: '2026-02-01' });
    expect(customPeriod('bad', undefined)).toEqual({ preset: 'custom', start: undefined, end: undefined });
  });
});

describe('stats period', () => {
  test('legacy all maps to last 10 years', () => {
    expect(toStatsPeriod({ preset: 'all' })).toEqual({ preset: 'last_10_years' });
    expect(toStatsPeriod({ preset: 'this_month' })).toEqual({ preset: 'this_month' });
  });

  test('boundedRange always returns both bounds and never 2000-01-01', () => {
    expect(boundedRange({ preset: 'all' }, MID_SEPT)).toEqual({ start: '2016-10-01', end: '2026-09-30' });
    expect(boundedRange({ preset: 'this_year' }, MID_SEPT)).toEqual({ start: '2026-01-01', end: '2026-12-31' });
    expect(boundedRange({ preset: 'custom', start: '2025-03-01' }, MID_SEPT)).toEqual({ start: '2025-03-01', end: '2026-09-30' });
    expect(boundedRange({ preset: 'custom', end: '2020-01-31' }, MID_SEPT)).toEqual({ start: '2016-10-01', end: '2020-01-31' });
  });
});

describe('formatDataStart', () => {
  test('formats year and month in Chinese', () => {
    expect(formatDataStart('2025-05-18')).toBe('2025年05月');
  });
});
