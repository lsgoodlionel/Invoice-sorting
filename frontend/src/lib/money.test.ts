import { describe, expect, test } from 'vitest';
import { centsToYuanString, formatCents, parseYuanToCents, sumCents } from './money';

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
