import { describe, expect, test } from 'vitest';
import {
  ATTACHMENT_KIND_OPTIONS,
  isDateBasis,
  isStatus,
  parseStatusList,
  STATUS_META,
  statusLabel,
  statusRank,
  stepLabel,
  toggleStatus,
} from './status';

describe('status utils', () => {
  test('labels and ranks follow the main line', () => {
    expect(statusLabel('complete')).toBe('凭证齐全');
    expect(statusRank('spent')).toBe(0);
    expect(statusRank('reimbursed')).toBe(4);
    expect(statusRank('void')).toBe(-1);
  });

  test('semantic colors', () => {
    expect(STATUS_META.spent.color).toBe('gray');
    expect(STATUS_META.invoiced.color).toBe('blue');
    expect(STATUS_META.complete.color).toBe('green');
    expect(STATUS_META.sent.color).toBe('orange');
    expect(STATUS_META.reimbursed).toMatchObject({ color: 'ink', variant: 'filled' });
  });

  test('parseStatusList filters invalid values and duplicates', () => {
    expect(parseStatusList('spent, sent,foo,spent')).toEqual(['spent', 'sent']);
    expect(parseStatusList(null)).toEqual([]);
    expect(isStatus('void')).toBe(true);
    expect(isStatus('draft')).toBe(false);
  });

  test('toggleStatus returns new arrays', () => {
    const selected = ['spent'] as const;
    const added = toggleStatus(selected, 'sent');
    expect(added).toEqual(['spent', 'sent']);
    expect(toggleStatus(added, 'spent')).toEqual(['sent']);
    expect(selected).toEqual(['spent']);
  });

  test('date basis guard and kind options', () => {
    expect(isDateBasis('received')).toBe(true);
    expect(isDateBasis('created')).toBe(false);
    expect(ATTACHMENT_KIND_OPTIONS).toHaveLength(12);
  });
  test('stepLabel shows 已收凭证 for invoice exempt records on the second step', () => {
    expect(stepLabel('invoiced', false)).toBe('已开票');
    expect(stepLabel('invoiced', true)).toBe('已收凭证');
    expect(stepLabel('complete', true)).toBe('凭证齐全');
  });
});
