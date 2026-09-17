// 周期预设 → {start, end}（含边界，按 Asia/Shanghai 的日历日期）。

export const TIME_ZONE = 'Asia/Shanghai';

export type PeriodPreset =
  | 'this_month'
  | 'this_quarter'
  | 'this_year'
  | 'last_month'
  | 'last_quarter'
  | 'all'
  | 'custom';

export interface DateRange {
  start: string;
  end: string;
}

export interface Period {
  preset: PeriodPreset;
  start?: string;
  end?: string;
}

export const DEFAULT_PRESET: PeriodPreset = 'this_year';

export const PERIOD_OPTIONS: readonly { value: PeriodPreset; label: string }[] = [
  { value: 'this_month', label: '本月' },
  { value: 'this_quarter', label: '本季度' },
  { value: 'this_year', label: '本年' },
  { value: 'last_month', label: '上月' },
  { value: 'last_quarter', label: '上季度' },
  { value: 'all', label: '全部' },
  { value: 'custom', label: '自定义' },
];

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const MONTHS_PER_QUARTER = 3;

interface YearMonth {
  year: number;
  month: number; // 1-12
}

const pad = (value: number): string => String(value).padStart(2, '0');

export function isValidDate(value: string | null | undefined): value is string {
  if (!value || !DATE_PATTERN.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  return month >= 1 && month <= 12 && day >= 1 && day <= daysInMonth({ year, month });
}

/** 返回上海时区的今天 YYYY-MM-DD */
export function todayInShanghai(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now);
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? '';
  return `${get('year')}-${get('month')}-${get('day')}`;
}

function daysInMonth({ year, month }: YearMonth): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

function shiftMonth({ year, month }: YearMonth, delta: number): YearMonth {
  const index = year * 12 + (month - 1) + delta;
  return { year: Math.floor(index / 12), month: (index % 12) + 1 };
}

function monthRange(first: YearMonth, monthCount: number): DateRange {
  const last = shiftMonth(first, monthCount - 1);
  return {
    start: `${first.year}-${pad(first.month)}-01`,
    end: `${last.year}-${pad(last.month)}-${pad(daysInMonth(last))}`,
  };
}

function quarterStart({ year, month }: YearMonth): YearMonth {
  return { year, month: Math.floor((month - 1) / MONTHS_PER_QUARTER) * MONTHS_PER_QUARTER + 1 };
}

/** 计算预设区间；all/custom 返回 null（custom 由调用方提供起止）。 */
export function presetRange(preset: PeriodPreset, now: Date = new Date()): DateRange | null {
  const [year, month] = todayInShanghai(now).split('-').map(Number);
  const current: YearMonth = { year, month };
  switch (preset) {
    case 'this_month':
      return monthRange(current, 1);
    case 'last_month':
      return monthRange(shiftMonth(current, -1), 1);
    case 'this_quarter':
      return monthRange(quarterStart(current), MONTHS_PER_QUARTER);
    case 'last_quarter':
      return monthRange(shiftMonth(quarterStart(current), -MONTHS_PER_QUARTER), MONTHS_PER_QUARTER);
    case 'this_year':
      return monthRange({ year, month: 1 }, 12);
    default:
      return null;
  }
}

/** 解析周期为实际查询区间；无日期限制时返回 {}。 */
export function resolvePeriod(period: Period, now: Date = new Date()): Partial<DateRange> {
  if (period.preset === 'custom') {
    return {
      ...(isValidDate(period.start) ? { start: period.start } : {}),
      ...(isValidDate(period.end) ? { end: period.end } : {}),
    };
  }
  return presetRange(period.preset, now) ?? {};
}

const PRESET_VALUES = new Set<string>(PERIOD_OPTIONS.map((option) => option.value));

export function isPreset(value: string | null): value is PeriodPreset {
  return value !== null && PRESET_VALUES.has(value);
}

/** 从 URL 查询参数解码周期。只有起止日期时视为自定义。 */
export function decodePeriod(params: URLSearchParams, fallback: PeriodPreset = DEFAULT_PRESET): Period {
  const raw = params.get('period');
  const start = params.get('start') ?? undefined;
  const end = params.get('end') ?? undefined;
  if (isPreset(raw) && raw !== 'custom') return { preset: raw };
  if (raw === 'custom' || isValidDate(start) || isValidDate(end)) {
    return {
      preset: 'custom',
      start: isValidDate(start) ? start : undefined,
      end: isValidDate(end) ? end : undefined,
    };
  }
  return { preset: fallback };
}

/** 将周期写入查询参数，返回新的 URLSearchParams，不修改传入对象。 */
export function encodePeriod(params: URLSearchParams, period: Period): URLSearchParams {
  const next = new URLSearchParams(params);
  next.set('period', period.preset);
  next.delete('start');
  next.delete('end');
  if (period.preset === 'custom') {
    if (isValidDate(period.start)) next.set('start', period.start);
    if (isValidDate(period.end)) next.set('end', period.end);
  }
  return next;
}

export function periodLabel(period: Period): string {
  if (period.preset !== 'custom') {
    return PERIOD_OPTIONS.find((option) => option.value === period.preset)?.label ?? '';
  }
  return `${period.start ?? '…'} 至 ${period.end ?? '…'}`;
}
