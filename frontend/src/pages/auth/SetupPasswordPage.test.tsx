import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import { AuthGate } from '../../components/auth/AuthGate';
import { AUTHENTICATED, NEEDS_LOGIN, NEEDS_SETUP, SAAS_AUTHENTICATED, SAAS_NEEDS_SETUP, authStatusRoute } from '../../test/authStatus';
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
    expect(await screen.findByText(/为管理员账户 admin 设置初始密码/)).toBeInTheDocument();
    expect(screen.getByText(/设置后可在「设置 → 用户管理」中添加其他用户/)).toBeInTheDocument();
    expect(screen.getByLabelText('用户名')).toHaveValue('admin');
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
        return { data: { authenticated: true, user: AUTHENTICATED.user } };
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

describe('SetupPasswordPage (多账套首个平台管理员)', () => {
  test('explains the platform admin account and offers an editable username', async () => {
    mockFetch({ 'GET /api/auth/status': SAAS_NEEDS_SETUP });
    renderGate();
    expect(await screen.findByRole('heading', { name: '设置平台管理员' })).toBeInTheDocument();
    expect(screen.getByText(/这是平台管理员账号，用于开通与管理各账套/)).toBeInTheDocument();
    expect(screen.getByText(/在那里开通账套并指定各账套的管理员/)).toBeInTheDocument();
    const username = screen.getByLabelText('用户名');
    expect(username).toHaveValue('admin');
    expect(username).not.toHaveAttribute('readonly');
  });

  test('keeps submit disabled until the username is valid', async () => {
    const user = userEvent.setup();
    mockFetch({ 'GET /api/auth/status': SAAS_NEEDS_SETUP });
    renderGate();
    const submit = await screen.findByRole('button', { name: '设置并进入' });
    await user.type(screen.getByLabelText('新密码'), 'Ledger-2026');
    await user.type(screen.getByLabelText('确认密码'), 'Ledger-2026');
    expect(submit).toBeEnabled();

    await user.clear(screen.getByLabelText('用户名'));
    await user.type(screen.getByLabelText('用户名'), '坏 账号');
    expect(screen.getByText('只能包含字母、数字、下划线、点、连字符')).toBeInTheDocument();
    expect(submit).toBeDisabled();
  });

  test('sends the chosen username and enters the app', async () => {
    const user = userEvent.setup();
    const status = authStatusRoute(SAAS_NEEDS_SETUP);
    const { calls } = mockFetch({
      'GET /api/auth/status': status.route,
      'POST /api/auth/setup': () => {
        status.set(SAAS_AUTHENTICATED);
        return { data: { authenticated: true, user: SAAS_AUTHENTICATED.user, tenant: { slug: 'platform', name: '平台运营' } } };
      },
    });
    renderGate();
    await user.clear(await screen.findByLabelText('用户名'));
    await user.type(screen.getByLabelText('用户名'), 'ops-boss');
    await user.type(screen.getByLabelText('新密码'), 'Ledger-2026');
    await user.type(screen.getByLabelText('确认密码'), 'Ledger-2026');
    await user.click(screen.getByRole('button', { name: '设置并进入' }));

    expect(await screen.findByText('应用内容')).toBeInTheDocument();
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ username: 'ops-boss', password: 'Ledger-2026' });
  });

  test('switches to login page when the platform admin already exists (409)', async () => {
    const user = userEvent.setup();
    const status = authStatusRoute(SAAS_NEEDS_SETUP);
    mockFetch({
      'GET /api/auth/status': status.route,
      'POST /api/auth/setup': () => {
        status.set(NEEDS_LOGIN);
        return { status: 409, error: '已创建过平台管理员，请直接登录' };
      },
    });
    renderGate();
    await user.type(await screen.findByLabelText('新密码'), 'Ledger-2026');
    await user.type(screen.getByLabelText('确认密码'), 'Ledger-2026');
    await user.click(screen.getByRole('button', { name: '设置并进入' }));

    expect(await screen.findByRole('button', { name: '登录' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('平台管理员已被创建过，请登录')).toBeInTheDocument());
  });
});
