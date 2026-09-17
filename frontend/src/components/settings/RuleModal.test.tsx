import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import { mockFetch } from '../../test/fetchMock';
import { renderWithProviders } from '../../test/render';
import { RuleModal } from './RuleModal';

describe('RuleModal invoice exempt condition', () => {
  test('reads existing condition and saves the chosen filter', async () => {
    const user = userEvent.setup();
    const rule = { id: 7, category_id: null, attachment_kind: 'payment' as const, level: 'required' as const, condition: { invoice_exempt: true }, hint: '境外消费需附银行卡交易明细' };
    const { calls } = mockFetch({ 'GET /api/categories': [], 'PATCH /api/checklist-rules/7': rule });
    renderWithProviders(<RuleModal editing={rule} onClose={() => undefined} />);
    const dialog = await screen.findByRole('dialog');
    const select = dialog.querySelector('input[aria-label="免发票记录"]') as HTMLInputElement;
    expect(select).toHaveValue('仅免发票记录');

    await user.click(select);
    await user.click(await screen.findByRole('option', { name: '排除免发票记录' }));
    await user.click(within(dialog).getByRole('button', { name: '保存' }));
    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH')?.body).toMatchObject({ condition: { invoice_exempt: false } }));
  });
});
