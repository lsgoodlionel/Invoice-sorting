import { screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import { MEMBER_USER } from '../../test/authStatus';
import { renderWithProviders } from '../../test/render';
import { NavUserFooter } from './NavUserFooter';

describe('NavUserFooter', () => {
  test('shows admin label and logout', () => {
    renderWithProviders(<NavUserFooter />);
    expect(screen.getByTestId('nav-current-user')).toHaveTextContent('管理员（管理员）');
    expect(screen.getByRole('button', { name: '退出登录' })).toBeInTheDocument();
  });

  test('shows member name without role suffix', () => {
    renderWithProviders(<NavUserFooter />, { currentUser: { user: MEMBER_USER, isAdmin: false, authEnabled: true } });
    expect(screen.getByTestId('nav-current-user')).toHaveTextContent(/^张三$/);
  });

  test('hidden when auth is disabled', () => {
    renderWithProviders(<NavUserFooter />, { currentUser: { user: null, isAdmin: true, authEnabled: false } });
    expect(screen.queryByRole('button', { name: '退出登录' })).not.toBeInTheDocument();
  });
});
