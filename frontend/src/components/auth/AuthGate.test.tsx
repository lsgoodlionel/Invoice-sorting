import { useQuery } from '@tanstack/react-query';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router';
import { describe, expect, test, vi } from 'vitest';
import { api } from '../../api/client';
import { createQueryClient } from '../../queryClient';
import { AUTHENTICATED, AUTHENTICATED_MEMBER, AUTH_DISABLED, NEEDS_LOGIN, NEEDS_SETUP, authStatusRoute } from '../../test/authStatus';
import { mockFetch } from '../../test/fetchMock';
import { renderWithProviders } from '../../test/render';
import { AuthGate } from './AuthGate';
import { useCurrentUser } from './CurrentUserContext';

const renderGate = (route = '/') =>
  renderWithProviders(
    <AuthGate>
      <div>应用内容</div>
    </AuthGate>,
    { route },
  );

describe('AuthGate states', () => {
  test('shows brand loading state while status is pending', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => undefined)));
    renderGate();
    expect(screen.getByRole('status', { name: '正在检查登录状态' })).toBeInTheDocument();
    expect(screen.queryByText('应用内容')).not.toBeInTheDocument();
  });

  test('renders the app when authenticated', async () => {
    mockFetch({ 'GET /api/auth/status': AUTHENTICATED });
    renderGate();
    expect(await screen.findByText('应用内容')).toBeInTheDocument();
  });

  test('renders the app when auth is disabled', async () => {
    mockFetch({ 'GET /api/auth/status': AUTH_DISABLED });
    renderGate();
    expect(await screen.findByText('应用内容')).toBeInTheDocument();
  });

  test('renders setup page when no password has been set', async () => {
    mockFetch({ 'GET /api/auth/status': NEEDS_SETUP });
    renderGate();
    expect(await screen.findByRole('heading', { name: '欢迎使用发票账本' })).toBeInTheDocument();
    expect(screen.queryByText('应用内容')).not.toBeInTheDocument();
  });

  test('renders login page when password is set but not authenticated', async () => {
    mockFetch({ 'GET /api/auth/status': NEEDS_LOGIN });
    renderGate();
    expect(await screen.findByRole('button', { name: '登录' })).toBeInTheDocument();
    expect(screen.queryByText('应用内容')).not.toBeInTheDocument();
  });

  test('shows error with retry when status request fails', async () => {
    const user = userEvent.setup();
    let failing = true;
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        if (failing) throw new TypeError('network');
        return new Response(JSON.stringify({ ok: true, data: AUTHENTICATED, error: null }), { status: 200 });
      }),
    );
    renderGate();
    expect(await screen.findByText('无法连接本地服务，请确认后端已启动')).toBeInTheDocument();
    failing = false;
    await user.click(screen.getByRole('button', { name: '重试' }));
    expect(await screen.findByText('应用内容')).toBeInTheDocument();
  });
});

function ProtectedProbe() {
  const { data } = useQuery({ queryKey: ['probe'], queryFn: () => api.get<string>('/expenses') });
  return <div>应用内容{data}</div>;
}

describe('global 401 handling', () => {
  test('returns to login page after a protected request 401 without error notification', async () => {
    const status = authStatusRoute(AUTHENTICATED);
    mockFetch({
      'GET /api/auth/status': status.route,
      'GET /api/expenses': () => {
        status.set(NEEDS_LOGIN);
        return { status: 401, error: '请先登录' };
      },
    });
    renderWithProviders(
      <AuthGate>
        <ProtectedProbe />
      </AuthGate>,
      { client: createQueryClient() },
    );
    expect(await screen.findByRole('button', { name: '登录' })).toBeInTheDocument();
    expect(screen.queryByText('应用内容')).not.toBeInTheDocument();
    expect(screen.queryByText('请先登录')).not.toBeInTheDocument();
    expect(screen.queryByText('加载失败')).not.toBeInTheDocument();
  });

  test('login keeps the current route', async () => {
    const user = userEvent.setup();
    const status = authStatusRoute(NEEDS_LOGIN);
    mockFetch({
      'GET /api/auth/status': status.route,
      'POST /api/auth/login': () => {
        status.set(AUTHENTICATED);
        return { data: { authenticated: true, user: AUTHENTICATED.user } };
      },
    });
    renderWithProviders(
      <AuthGate>
        <Routes>
          <Route path="/batches" element={<div>批次页</div>} />
          <Route path="*" element={<div>其他页</div>} />
        </Routes>
      </AuthGate>,
      { route: '/batches' },
    );
    await user.type(await screen.findByLabelText('密码'), 'correct-password{Enter}');
    await waitFor(() => expect(screen.getByText('批次页')).toBeInTheDocument());
  });
});

function CurrentUserProbe() {
  const { user, isAdmin, authEnabled } = useCurrentUser();
  return <div>{`用户:${user?.display_name ?? '无'} 管理员:${isAdmin} 认证:${authEnabled}`}</div>;
}

describe('current user context', () => {
  const renderProbe = () =>
    renderWithProviders(
      <AuthGate>
        <CurrentUserProbe />
      </AuthGate>,
    );

  test('provides admin user', async () => {
    mockFetch({ 'GET /api/auth/status': AUTHENTICATED });
    renderProbe();
    expect(await screen.findByText('用户:管理员 管理员:true 认证:true')).toBeInTheDocument();
  });

  test('provides member user as non-admin', async () => {
    mockFetch({ 'GET /api/auth/status': AUTHENTICATED_MEMBER });
    renderProbe();
    expect(await screen.findByText('用户:张三 管理员:false 认证:true')).toBeInTheDocument();
  });

  test('treats everyone as admin when auth is disabled', async () => {
    mockFetch({ 'GET /api/auth/status': AUTH_DISABLED });
    renderProbe();
    expect(await screen.findByText('用户:无 管理员:true 认证:false')).toBeInTheDocument();
  });
});
