import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import type { ImportConfirmRow, ImportSession } from '../api/types';
import { mockFetch } from '../test/fetchMock';
import { makeImportRow } from '../test/fixtures';
import { renderWithProviders } from '../test/render';
import { CollectPage } from './CollectPage';

const session: ImportSession = {
  session_id: 'sess-1',
  rows: [
    makeImportRow({ row_id: 'r1', warnings: ['购方名称与设置不一致'] }),
    makeImportRow({
      row_id: 'r2',
      suggested: { spent_on: '2026-09-12', amount_cents: 29800, merchant: '腾讯云', summary: '会议会员', category_id: 1 },
      match: { expense_id: 42, merchant: '腾讯云', amount_cents: 29800, spent_on: '2026-09-11' },
    }),
  ],
  attachments: [],
  duplicates: [{ original_name: 'dup.pdf', existing_expense_id: 7, reason: '发票号码重复' }],
  errors: [{ original_name: 'bad.ofd', error: '无法解析' }],
  notices: [],
};

describe('CollectPage', () => {
  test('edits category in the confirm table and submits the right payload', async () => {
    const user = userEvent.setup();
    const { calls } = mockFetch({
      'GET /api/settings': { buyer_name: '', buyer_tax_id: '', overdue_days: 30, data_dir: '/d', inbox_dir: '/d/收件箱' },
      'GET /api/categories': [
        { id: 1, name: '办公用品', color: '#333', keywords: [], route_hint: '', sort: 1, archived: false },
        { id: 2, name: '软件服务', color: '#555', keywords: [], route_hint: '', sort: 2, archived: false },
      ],
      'GET /api/attachments/unassigned': [],
      'POST /api/imports': session,
      'POST /api/imports/sess-1/confirm': { created: [100], attached: [42], skipped: 0 },
    });
    renderWithProviders(<CollectPage />, { route: '/collect' });
    expect(await screen.findByText(/\/d\/收件箱/)).toBeInTheDocument();

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, [new File(['%PDF'], 'a.pdf', { type: 'application/pdf' })]);

    const row2 = await screen.findByTestId('import-row-r2');
    expect(screen.getByTestId('import-row-r1')).toHaveClass('row-warning');
    expect(screen.getByText('dup.pdf')).toBeInTheDocument();
    expect(screen.getByText('bad.ofd')).toBeInTheDocument();
    expect(within(row2).getByDisplayValue(/挂到已支出 #42/)).toBeInTheDocument();

    await user.click(row2.querySelector('input[aria-label="分类"]') as HTMLInputElement);
    await user.click(await screen.findByRole('option', { name: '软件服务' }));

    await user.click(screen.getByRole('button', { name: '全部确认' }));
    await waitFor(() => expect(calls.some((c) => c.url === '/api/imports/sess-1/confirm')).toBe(true));
    const body = calls.find((c) => c.url === '/api/imports/sess-1/confirm')?.body as { rows: ImportConfirmRow[] };
    expect(body.rows).toEqual([
      { row_id: 'r1', action: 'create', spent_on: '2026-09-15', amount_cents: 96000, merchant: '京东某店', summary: '鼠标', category_id: 1 },
      { row_id: 'r2', action: 'attach', expense_id: 42, spent_on: '2026-09-12', amount_cents: 29800, merchant: '腾讯云', summary: '会议会员', category_id: 2 },
    ]);
    await waitFor(() => expect(screen.queryByTestId('import-row-r1')).not.toBeInTheDocument());
  });
});
