import { describe, expect, test } from 'vitest';
import { buildCondition, conditionSwitches, describeCondition, INVOICE_EXEMPT_OPTIONS } from './rules';

const EMPTY_INPUT = { amountGte: null, amountLt: null, isOnlineOnly: false, isNonlocalOnly: false, excludeDetailPlatform: false, invoiceExempt: 'any' as const, contentKeywords: [] as string[], excludeKeywords: [] as string[] };

describe('rule conditions', () => {
  test('describeCondition', () => {
    expect(describeCondition({})).toBe('始终');
    expect(describeCondition({ amount_gte: 100000, amount_lt: 3000000, is_online: true })).toBe('金额 ≥ ¥1,000.00，金额 < ¥30,000.00，仅网购');
  });

  test('describeCondition covers nonlocal and detail platform flags', () => {
    expect(describeCondition({ is_nonlocal: true, detail_platform: false })).toBe('仅外地发票，排除已带明细平台');
    expect(describeCondition({ detail_platform: true })).toBe('仅已带明细平台');
    expect(describeCondition({ is_nonlocal: false })).toBe('仅本地发票');
  });

  test('buildCondition omits empty values', () => {
    expect(buildCondition(EMPTY_INPUT)).toEqual({});
    expect(buildCondition({ ...EMPTY_INPUT, amountGte: 0, amountLt: 500, isOnlineOnly: true })).toEqual({ amount_gte: 0, amount_lt: 500, is_online: true });
  });

  test('buildCondition encodes nonlocal and detail platform switches', () => {
    expect(buildCondition({ ...EMPTY_INPUT, isNonlocalOnly: true })).toEqual({ is_nonlocal: true });
    expect(buildCondition({ ...EMPTY_INPUT, excludeDetailPlatform: true })).toEqual({ detail_platform: false });
    expect(buildCondition({ ...EMPTY_INPUT, isNonlocalOnly: true, excludeDetailPlatform: true })).toEqual({ is_nonlocal: true, detail_platform: false });
  });

  test('conditionSwitches reads flags back from a stored condition', () => {
    expect(conditionSwitches({ is_nonlocal: true, detail_platform: false, is_online: true })).toEqual({
      isOnlineOnly: true, isNonlocalOnly: true, excludeDetailPlatform: true, invoiceExempt: 'any', contentKeywords: [], excludeKeywords: [],
    });
    expect(conditionSwitches({})).toEqual({ isOnlineOnly: false, isNonlocalOnly: false, excludeDetailPlatform: false, invoiceExempt: 'any', contentKeywords: [], excludeKeywords: [] });
  });

  test('invoice exempt condition is described, encoded and read back', () => {
    expect(describeCondition({ invoice_exempt: true })).toBe('仅免发票记录');
    expect(describeCondition({ invoice_exempt: false, is_nonlocal: true })).toBe('仅外地发票，排除免发票记录');
    expect(buildCondition({ ...EMPTY_INPUT, invoiceExempt: 'only' })).toEqual({ invoice_exempt: true });
    expect(buildCondition({ ...EMPTY_INPUT, invoiceExempt: 'exclude' })).toEqual({ invoice_exempt: false });
    expect(conditionSwitches({ invoice_exempt: true }).invoiceExempt).toBe('only');
    expect(conditionSwitches({ invoice_exempt: false }).invoiceExempt).toBe('exclude');
    expect(INVOICE_EXEMPT_OPTIONS.map((option) => option.label)).toEqual(['不限', '仅免发票记录', '排除免发票记录']);
  });

  test('content keyword conditions are described, encoded and read back', () => {
    const lodging = ['住宿', '酒店'];
    expect(describeCondition({ content_keywords: lodging })).toBe('发票内容含：住宿、酒店');
    expect(describeCondition({ exclude_keywords: lodging })).toBe('发票内容不含：住宿、酒店');
    expect(buildCondition({ ...EMPTY_INPUT, contentKeywords: [' 住宿 ', '', '酒店'] })).toEqual({ content_keywords: lodging });
    expect(buildCondition({ ...EMPTY_INPUT, excludeKeywords: lodging })).toEqual({ exclude_keywords: lodging });
    expect(conditionSwitches({ content_keywords: lodging }).contentKeywords).toEqual(lodging);
    expect(conditionSwitches({ exclude_keywords: lodging }).excludeKeywords).toEqual(lodging);
  });
});
