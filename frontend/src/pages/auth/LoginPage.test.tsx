import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, test } from 'vitest';
import { AuthGate } from '../../components/auth/AuthGate';
import { REMEMBERED_USERNAME_KEY } from '../../lib/rememberedUsername';
import { createQueryClient } from '../../queryClient';
import { AUTHENTICATED_MEMBER, NEEDS_LOGIN, authStatusRoute } from '../../test/authStatus';
import { mockFetch } from '../../test/fetchMock';
import { renderWithProviders } from '../../test/render';

const renderGate = () =>
  renderWithProviders(
    <AuthGate>
      <div>应用内容</div>
    </AuthGate>,
    { client: createQueryClient() },
  );

afterEach(() => window.localStorage.clear());

describe('LoginPage', () => {
  test('defaults username to admin, focuses password and shows reset guidance', async () => {
    mockFetch({ 'GET /api/auth/status': NEEDS_LOGIN });
    renderGate();
    const password = await screen.findByLabelText('密码');
    const username = screen.getByLabelText('用户名');
    expect(username).toHaveValue('admin');
    expect(username).toHaveAttribute('autocomplete', 'username');
    expect(password).toHaveFocus();
    expect(password).toHaveAttribute('autocomplete', 'current-password');
    expect(screen.getByRole('heading', { name: '登录' })).toBeInTheDocument();
    expect(screen.getByText('忘记密码？请联系管理员重置')).toBeInTheDocument();
    expect(screen.queryByText(/reset-password/)).not.toBeInTheDocument();
  });

  test('prefills the last successfully used username', async () => {
    window.localStorage.setItem(REMEMBERED_USERNAME_KEY, 'zhangsan');
    mockFetch({ 'GET /api/auth/status': NEEDS_LOGIN });
    renderGate();
    expect(await screen.findByLabelText('用户名')).toHaveValue('zhangsan');
  });

  test('shows backend error once and marks inputs invalid', async () => {
    const user = userEvent.setup();
    mockFetch({
      'GET /api/auth/status': NEEDS_LOGIN,
      'POST /api/auth/login': () => ({ status: 401, error: '用户名或密码错误' }),
    });
    renderGate();
    await user.type(await screen.findByLabelText('密码'), 'wrong-password{Enter}');
    expect(await screen.findByText('用户名或密码错误')).toBeInTheDocument();
    expect(screen.getAllByText('用户名或密码错误')).toHaveLength(1);
    expect(screen.getByLabelText('密码')).toHaveAttribute('aria-invalid', 'true');
  });

  test('shows rate limit message verbatim (429)', async () => {
    const user = userEvent.setup();
    mockFetch({
      'GET /api/auth/status': NEEDS_LOGIN,
      'POST /api/auth/login': () => ({ status: 429, error: '尝试次数过多，请 12 分钟后再试' }),
    });
    renderGate();
    await user.type(await screen.findByLabelText('密码'), 'some-password');
    await user.click(screen.getByRole('button', { name: '登录' }));
    expect(await screen.findByText('尝试次数过多，请 12 分钟后再试')).toBeInTheDocument();
  });

  test('disables submit without username', async () => {
    const user = userEvent.setup();
    mockFetch({ 'GET /api/auth/status': NEEDS_LOGIN });
    renderGate();
    await user.type(await screen.findByLabelText('密码'), 'some-password');
    await user.clear(screen.getByLabelText('用户名'));
    expect(screen.getByRole('button', { name: '登录' })).toBeDisabled();
  });

  test('sends username and password, remembers username and enters the app', async () => {
    const user = userEvent.setup();
    const status = authStatusRoute(NEEDS_LOGIN);
    const { calls } = mockFetch({
      'GET /api/auth/status': status.route,
      'POST /api/auth/login': () => {
        status.set(AUTHENTICATED_MEMBER);
        return { data: { authenticated: true, user: AUTHENTICATED_MEMBER.user } };
      },
    });
    renderGate();
    const username = await screen.findByLabelText('用户名');
    await user.clear(username);
    await user.type(username, ' zhangsan ');
    await user.type(screen.getByLabelText('密码'), 'correct-password');
    await user.click(screen.getByRole('button', { name: '登录' }));

    expect(await screen.findByText('应用内容')).toBeInTheDocument();
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ username: 'zhangsan', password: 'correct-password' });
    expect(window.localStorage.getItem(REMEMBERED_USERNAME_KEY)).toBe('zhangsan');
    await waitFor(() => expect(calls.filter((c) => c.url === '/api/auth/status').length).toBeGreaterThanOrEqual(2));
  });
});
