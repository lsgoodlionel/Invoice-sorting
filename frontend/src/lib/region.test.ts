import { describe, expect, test } from 'vitest';
import { makeAttachment, makeInvoice } from '../test/fixtures';
import { CHINA_REGIONS, collectOrderNos, describeRegion, regionBadge } from './region';

describe('region helpers', () => {
  test('regionBadge distinguishes nonlocal, local and unknown', () => {
    expect(regionBadge('北京', true)).toEqual({ label: '外地·北京', color: 'orange' });
    expect(regionBadge('上海', false)).toEqual({ label: '上海', color: 'gray' });
    expect(regionBadge('', false)).toBeNull();
  });

  test('describeRegion marks nonlocal in parentheses', () => {
    expect(describeRegion('北京', true)).toBe('北京（外地）');
    expect(describeRegion('上海', false)).toBe('上海（本地）');
    expect(describeRegion('', false)).toBe('未知');
  });

  test('collectOrderNos returns unique non-empty invoice order numbers', () => {
    const attachments = [
      makeAttachment({ id: 1, invoice: makeInvoice({ order_no: 'JD001' }) }),
      makeAttachment({ id: 2, invoice: makeInvoice({ order_no: '' }) }),
      makeAttachment({ id: 3, kind: 'order', invoice: null }),
      makeAttachment({ id: 4, invoice: makeInvoice({ order_no: 'JD001' }) }),
      makeAttachment({ id: 5, invoice: makeInvoice({ order_no: 'DD9' }) }),
    ];
    expect(collectOrderNos(attachments)).toEqual(['JD001', 'DD9']);
  });

  test('CHINA_REGIONS lists 31 provincial short names including 上海', () => {
    expect(CHINA_REGIONS).toHaveLength(31);
    expect(new Set(CHINA_REGIONS).size).toBe(31);
    expect(CHINA_REGIONS).toContain('上海');
  });
});
