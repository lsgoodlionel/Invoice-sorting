import { describe, expect, test } from 'vitest';
import { makeCandidate } from '../test/fixtures';
import { candidateLabel, candidateOptionLabel, candidateReasons } from './candidates';

describe('candidate labels', () => {
  test('label with id, merchant and amount', () => {
    expect(candidateLabel(makeCandidate())).toBe('#42 腾讯云 ¥298.00');
    expect(candidateLabel(makeCandidate({ merchant: '', amount_cents: 14426, currency: 'USD', original_amount_cents: 2000 })))
      .toBe('#42 ¥144.26（US$20.00）');
  });

  test('reasons and option label', () => {
    expect(candidateReasons(makeCandidate())).toBe('金额相同、日期相差 1 天');
    expect(candidateReasons(makeCandidate({ reasons: [] }))).toBe('');
    expect(candidateOptionLabel(makeCandidate())).toBe('挂到 #42 腾讯云 ¥298.00 · 85 分 · 金额相同、日期相差 1 天');
    expect(candidateOptionLabel(makeCandidate({ reasons: [] }))).toBe('挂到 #42 腾讯云 ¥298.00 · 85 分');
  });
});
