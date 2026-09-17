import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test, vi } from 'vitest';
import { makeAttachment, makeChecklistItem } from '../test/fixtures';
import { renderWithProviders } from '../test/render';
import { ChecklistPanel } from './ChecklistPanel';

const items = [
  makeChecklistItem({ id: 1, attachment_kind: 'invoice', kind_label: '发票', state: 'present' }),
  makeChecklistItem({ id: 2, attachment_kind: 'order', kind_label: '订单明细', state: 'missing', hint: '网购需附订单' }),
  makeChecklistItem({ id: 3, attachment_kind: 'acceptance', kind_label: '验收单', state: 'not_needed', reason: '无需验收' }),
];

function renderPanel() {
  const onSetState = vi.fn();
  const onUpload = vi.fn();
  renderWithProviders(
    <ChecklistPanel items={items} attachments={[makeAttachment({ original_name: '发票_888.pdf' })]} onSetState={onSetState} onUpload={onUpload} />,
  );
  return { onSetState, onUpload };
}

describe('ChecklistPanel', () => {
  test('renders present, missing and not-needed rows', () => {
    renderPanel();
    expect(within(screen.getByTestId('checklist-1')).getByText('发票_888.pdf')).toBeInTheDocument();
    const missing = screen.getByTestId('checklist-2');
    expect(within(missing).getByLabelText('缺少')).toBeInTheDocument();
    expect(within(missing).getByText('网购需附订单')).toBeInTheDocument();
    expect(within(missing).getByText('拖入或点击选择')).toBeInTheDocument();
    expect(within(screen.getByTestId('checklist-3')).getByText('原因：无需验收')).toBeInTheDocument();
  });

  test('marks a missing item as not needed with a reason', async () => {
    const user = userEvent.setup();
    const { onSetState } = renderPanel();
    await user.click(within(screen.getByTestId('checklist-2')).getByRole('button', { name: '不需要' }));
    await user.type(await screen.findByLabelText('原因（可选）'), '线下购买');
    await user.click(screen.getByRole('button', { name: '确认不需要' }));
    expect(onSetState).toHaveBeenCalledWith(2, 'not_needed', '线下购买');
  });

  test('restores a not-needed item', async () => {
    const user = userEvent.setup();
    const { onSetState } = renderPanel();
    await user.click(within(screen.getByTestId('checklist-3')).getByRole('button', { name: '恢复' }));
    expect(onSetState).toHaveBeenCalledWith(3, 'missing');
  });

  test('uploads files for the missing kind', async () => {
    const user = userEvent.setup();
    const { onUpload } = renderPanel();
    const input = screen.getByTestId('checklist-2').querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['x'], '订单.png', { type: 'image/png' });
    await user.upload(input, file);
    await vi.waitFor(() => expect(onUpload).toHaveBeenCalledWith('order', [file]));
  });

  test('shows hint when there are no checklist items', () => {
    renderWithProviders(<ChecklistPanel items={[]} attachments={[]} onSetState={vi.fn()} onUpload={vi.fn()} />);
    expect(screen.getByText('该分类没有凭证要求。')).toBeInTheDocument();
  });
});
