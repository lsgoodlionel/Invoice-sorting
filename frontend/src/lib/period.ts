// 周期预设 → {start, end}（含边界，按 Asia/Shanghai 的日历日期）。

export const TIME_ZONE = 'Asia/Shanghai';

export type PeriodPreset =
  | 'this_month'
  | 'this_quarter'
  | 'this_year'
  | 'last_month'
  | 'last_quarter'
  | 'last_3_years'
  | 'last_5_years'
  | 'last_10_years'
  | 'all' // 兼容旧链接：清单页表示不限日期，统计页视为近10年
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

/** 可直接点选的快捷区间（不含兼容用的 all 与手工修改后的 custom）。 */
export const PERIOD_OPTIONS: readonly { value: PeriodPreset; label: string }[] = [
  { value: 'this_month', label: '本月' },
  { value: 'this_quarter', label: '本季度' },
  { value: 'this_year', label: '本年' },
  { value: 'last_month', label: '上月' },
  { value: 'last_quarter', label: '上季度' },
  { value: 'last_3_years', label: '近3年' },
  { value: 'last_5_years', label: '近5年' },
  { value: 'last_10_years', label: '近10年' },
];

export const ALL_DATES_LABEL = '全部日期';
export const STATS_FALLBACK_PRESET: PeriodPreset = 'last_10_years';

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const MONTHS_PER_QUARTER = 3;
const MONTHS_PER_YEAR = 12;
const YEAR_SPANS: Partial<Record<PeriodPreset, number>> = { last_3_years: 3, last_5_years: 5, last_10_years: 10 };

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

/** 近 N 年：从 N×12−1 个月前的月初到本月月末（含当月）。 */
function recentYearsRange(current: YearMonth, years: number): DateRange {
  const monthCount = years * MONTHS_PER_YEAR;
  return monthRange(shiftMonth(current, -(monthCount - 1)), monthCount);
}

/** 计算预设区间；all/custom 返回 null（custom 由调用方提供起止）。 */
export function presetRange(preset: PeriodPreset, now: Date = new Date()): DateRange | null {
  const [year, month] = todayInShanghai(now).split('-').map(Number);
  const current: YearMonth = { year, month };
  const years = YEAR_SPANS[preset];
  if (years) return recentYearsRange(current, years);
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

const PRESET_VALUES = new Set<string>([...PERIOD_OPTIONS.map((option) => option.value), 'all', 'custom']);

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

/** 手工修改日期后的自定义周期；起止颠倒时自动交换，无效日期视为未填。 */
export function customPeriod(start: string | null | undefined, end: string | null | undefined): Period {
  const validStart = isValidDate(start) ? start : undefined;
  const validEnd = isValidDate(end) ? end : undefined;
  if (validStart && validEnd && validStart > validEnd) {
    return { preset: 'custom', start: validEnd, end: validStart };
  }
  return { preset: 'custom', start: validStart, end: validEnd };
}

/** 统计页不支持“不限日期”：旧链接的 all 视为近10年。 */
export function toStatsPeriod(period: Period): Period {
  return period.preset === 'all' ? { preset: STATS_FALLBACK_PRESET } : period;
}

/** 统计接口需要明确起止：all 视为近10年；自定义缺失的起点取近10年月初、终点取本月月末。 */
export function boundedRange(period: Period, now: Date = new Date()): DateRange {
  const range = resolvePeriod(toStatsPeriod(period), now);
  const fallback = presetRange(STATS_FALLBACK_PRESET, now) as DateRange;
  const start = range.start ?? fallback.start;
  const end = range.end ?? fallback.end;
  return start > end ? { start: end, end: start } : { start, end };
}

/** YYYY-MM-DD → “2025年05月” */
export function formatDataStart(value: string): string {
  return `${value.slice(0, 4)}年${value.slice(5, 7)}月`;
}

export function periodLabel(period: Period): string {
  if (period.preset === 'all') return ALL_DATES_LABEL;
  if (period.preset !== 'custom') {
    return PERIOD_OPTIONS.find((option) => option.value === period.preset)?.label ?? '';
  }
  return `${period.start ?? '…'} 至 ${period.end ?? '…'}`;
}
