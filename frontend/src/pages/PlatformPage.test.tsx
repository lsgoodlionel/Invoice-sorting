import { screen, waitFor } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import { AUTHENTICATED, SAAS_AUTHENTICATED } from '../test/authStatus';
import { mockFetch } from '../test/fetchMock';
import { OVERVIEW, makeTenantPage } from '../test/platformFixtures';
import { ADMIN_CONTEXT, renderWithProviders } from '../test/render';
import { PlatformPage } from './PlatformPage';

type Routes = Record<string, unknown>;

const MEMBER_CONTEXT = { user: null, isAdmin: false, authEnabled: true };

function setup(routes: Routes, currentUser = ADMIN_CONTEXT) {
  const result = mockFetch({
    'GET /api/auth/status': SAAS_AUTHENTICATED,
    'GET /api/platform/overview': OVERVIEW,
    'GET /api/platform/tenants': makeTenantPage([]),
    'GET /api/platform/plans': [],
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
    expect(calls.some((call) => call.url.startsWith('/api/platform'))).toBe(false);
  });

  test('单账套部署没有平台概念：不探测也不显示', async () => {
    const { calls } = setup({ 'GET /api/auth/status': AUTHENTICATED });

    await waitFor(() => expect(screen.queryByRole('heading', { name: '平台运营' })).not.toBeInTheDocument());
    expect(calls.some((call) => call.url.startsWith('/api/platform'))).toBe(false);
  });
});
