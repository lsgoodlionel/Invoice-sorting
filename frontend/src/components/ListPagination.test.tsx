import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test, vi } from 'vitest';
import { renderWithProviders } from '../test/render';
import { ListPagination } from './ListPagination';

describe('ListPagination', () => {
  test('changes page size and supports direct page jump', async () => {
    const user = userEvent.setup();
    const onPageChange = vi.fn();
    const onPageSizeChange = vi.fn();
    renderWithProviders(<ListPagination total={95} page={1} pageSize={10} onPageChange={onPageChange} onPageSizeChange={onPageSizeChange} />);
    await user.click(screen.getByRole('combobox', { name: '每页显示' }));
    await user.click(await screen.findByRole('option', { name: '20 行' }));
    expect(onPageSizeChange).toHaveBeenCalledWith(20);
    await user.clear(screen.getByRole('textbox', { name: '跳转页码' }));
    await user.type(screen.getByRole('textbox', { name: '跳转页码' }), '7');
    await user.click(screen.getByRole('button', { name: '跳转' }));
    expect(onPageChange).toHaveBeenCalledWith(7);
  });

  test('all hides page navigation', () => {
    renderWithProviders(<ListPagination total={95} page={1} pageSize="all" onPageChange={vi.fn()} onPageSizeChange={vi.fn()} />);
    expect(screen.queryByRole('button', { name: '跳转' })).not.toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: '每页显示' })).toHaveValue('全部');
  });
});
