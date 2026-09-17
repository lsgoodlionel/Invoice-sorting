import { screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import { renderWithProviders } from '../test/render';
import { StatusBadge } from './StatusBadge';

describe('StatusBadge', () => {
  test('always shows the text label alongside color', () => {
    renderWithProviders(<StatusBadge status="complete" />);
    const badge = screen.getByText('凭证齐全');
    expect(badge.closest('[data-status]')).toHaveAttribute('data-status', 'complete');
    expect(screen.queryByText('手动')).not.toBeInTheDocument();
  });

  test('shows manual marker', () => {
    renderWithProviders(<StatusBadge status="sent" manual />);
    expect(screen.getByText('已外发')).toBeInTheDocument();
    expect(screen.getByText('手动')).toBeInTheDocument();
  });

  test('void is struck through', () => {
    renderWithProviders(<StatusBadge status="void" />);
    expect(screen.getByText('不报销/作废').closest('.status-void')).not.toBeNull();
  });
});
