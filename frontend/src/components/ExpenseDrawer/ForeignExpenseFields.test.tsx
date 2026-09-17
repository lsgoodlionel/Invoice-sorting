import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import type { ExpenseDetail } from '../../api/types';
import { mockFetch, type RecordedCall } from '../../test/fetchMock';
import { makeAttachment, makeDetail, makeEvidence } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { ExpenseDrawer } from './ExpenseDrawer';

function setup(detail: ExpenseDetail) {
  return mockFetch({
    'GET /api/expenses/1': detail,
    'GET /api/categories': [],
    'GET /api/projects': [],
    'PATCH /api/expenses/1': (call: RecordedCall) => ({ data: { ...detail, ...(call.body as object) } }),
  });
}

const patches = (calls: RecordedCall[]) => calls.filter((c) => c.method === 'PATCH').map((c) => c.body);

describe('ExpenseDrawer invoice exempt and currency', () => {
  test('toggling invoice exempt and choosing a foreign currency saves via PATCH', async () => {
    const user = userEvent.setup();
    const { calls } = setup(makeDetail({ id: 1 }));
    renderWithProviders(<ExpenseDrawer expenseId={1} onClose={() => undefined} />);
    const exempt = await screen.findByRole('switch', { name: '免发票（境外消费）' });
    expect(screen.queryByLabelText('原币金额')).not.toBeInTheDocument();
    expect(screen.getByText('已开票')).toBeInTheDocument();

    await user.click(exempt);
    await waitFor(() => expect(patches(calls)).toEqual([{ invoice_exempt: true }]));

    await user.click(document.querySelector('input[aria-label="币种"]') as HTMLInputElement);
    await user.click(await screen.findByRole('option', { name: '美元 USD' }));
    await waitFor(() => expect(patches(calls)).toContainEqual({ currency: 'USD' }));
  });

  test('exempt record shows 已收凭证 step, commits original amount on blur and clears it for CNY', async () => {
    const user = userEvent.setup();
    const detail = makeDetail({
      id: 1,
      invoice_exempt: true,
      currency: 'USD',
      original_amount_cents: 2000,
      attachments: [makeAttachment({ id: 31, kind: 'order', invoice: null, original_name: 'claude.png', evidence: makeEvidence() })],
    });
    const { calls } = setup(detail);
    renderWithProviders(<ExpenseDrawer expenseId={1} onClose={() => undefined} />);
    const original = await screen.findByLabelText('原币金额');
    expect(within(screen.getByRole('list', { name: '状态进度' })).getByText('已收凭证')).toBeInTheDocument();
    expect(screen.getByTestId('evidence-31')).toHaveTextContent('订单 · 2026-06-28 · US$20.00 · 订单号 MSD3K2L9QX1234');

    await user.clear(original);
    await user.type(original, '21');
    fireEvent.blur(original);
    await waitFor(() => expect(patches(calls)).toEqual([{ original_amount_cents: 2100 }]));

    await user.click(document.querySelector('input[aria-label="币种"]') as HTMLInputElement);
    await user.click(await screen.findByRole('option', { name: '人民币 CNY' }));
    await waitFor(() => expect(patches(calls)).toContainEqual({ currency: 'CNY', original_amount_cents: null }));
  });
});
