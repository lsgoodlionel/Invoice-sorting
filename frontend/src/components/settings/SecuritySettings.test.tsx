import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import { AUTHENTICATED, AUTH_DISABLED } from '../../test/authStatus';
import { mockFetch } from '../../test/fetchMock';
import { renderWithProviders } from '../../test/render';
import { SecuritySettings } from './SecuritySettings';

async function fillPasswords(user: ReturnType<typeof userEvent.setup>, current: string, next: string, confirm = next) {
  await user.type(await screen.findByLabelText('当前密码'), current);
  await user.type(screen.getByLabelText('新密码'), next);
  await user.type(screen.getByLabelText('确认新密码'), confirm);
}

describe('SecuritySettings', () => {
  test('changes password with contract payload and shows success message', async () => {
    const user = userEvent.setup();
    const { calls } = mockFetch({ 'GET /api/auth/status': AUTHENTICATED, 'POST /api/auth/password': null });
    renderWithProviders(<SecuritySettings />);
    await fillPasswords(user, 'old-password', 'new-password-1');
    expect(screen.getByLabelText('当前密码')).toHaveAttribute('autocomplete', 'current-password');
    expect(screen.getByLabelText('新密码')).toHaveAttribute('autocomplete', 'new-password');
    await user.click(screen.getByRole('button', { name: '修改密码' }));

    expect(await screen.findByText('密码已修改，其他设备需重新登录')).toBeInTheDocument();
    expect(calls.find((c) => c.url === '/api/auth/password')?.body).toEqual({
      current_password: 'old-password',
      new_password: 'new-password-1',
    });
    await waitFor(() => expect(screen.getByLabelText('当前密码')).toHaveValue(''));
  });

  test('disables submit until new passwords are valid and match', async () => {
    const user = userEvent.setup();
    mockFetch({ 'GET /api/auth/status': AUTHENTICATED });
    renderWithProviders(<SecuritySettings />);
    await fillPasswords(user, 'old-password', 'new-password-1', 'new-password-2');
    expect(screen.getByRole('button', { name: '修改密码' })).toBeDisabled();
  });

  test('shows wrong current password error inline', async () => {
    const user = userEvent.setup();
    mockFetch({
      'GET /api/auth/status': AUTHENTICATED,
      'POST /api/auth/password': () => ({ status: 400, error: '当前密码错误' }),
    });
    renderWithProviders(<SecuritySettings />);
    await fillPasswords(user, 'bad-password', 'new-password-1');
    await user.click(screen.getByRole('button', { name: '修改密码' }));
    expect(await screen.findByText('当前密码错误')).toBeInTheDocument();
  });

  test('logs out after confirmation', async () => {
    const user = userEvent.setup();
    const { calls } = mockFetch({ 'GET /api/auth/status': AUTHENTICATED, 'POST /api/auth/logout': null });
    renderWithProviders(<SecuritySettings />);
    await user.click(await screen.findByRole('button', { name: '退出登录' }));
    expect(calls.some((c) => c.url === '/api/auth/logout')).toBe(false);
    await user.click(await screen.findByRole('button', { name: '退出' }));
    await waitFor(() => expect(calls.some((c) => c.url === '/api/auth/logout')).toBe(true));
  });

  test('explains auth is disabled and hides the form', async () => {
    mockFetch({ 'GET /api/auth/status': AUTH_DISABLED });
    renderWithProviders(<SecuritySettings />);
    expect(await screen.findByText(/当前未启用登录认证/)).toBeInTheDocument();
    expect(screen.queryByLabelText('当前密码')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '退出登录' })).not.toBeInTheDocument();
  });
});
