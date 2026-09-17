import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import { AuthGate } from '../../components/auth/AuthGate';
import { AUTHENTICATED, NEEDS_LOGIN, NEEDS_SETUP, authStatusRoute } from '../../test/authStatus';
import { mockFetch } from '../../test/fetchMock';
import { renderWithProviders } from '../../test/render';

const renderGate = () =>
  renderWithProviders(
    <AuthGate>
      <div>应用内容</div>
    </AuthGate>,
  );

describe('SetupPasswordPage', () => {
  test('shows guidance, security note and autocomplete attributes', async () => {
    mockFetch({ 'GET /api/auth/status': NEEDS_SETUP });
    renderGate();
    expect(await screen.findByText(/首次使用请设置登录密码/)).toBeInTheDocument();
    expect(screen.getByText('尚未设置密码前任何人打开此页面都可以设置，请尽快完成。')).toBeInTheDocument();
    expect(screen.getByLabelText('新密码')).toHaveAttribute('autocomplete', 'new-password');
    expect(screen.getByLabelText('确认密码')).toHaveAttribute('autocomplete', 'new-password');
  });

  test('disables submit for short or mismatched passwords', async () => {
    const user = userEvent.setup();
    mockFetch({ 'GET /api/auth/status': NEEDS_SETUP });
    renderGate();
    const submit = await screen.findByRole('button', { name: '设置并进入' });
    expect(submit).toBeDisabled();

    await user.type(screen.getByLabelText('新密码'), 'short');
    await user.type(screen.getByLabelText('确认密码'), 'short');
    expect(screen.getByText('密码至少 8 位')).toBeInTheDocument();
    expect(submit).toBeDisabled();

    await user.clear(screen.getByLabelText('新密码'));
    await user.type(screen.getByLabelText('新密码'), 'long-enough-1');
    expect(screen.getByText('两次输入的密码不一致')).toBeInTheDocument();
    expect(submit).toBeDisabled();
  });

  test('submits password and enters the app on success', async () => {
    const user = userEvent.setup();
    const status = authStatusRoute(NEEDS_SETUP);
    const { calls } = mockFetch({
      'GET /api/auth/status': status.route,
      'POST /api/auth/setup': () => {
        status.set(AUTHENTICATED);
        return { data: { authenticated: true } };
      },
    });
    renderGate();
    await user.type(await screen.findByLabelText('新密码'), 'Ledger-2026');
    await user.type(screen.getByLabelText('确认密码'), 'Ledger-2026');
    expect(screen.getByText(/强度/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '设置并进入' }));

    expect(await screen.findByText('应用内容')).toBeInTheDocument();
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ password: 'Ledger-2026' });
  });

  test('switches to login page when password was already set (409)', async () => {
    const user = userEvent.setup();
    const status = authStatusRoute(NEEDS_SETUP);
    mockFetch({
      'GET /api/auth/status': status.route,
      'POST /api/auth/setup': () => {
        status.set(NEEDS_LOGIN);
        return { status: 409, error: '已设置过初始密码，请直接登录' };
      },
    });
    renderGate();
    await user.type(await screen.findByLabelText('新密码'), 'Ledger-2026');
    await user.type(screen.getByLabelText('确认密码'), 'Ledger-2026');
    await user.click(screen.getByRole('button', { name: '设置并进入' }));

    expect(await screen.findByRole('button', { name: '登录' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('已被设置过，请登录')).toBeInTheDocument());
  });
});
