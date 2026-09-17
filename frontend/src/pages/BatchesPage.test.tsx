import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import type { BatchDetail } from '../api/types';
import { mockFetch } from '../test/fetchMock';
import { makeBatch, makeExpense } from '../test/fixtures';
import { renderWithProviders } from '../test/render';
import { BatchesPage } from './BatchesPage';

describe('BatchesPage', () => {
  test('creating a batch selects it and opens the add-records modal', async () => {
    const user = userEvent.setup();
    let batches: BatchDetail[] = [];
    const created = makeBatch({ id: 12, name: '10月第1批' });
    const { calls } = mockFetch({
      'GET /api/batches': () => ({ data: batches }),
      'POST /api/batches': () => {
        batches = [created];
        return { data: created };
      },
      'GET /api/batches/12': created,
      'GET /api/projects': [],
      'GET /api/expenses': { items: [makeExpense({ id: 1, merchant: '京东某店' })], total: 1, total_cents: 0, status_counts: {} },
    });
    renderWithProviders(<BatchesPage />, { route: '/batches' });
    await user.click(await screen.findByRole('button', { name: '新建批次' }));
    await user.type(await screen.findByLabelText(/名称/), '10月第1批');
    await user.click(screen.getByRole('button', { name: '创建' }));

    expect(await screen.findByText('添加记录到「10月第1批」')).toBeInTheDocument();
    expect(await screen.findByLabelText('选择 京东某店')).toBeInTheDocument();
    await waitFor(() => expect(calls.some((call) => call.url === '/api/batches/12')).toBe(true));
  });
});
