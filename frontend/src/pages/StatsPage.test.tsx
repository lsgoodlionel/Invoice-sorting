import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import type { Stats } from '../api/types';
import { presetRange } from '../lib/period';
import { mockFetch, type RecordedCall } from '../test/fetchMock';
import { renderWithProviders } from '../test/render';
import { StatsPage } from './StatsPage';

const TOTALS = { spent_cents: 30000, pending_cents: 0, in_transit_cents: 0, reimbursed_cents: 0, void_cents: 0 };

function makeStats(overrides: Partial<Stats> = {}): Stats {
  return {
    start: '2016-10-01',
    end: '2026-09-30',
    date_basis: 'spent',
    data_start: '2025-05-18',
    totals: TOTALS,
    rows: [],
    months: [
      { month: '2025-05', amount_cents: 30000 },
      { month: '2025-06', amount_cents: 0 },
    ],
    ...overrides,
  };
}

const statsCalls = (calls: RecordedCall[]) => calls.filter((call) => call.url.startsWith('/api/stats'));
const lastParams = (calls: RecordedCall[]) => new URL(statsCalls(calls).at(-1)?.url ?? '', 'http://x').searchParams;

describe('StatsPage', () => {
  test('legacy period=all requests the last 10 years instead of 2000-01-01', async () => {
    const { calls } = mockFetch({ 'GET /api/stats': makeStats() });
    renderWithProviders(<StatsPage />, { route: '/stats?period=all' });
    const decade = presetRange('last_10_years') ?? { start: '', end: '' };
    await waitFor(() => expect(statsCalls(calls).length).toBeGreaterThan(0));
    expect(lastParams(calls).get('start')).toBe(decade.start);
    expect(lastParams(calls).get('end')).toBe(decade.end);
    expect(calls.some((call) => call.url.includes('2000-01-01'))).toBe(false);
    expect(screen.getByRole('button', { name: '近10年' })).toHaveAttribute('aria-pressed', 'true');
  });

  test('shows the data start hint when data begins after the selected start', async () => {
    mockFetch({ 'GET /api/stats': makeStats() });
    renderWithProviders(<StatsPage />, { route: '/stats?period=last_10_years' });
    expect(await screen.findByText('（数据自 2025年05月 起）')).toBeInTheDocument();
    expect(screen.getAllByText('25-05').length).toBeGreaterThan(0);
  });

  test('hides the hint when data starts before the selected start', async () => {
    mockFetch({ 'GET /api/stats': makeStats({ start: '2026-01-01', end: '2026-12-31', data_start: '2026-01-01' }) });
    renderWithProviders(<StatsPage />, { route: '/stats' });
    await screen.findAllByText('25-05');
    await waitFor(() => expect(screen.getByRole('button', { name: '本年' })).toHaveAttribute('aria-pressed', 'true'));
    expect(screen.queryByText(/数据自/)).not.toBeInTheDocument();
  });

  test('clicking a preset requests its resolved range', async () => {
    const { calls } = mockFetch({ 'GET /api/stats': makeStats({ data_start: null }) });
    renderWithProviders(<StatsPage />, { route: '/stats' });
    await userEvent.setup().click(screen.getByRole('button', { name: '近3年' }));
    const range = presetRange('last_3_years') ?? { start: '', end: '' };
    await waitFor(() => expect(lastParams(calls).get('start')).toBe(range.start));
    expect(lastParams(calls).get('end')).toBe(range.end);
  });
});
