import { screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import { makeStatusEvent } from '../../test/fixtures';
import { renderWithProviders } from '../../test/render';
import { TimelineSection } from './TimelineSection';

describe('TimelineSection actor', () => {
  test('shows actor, system for automatic changes without actor', () => {
    renderWithProviders(
      <TimelineSection
        events={[
          makeStatusEvent({ id: 1, to_status: 'spent', is_manual: false, actor: { id: 2, display_name: '张三' } }),
          makeStatusEvent({ id: 2, from_status: 'spent', to_status: 'invoiced', is_manual: false, actor: null }),
          makeStatusEvent({ id: 3, from_status: 'invoiced', to_status: 'void', is_manual: true, actor: { id: 1, display_name: '管理员' } }),
          makeStatusEvent({ id: 4, from_status: 'void', to_status: 'spent', is_manual: true, actor: null }),
        ]}
      />,
    );
    expect(screen.getByText('（自动 · 张三）')).toBeInTheDocument();
    expect(screen.getByText('（自动 · 系统）')).toBeInTheDocument();
    expect(screen.getByText('（手动 · 管理员）')).toBeInTheDocument();
    expect(screen.getByText('（手动）')).toBeInTheDocument();
  });
});
