import { describe, expect, test } from 'vitest';
import { centsToYuanString, CURRENCY_OPTIONS, currencySymbol, formatCents, formatMoney, isForeignCurrency, parseYuanToCents, sumCents } from './money';

describe('formatCents', () => {
  test('formats with symbol, thousands and two decimals', () => {
    expect(formatCents(96000)).toBe('¥960.00');
    expect(formatCents(123456789)).toBe('¥1,234,567.89');
    expect(formatCents(5)).toBe('¥0.05');
    expect(formatCents(0)).toBe('¥0.00');
  });

  test('formats negative amounts with leading minus', () => {
    expect(formatCents(-12345)).toBe('-¥123.45');
  });

  test('omits symbol when requested', () => {
    expect(formatCents(100000, { symbol: false })).toBe('1,000.00');
  });

  test('returns dash for missing or non-finite values', () => {
    expect(formatCents(null)).toBe('—');
    expect(formatCents(undefined)).toBe('—');
    expect(formatCents(Number.NaN)).toBe('—');
  });
});

describe('parseYuanToCents', () => {
  test('parses thousands separators and partial decimals', () => {
    expect(parseYuanToCents('1,234.5')).toBe(123450);
    expect(parseYuanToCents('960')).toBe(96000);
    expect(parseYuanToCents('¥ 12.34')).toBe(1234);
    expect(parseYuanToCents('.5')).toBe(50);
    expect(parseYuanToCents('7.')).toBe(700);
  });

  test('avoids floating point errors such as 0.1 + 0.2 and 19.99', () => {
    expect(parseYuanToCents('0.1')! + parseYuanToCents('0.2')!).toBe(30);
    expect(parseYuanToCents('19.99')).toBe(1999);
    expect(parseYuanToCents('1.005')).toBe(101);
    expect(parseYuanToCents('4.35')).toBe(435);
    expect(parseYuanToCents(0.29)).toBe(29);
  });

  test('rounds the third decimal half up', () => {
    expect(parseYuanToCents('2.344')).toBe(234);
    expect(parseYuanToCents('2.345')).toBe(235);
  });

  test('handles negative values', () => {
    expect(parseYuanToCents('-12.30')).toBe(-1230);
    expect(parseYuanToCents('-0')).toBe(0);
  });

  test('returns null for invalid input', () => {
    expect(parseYuanToCents('')).toBeNull();
    expect(parseYuanToCents('abc')).toBeNull();
    expect(parseYuanToCents('1.2.3')).toBeNull();
    expect(parseYuanToCents('-')).toBeNull();
    expect(parseYuanToCents(null)).toBeNull();
    expect(parseYuanToCents(undefined)).toBeNull();
    expect(parseYuanToCents('99999999999999999')).toBeNull();
  });
});

describe('helpers', () => {
  test('centsToYuanString strips grouping', () => {
    expect(centsToYuanString(123456)).toBe('1234.56');
    expect(centsToYuanString(null)).toBe('');
  });

  test('sumCents adds integers', () => {
    expect(sumCents([10, 20, 30])).toBe(60);
    expect(sumCents([])).toBe(0);
  });
});

describe('formatMoney', () => {
  test('uses currency symbols', () => {
    expect(formatMoney(2000, 'USD')).toBe('US$20.00');
    expect(formatMoney(123456, 'EUR')).toBe('€1,234.56');
    expect(formatMoney(999, 'GBP')).toBe('£9.99');
    expect(formatMoney(10000, 'HKD')).toBe('HK$100.00');
    expect(formatMoney(150000, 'JPY')).toBe('JP¥1,500.00');
    expect(formatMoney(14426, 'CNY')).toBe('¥144.26');
  });

  test('treats empty currency as CNY and is case-insensitive', () => {
    expect(formatMoney(100, '')).toBe('¥1.00');
    expect(formatMoney(100, 'usd')).toBe('US$1.00');
  });

  test('falls back to ISO code prefix for unknown currencies', () => {
    expect(formatMoney(500, 'SGD')).toBe('SGD 5.00');
  });

  test('handles negative and missing amounts', () => {
    expect(formatMoney(-2000, 'USD')).toBe('-US$20.00');
    expect(formatMoney(null, 'USD')).toBe('—');
  });

  test('currency helpers', () => {
    expect(currencySymbol('USD')).toBe('US$');
    expect(currencySymbol('XYZ')).toBe('XYZ');
    expect(isForeignCurrency('USD')).toBe(true);
    expect(isForeignCurrency('CNY')).toBe(false);
    expect(isForeignCurrency('')).toBe(false);
    expect(CURRENCY_OPTIONS.map((option) => option.value)).toEqual(['CNY', 'USD', 'EUR', 'GBP', 'HKD', 'JPY']);
  });
});
