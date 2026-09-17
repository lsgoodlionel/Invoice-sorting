import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import type { ExpenseListResult } from '../api/types';
import { mockFetch } from '../test/fetchMock';
import { makeExpense } from '../test/fixtures';
import { renderWithProviders } from '../test/render';
import { ExpensesPage } from './ExpensesPage';

const list: ExpenseListResult = {
  items: [
    makeExpense({ id: 1, merchant: '京东某店', amount_cents: 96000, missing_count: 2 }),
    makeExpense({ id: 2, merchant: '腾讯云', amount_cents: 29800, status: 'complete', batch_name: '9月第1批' }),
  ],
  total: 2,
  total_cents: 125800,
  status_counts: {
    invoiced: { count: 1, amount_cents: 96000 },
    complete: { count: 1, amount_cents: 29800 },
  },
};

function setupRoutes(items: ExpenseListResult = list) {
  return mockFetch({
    'GET /api/expenses': items,
    'GET /api/categories': [],
    'GET /api/projects': [],
    'GET /api/batches': [],
  });
}

describe('ExpensesPage', () => {
  test('renders rows and status group counts', async () => {
    setupRoutes();
    renderWithProviders(<ExpensesPage />, { route: '/expenses?period=all' });
    expect(await screen.findByText('京东某店')).toBeInTheDocument();
    expect(screen.getByText('腾讯云')).toBeInTheDocument();
    expect(screen.getAllByText('¥960.00').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('缺 2 项')).toBeInTheDocument();
    expect(screen.getByText('9月第1批')).toBeInTheDocument();
    expect(screen.getByTestId('status-count-invoiced')).toHaveTextContent('1');
    expect(screen.getByTestId('status-count-complete')).toHaveTextContent('1');
    expect(screen.getByTestId('status-count-spent')).toHaveTextContent('0');
    expect(within(screen.getByTestId('status-group-invoiced')).getByText('¥960.00')).toBeInTheDocument();
    expect(screen.getByText(/共 2 条/)).toHaveTextContent('¥1,258.00');
  });

  test('clicking a status group adds it to the request filter', async () => {
    const user = userEvent.setup();
    const { calls } = setupRoutes();
    renderWithProviders(<ExpensesPage />, { route: '/expenses?period=all' });
    await screen.findByText('京东某店');
    await user.click(screen.getByTestId('status-group-sent'));
    await waitFor(() => expect(calls.some((c) => c.url.includes('status=sent'))).toBe(true));
    expect(screen.getByTestId('status-group-sent')).toHaveAttribute('aria-pressed', 'true');
  });

  test('selection shows total and add-to-batch bar', async () => {
    const user = userEvent.setup();
    setupRoutes();
    renderWithProviders(<ExpensesPage />, { route: '/expenses?period=all' });
    await user.click(await screen.findByLabelText('选择 京东某店'));
    await user.click(screen.getByLabelText('选择 腾讯云'));
    expect(screen.getByText(/已选/)).toHaveTextContent('已选 2 条 · 合计 ¥1,258.00');
    expect(screen.getByRole('button', { name: /加入批次/ })).toBeEnabled();
  });

  test('shows guidance when empty', async () => {
    setupRoutes({ items: [], total: 0, total_cents: 0, status_counts: {} });
    renderWithProviders(<ExpensesPage />, { route: '/expenses' });
    expect(await screen.findByText('这里还没有记录')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '去收集页' })).toHaveAttribute('href', '/collect');
  });
});
