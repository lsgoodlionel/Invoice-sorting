import { describe, expect, test } from 'vitest';
import { buildCondition, describeCondition } from './rules';

describe('rule conditions', () => {
  test('describeCondition', () => {
    expect(describeCondition({})).toBe('始终');
    expect(describeCondition({ amount_gte: 100000, amount_lt: 3000000, is_online: true })).toBe('金额 ≥ ¥1,000.00，金额 < ¥30,000.00，仅网购');
  });

  test('buildCondition omits empty values', () => {
    expect(buildCondition({ amountGte: null, amountLt: null, isOnlineOnly: false })).toEqual({});
    expect(buildCondition({ amountGte: 0, amountLt: 500, isOnlineOnly: true })).toEqual({ amount_gte: 0, amount_lt: 500, is_online: true });
  });
});
