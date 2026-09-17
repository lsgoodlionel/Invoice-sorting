import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import { AuthGate } from '../../components/auth/AuthGate';
import { createQueryClient } from '../../queryClient';
import { AUTHENTICATED, NEEDS_LOGIN, authStatusRoute } from '../../test/authStatus';
import { mockFetch } from '../../test/fetchMock';
import { renderWithProviders } from '../../test/render';

const renderGate = () =>
  renderWithProviders(
    <AuthGate>
      <div>应用内容</div>
    </AuthGate>,
    { client: createQueryClient() },
  );

describe('LoginPage', () => {
  test('focuses password input and shows reset command hints', async () => {
    mockFetch({ 'GET /api/auth/status': NEEDS_LOGIN });
    renderGate();
    const input = await screen.findByLabelText('密码');
    expect(input).toHaveFocus();
    expect(input).toHaveAttribute('autocomplete', 'current-password');
    expect(
      screen.getByText(
        'sudo -u invoice env INVOICE_SORTING_DATA_DIR=/var/lib/invoice-sorting /opt/invoice-sorting/app/backend/.venv/bin/invoice-sorting reset-password',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('backend/.venv/bin/invoice-sorting reset-password')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /复制/ })).toHaveLength(2);
  });

  test('shows wrong password error under the input without a global notification', async () => {
    const user = userEvent.setup();
    mockFetch({
      'GET /api/auth/status': NEEDS_LOGIN,
      'POST /api/auth/login': () => ({ status: 401, error: '密码错误' }),
    });
    renderGate();
    await user.type(await screen.findByLabelText('密码'), 'wrong-password{Enter}');
    expect(await screen.findByText('密码错误')).toBeInTheDocument();
    expect(screen.getAllByText('密码错误')).toHaveLength(1);
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
    expect(screen.getAllByText('尝试次数过多，请 12 分钟后再试')).toHaveLength(1);
  });

  test('sends password and refreshes status on success', async () => {
    const user = userEvent.setup();
    const status = authStatusRoute(NEEDS_LOGIN);
    const { calls } = mockFetch({
      'GET /api/auth/status': status.route,
      'POST /api/auth/login': () => {
        status.set(AUTHENTICATED);
        return { data: { authenticated: true } };
      },
    });
    renderGate();
    await user.type(await screen.findByLabelText('密码'), 'correct-password');
    await user.click(screen.getByRole('button', { name: '登录' }));
    expect(await screen.findByText('应用内容')).toBeInTheDocument();
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ password: 'correct-password' });
    await waitFor(() => expect(calls.filter((c) => c.url === '/api/auth/status').length).toBeGreaterThanOrEqual(2));
  });
});
