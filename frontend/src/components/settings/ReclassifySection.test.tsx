import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import type { ReclassifyItem } from '../../api/hooks/reclassify';
import { mockFetch } from '../../test/fetchMock';
import { renderWithProviders } from '../../test/render';
import { ReclassifySection } from './ReclassifySection';

const books: ReclassifyItem = {
  expense_id: 11,
  spent_on: '2025-08-15',
  merchant: '上海圆迈贸易有限公司',
  summary: '系统之美',
  amount_cents: 5971,
  status: 'invoiced',
  current_category_id: 7,
  current_category_name: '印刷快递',
  suggested_category_id: 11,
  suggested_category_name: '图书',
  basis: '发票税收分类：印刷品',
};
const device: ReclassifyItem = {
  ...books,
  expense_id: 22,
  merchant: '北京京东工业品贸易有限公司',
  summary: 'UPS 不间断电源',
  current_category_name: '易耗品',
  suggested_category_id: 4,
  suggested_category_name: '设备',
  basis: '文件名分类词',
};

describe('ReclassifySection', () => {
  test('checks, previews suggestions with basis and applies the selected ones', async () => {
    const user = userEvent.setup();
    const { calls } = mockFetch({
      'GET /api/reclassify/preview': [books, device],
      'POST /api/reclassify/apply': { updated: 1 },
    });
    renderWithProviders(<ReclassifySection />);

    await user.click(screen.getByRole('button', { name: '检查分类' }));
    const row = await screen.findByTestId('reclassify-row-11');
    expect(within(row).getByText('印刷快递 → 图书')).toBeInTheDocument();
    expect(within(row).getByText('发票税收分类：印刷品')).toBeInTheDocument();

    await user.click(within(screen.getByTestId('reclassify-row-22')).getByRole('checkbox'));
    await user.click(screen.getByRole('button', { name: '改正所选 1 条' }));

    await waitFor(() =>
      expect(calls.find((call) => call.url === '/api/reclassify/apply')?.body).toEqual({
        changes: [{ expense_id: 11, category_id: 11 }],
      }),
    );
    expect(await screen.findByText('已改正 1 条记录的分类')).toBeInTheDocument();
  });

  test('includes sent records only when requested', async () => {
    const user = userEvent.setup();
    const { calls } = mockFetch({ 'GET /api/reclassify/preview': [] });
    renderWithProviders(<ReclassifySection />);

    await user.click(screen.getByRole('checkbox', { name: '包含已外发、已报销的记录' }));
    await user.click(screen.getByRole('button', { name: '检查分类' }));

    expect(await screen.findByText('所有记录的分类都与最新规则一致')).toBeInTheDocument();
    expect(calls.find((call) => call.url.startsWith('/api/reclassify/preview'))?.url).toBe(
      '/api/reclassify/preview?include_sent=true',
    );
  });
});
