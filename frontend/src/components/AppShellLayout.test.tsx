import { screen, waitFor } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import { AUTHENTICATED, SAAS_AUTHENTICATED } from '../test/authStatus';
import { mockFetch } from '../test/fetchMock';
import { OVERVIEW } from '../test/platformFixtures';
import { ADMIN_CONTEXT, renderWithProviders } from '../test/render';
import { AppShellLayout } from './AppShellLayout';

type Routes = Record<string, unknown>;

const MEMBER_CONTEXT = { user: null, isAdmin: false, authEnabled: true };

function setup(routes: Routes = {}, currentUser = ADMIN_CONTEXT) {
  mockFetch({
    'GET /api/auth/status': SAAS_AUTHENTICATED,
    'GET /api/auth/tenants': [],
    'GET /api/dashboard': { missing: [], overdue: [], spent_without_invoice: [], unassigned_count: 0, month_totals: {} },
    'GET /api/license/status': { state: 'active', message: '授权正常。' },
    'GET /api/quota': { enforced: false },
    'GET /api/platform/overview': OVERVIEW,
    ...routes,
  });
  renderWithProviders(<AppShellLayout />, { currentUser });
}

describe('平台入口的可见性', () => {
  test('平台管理员的导航里出现「平台」', async () => {
    setup();

    expect(await screen.findByRole('link', { name: '平台' })).toHaveAttribute('href', '/platform');
  });

  test('租户管理员（探测 403）看不到入口', async () => {
    setup({ 'GET /api/platform/overview': () => ({ status: 403, error: '需要平台管理员权限' }) });

    await screen.findByRole('link', { name: '清单' });
    await waitFor(() => expect(screen.queryByRole('link', { name: '平台' })).not.toBeInTheDocument());
  });

  test('普通成员看不到入口', async () => {
    setup({}, MEMBER_CONTEXT);

    await screen.findByRole('link', { name: '清单' });
    expect(screen.queryByRole('link', { name: '平台' })).not.toBeInTheDocument();
  });

  test('单账套部署不出现平台入口', async () => {
    setup({ 'GET /api/auth/status': AUTHENTICATED });

    await screen.findByRole('link', { name: '清单' });
    expect(screen.queryByRole('link', { name: '平台' })).not.toBeInTheDocument();
  });
});
