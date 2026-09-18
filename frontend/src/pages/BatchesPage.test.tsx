import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useLocation } from 'react-router';
import { describe, expect, test } from 'vitest';
import type { BatchDetail } from '../api/types';
import { presetRange } from '../lib/period';
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

  describe('batch list filters', () => {
    const month = presetRange('this_month') ?? { start: '', end: '' };
    const list = [
      makeBatch({ id: 1, name: '草稿批', status: 'draft', total_cents: 10000, created_at: `${month.start}T10:00:00+08:00` }),
      makeBatch({ id: 2, name: '外发批', status: 'sent', total_cents: 20000, created_at: '2020-01-05T10:00:00+08:00', sent_on: month.end }),
      makeBatch({ id: 3, name: '到账批', status: 'received', total_cents: 40000, created_at: '2020-01-06T10:00:00+08:00', sent_on: '2020-02-01', received_on: '2020-03-01' }),
    ];

    function LocationProbe() {
      return <div data-testid="location">{useLocation().search}</div>;
    }

    function setup(route: string) {
      mockFetch({
        'GET /api/batches': list,
        'GET /api/batches/1': list[0],
        'GET /api/batches/2': list[1],
        'GET /api/batches/3': list[2],
        'GET /api/projects': [],
        'GET /api/categories': [],
      });
      renderWithProviders(<><BatchesPage /><LocationProbe /></>, { route });
    }

    const listedNames = () => screen.getAllByRole('listitem').map((item) => item.querySelector('p')?.textContent);
    const search = () => new URLSearchParams(screen.getByTestId('location').textContent ?? '');

    test('shows count and total of all batches by default', async () => {
      setup('/batches');
      expect(await screen.findByTestId('batch-list-summary')).toHaveTextContent('3 个批次 · 合计 ¥700.00');
      expect(screen.getByRole('button', { name: '全部日期' })).toHaveAttribute('aria-pressed', 'true');
    });

    test('status filter narrows the list and syncs to the URL', async () => {
      const user = userEvent.setup();
      setup('/batches');
      await screen.findByTestId('batch-list-summary');
      await user.click(screen.getByRole('radio', { name: '已到账' }));
      expect(listedNames()).toEqual(['到账批']);
      expect(screen.getByTestId('batch-list-summary')).toHaveTextContent('1 个批次 · 合计 ¥400.00');
      expect(search().get('batch_status')).toBe('received');
    });

    test('period and basis filter by the chosen date and sync to the URL', async () => {
      const user = userEvent.setup();
      setup('/batches');
      await screen.findByTestId('batch-list-summary');
      await user.click(screen.getByRole('button', { name: '本月' }));
      expect(listedNames()).toEqual(['草稿批']);
      await user.click(screen.getByRole('combobox', { name: '日期口径' }));
      await user.click(await screen.findByRole('option', { name: '外发日期' }));
      await waitFor(() => expect(listedNames()).toEqual(['外发批']));
      expect(search().get('batch_period')).toBe('this_month');
      expect(search().get('batch_basis')).toBe('sent');
    });

    test('restores filters from the URL on load', async () => {
      setup('/batches?batch_period=custom&batch_start=2020-01-01&batch_end=2020-01-31');
      await screen.findByTestId('batch-list-summary');
      expect(listedNames()).toEqual(['外发批', '到账批']);
      expect(screen.getByRole('textbox', { name: '起始日期' })).toHaveValue('2020-01-01');
    });

    test('keeps showing a selected batch that is filtered out, with a hint', async () => {
      setup('/batches?id=2&batch_status=draft');
      expect(await screen.findByText('当前批次不在筛选结果中')).toBeInTheDocument();
      expect(listedNames()).toEqual(['草稿批']);
      expect(await screen.findByText('外发批', { selector: 'p' })).toBeInTheDocument();
      expect(search().get('id')).toBe('2');
    });

    test('selecting a batch keeps the filter params', async () => {
      const user = userEvent.setup();
      setup('/batches?batch_status=draft');
      await user.click(await screen.findByRole('listitem'));
      expect(search().get('id')).toBe('1');
      expect(search().get('batch_status')).toBe('draft');
    });
  });
});
