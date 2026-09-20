import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import { createQueryClient } from '../../queryClient';
import { AUTHENTICATED, SAAS_AUTHENTICATED, TENANT_OPTIONS } from '../../test/authStatus';
import { mockFetch } from '../../test/fetchMock';
import { renderWithProviders } from '../../test/render';
import { NavUserFooter } from './NavUserFooter';

type Routes = Record<string, unknown>;

function setup(routes: Routes) {
  const result = mockFetch(routes);
  renderWithProviders(<NavUserFooter />, { client: createQueryClient() });
  return result;
}

describe('TenantSwitcher', () => {
  test('单租户部署完全看不到账套入口', async () => {
    setup({ 'GET /api/auth/status': AUTHENTICATED });
    expect(await screen.findByRole('button', { name: '退出登录' })).toBeInTheDocument();
    expect(screen.queryByTestId('tenant-switcher')).not.toBeInTheDocument();
  });

  test('只有一个账套时不显示切换入口', async () => {
    setup({
      'GET /api/auth/status': SAAS_AUTHENTICATED,
      'GET /api/auth/tenants': [TENANT_OPTIONS[0]],
    });
    expect(await screen.findByRole('button', { name: '退出登录' })).toBeInTheDocument();
    expect(screen.queryByTestId('tenant-switcher')).not.toBeInTheDocument();
  });

  test('多个账套时显示当前账套并可切换', async () => {
    const user = userEvent.setup();
    const { calls } = setup({
      'GET /api/auth/status': SAAS_AUTHENTICATED,
      'GET /api/auth/tenants': TENANT_OPTIONS,
      'POST /api/auth/switch-tenant': { authenticated: true, user: null, tenant: TENANT_OPTIONS[1] },
    });

    const trigger = await screen.findByTestId('tenant-switcher');
    expect(trigger).toHaveTextContent('阿尔法账套');
    await user.click(trigger);
    await user.click(await screen.findByRole('menuitem', { name: '贝塔账套' }));

    await waitFor(() => {
      const call = calls.find((item) => item.url === '/api/auth/switch-tenant');
      expect(call?.body).toEqual({ slug: 'beta' });
    });
  });
});
