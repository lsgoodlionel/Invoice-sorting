import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import { AUTHENTICATED, SAAS_AUTHENTICATED } from '../test/authStatus';
import { mockFetch } from '../test/fetchMock';
import { UNCONFIGURED_MAIL, makeMailSettings } from '../test/mailFixtures';
import { OVERVIEW, makeTenantPage } from '../test/platformFixtures';
import { ADMIN_CONTEXT, renderWithProviders } from '../test/render';
import { makeApplication, makeApplicationPage } from '../test/signupFixtures';
import { PlatformPage } from './PlatformPage';

type Routes = Record<string, unknown>;

const MEMBER_CONTEXT = { user: null, isAdmin: false, authEnabled: true };

function setup(routes: Routes, currentUser = ADMIN_CONTEXT) {
  const result = mockFetch({
    'GET /api/auth/status': SAAS_AUTHENTICATED,
    'GET /api/platform/overview': OVERVIEW,
    'GET /api/platform/tenants': makeTenantPage([]),
    'GET /api/platform/plans': [],
    'GET /api/platform/applications': makeApplicationPage([]),
    ...routes,
  });
  renderWithProviders(<PlatformPage />, { currentUser });
  return result;
}

describe('平台页面的可见性', () => {
  test('平台管理员能看到概览与账套页签', async () => {
    setup({});

    expect(await screen.findByTestId('platform-overview')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '账套' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '平台运营' })).toBeInTheDocument();
  });

  test('概览显示账套、账号与用量合计', async () => {
    setup({});

    const overview = await screen.findByTestId('platform-overview');
    expect(overview).toHaveTextContent('3.0 MB');
    expect(overview).toHaveTextContent('12');
  });

  test('租户管理员（探测 403）被挡在外面', async () => {
    const { calls } = setup({ 'GET /api/platform/overview': () => ({ status: 403, error: '需要平台管理员权限' }) });

    await waitFor(() => expect(screen.queryByRole('heading', { name: '平台运营' })).not.toBeInTheDocument());
    expect(calls.some((call) => call.url === '/api/platform/tenants')).toBe(false);
  });

  test('普通成员不会发起任何平台请求', async () => {
    const { calls } = setup({}, MEMBER_CONTEXT);

    await waitFor(() => expect(screen.queryByRole('heading', { name: '平台运营' })).not.toBeInTheDocument());
    expect(screen.queryByRole('tab', { name: /申请/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: '推荐' })).not.toBeInTheDocument();
    expect(calls.some((call) => call.url.startsWith('/api/platform'))).toBe(false);
  });

  test('单账套部署没有平台概念：不探测也不显示', async () => {
    const { calls } = setup({ 'GET /api/auth/status': AUTHENTICATED });

    await waitFor(() => expect(screen.queryByRole('heading', { name: '平台运营' })).not.toBeInTheDocument());
    expect(calls.some((call) => call.url.startsWith('/api/platform'))).toBe(false);
  });
});

describe('申请与推荐页签', () => {
  test('有待审批申请时「申请」页签显示数量角标', async () => {
    const pending = [makeApplication(), makeApplication({ id: 2 }), makeApplication({ id: 3 })];
    const { calls } = setup({ 'GET /api/platform/applications': makeApplicationPage(pending) });

    expect(await screen.findByTestId('pending-badge')).toHaveTextContent('3');
    expect(screen.getByRole('tab', { name: /申请/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '推荐' })).toBeInTheDocument();
    const probe = calls.find((call) => call.url.startsWith('/api/platform/applications'));
    expect(probe?.url).toContain('status=pending');
  });

  test('没有待审批时不显示角标', async () => {
    setup({});
    expect(await screen.findByRole('tab', { name: /申请/ })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByTestId('pending-badge')).not.toBeInTheDocument());
  });
});

describe('邮件页签', () => {
  test('未配置邮件时「申请」页签顶部提示，点击跳到「邮件」页签', async () => {
    const user = userEvent.setup();
    setup({ 'GET /api/platform/mail-settings': UNCONFIGURED_MAIL });

    await user.click(await screen.findByRole('tab', { name: /申请/ }));
    expect(await screen.findByTestId('mail-not-configured')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '去配置邮件' }));

    expect(screen.getByRole('tab', { name: '邮件' })).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByLabelText('SMTP 服务器')).toBeInTheDocument();
  });

  test('已配置邮件时不显示提示', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'GET /api/platform/mail-settings': makeMailSettings() });

    await user.click(await screen.findByRole('tab', { name: /申请/ }));
    await waitFor(() => expect(calls.some((call) => call.url === '/api/platform/mail-settings')).toBe(true));
    expect(screen.queryByTestId('mail-not-configured')).not.toBeInTheDocument();
  });
});

describe('平台备份页签', () => {
  test('平台管理员能看到「平台备份」页签，打开后列出平台数据库备份', async () => {
    const user = userEvent.setup();
    setup({
      'GET /api/platform/backups': { items: [{ name: 'control_20260921_101500.db', size: 1024 * 1024, created_at: '2026-09-21T10:15:00+08:00' }] },
    });

    await user.click(await screen.findByRole('tab', { name: '平台备份' }));

    expect(await screen.findByLabelText('下载 control_20260921_101500.db'))
      .toHaveAttribute('href', '/api/platform/backups/control_20260921_101500.db');
  });

  test('租户管理员看不到「平台备份」，也不会请求平台备份列表', async () => {
    const { calls } = setup({ 'GET /api/platform/overview': () => ({ status: 403, error: '需要平台管理员权限' }) });

    await waitFor(() => expect(screen.queryByRole('heading', { name: '平台运营' })).not.toBeInTheDocument());
    expect(screen.queryByRole('tab', { name: '平台备份' })).not.toBeInTheDocument();
    expect(calls.some((call) => call.url.startsWith('/api/platform/backups'))).toBe(false);
  });
});
