import { describe, expect, test } from 'vitest';
import { buildCondition, conditionSwitches, describeCondition } from './rules';

const EMPTY_INPUT = { amountGte: null, amountLt: null, isOnlineOnly: false, isNonlocalOnly: false, excludeDetailPlatform: false };

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
      isOnlineOnly: true, isNonlocalOnly: true, excludeDetailPlatform: true,
    });
    expect(conditionSwitches({})).toEqual({ isOnlineOnly: false, isNonlocalOnly: false, excludeDetailPlatform: false });
  });
});
