import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import type { User } from '../../../api/types';
import { AUTHENTICATED, SAAS_AUTHENTICATED } from '../../../test/authStatus';
import { mockFetch } from '../../../test/fetchMock';
import { makeUser } from '../../../test/fixtures';
import { renderWithProviders } from '../../../test/render';
import { UserManager } from './UserManager';

const USERS: User[] = [makeUser({ id: 1, username: 'admin', display_name: '管理员', role: 'admin' })];

const INVITE = {
  id: 1,
  code: 'abc123XYZ',
  role: 'member',
  expires_on: '2026-09-27',
  is_used: false,
  used_at: null,
  created_at: '2026-09-20T10:00:00+08:00',
};

type Routes = Record<string, unknown>;

function setup(extra: Routes = {}) {
  const result = mockFetch({ 'GET /api/users': USERS, ...extra });
  renderWithProviders(<UserManager />);
  return result;
}

describe('邀请码入口', () => {
  test('单租户部署的用户管理里没有邀请码按钮', async () => {
    setup({ 'GET /api/auth/status': AUTHENTICATED });
    expect(await screen.findByRole('button', { name: '添加用户' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '邀请码' })).not.toBeInTheDocument();
  });

  test('多租户部署生成邀请码并展示给管理员', async () => {
    const user = userEvent.setup();
    const { calls } = setup({
      'GET /api/auth/status': SAAS_AUTHENTICATED,
      'POST /api/invites': INVITE,
    });

    await user.click(await screen.findByRole('button', { name: '邀请码' }));
    await user.click(await screen.findByRole('button', { name: '生成邀请码' }));

    expect(await screen.findByTestId('invite-code')).toHaveTextContent('abc123XYZ');
    expect(screen.getByText(/2026-09-27 前有效/)).toBeInTheDocument();
    await waitFor(() => {
      const call = calls.find((item) => item.url === '/api/invites');
      expect(call?.body).toEqual({ role: 'member' });
    });
  });

  test('可以生成管理员邀请码', async () => {
    const user = userEvent.setup();
    const { calls } = setup({
      'GET /api/auth/status': SAAS_AUTHENTICATED,
      'POST /api/invites': { ...INVITE, role: 'admin' },
    });

    await user.click(await screen.findByRole('button', { name: '邀请码' }));
    await user.click(await screen.findByRole('radio', { name: '管理员' }));
    await user.click(screen.getByRole('button', { name: '生成邀请码' }));

    await waitFor(() => {
      const call = calls.find((item) => item.url === '/api/invites');
      expect(call?.body).toEqual({ role: 'admin' });
    });
  });
});
