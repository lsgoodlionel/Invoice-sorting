import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import { mockFetch, type RecordedCall } from '../../test/fetchMock';
import { makePlan, makeTenant, makeTenantPage } from '../../test/platformFixtures';
import { renderWithProviders } from '../../test/render';
import { TenantManager } from './TenantManager';

type Routes = Record<string, unknown>;

const TENANTS = [
  makeTenant(),
  makeTenant({ slug: 'beta', name: '贝塔账套', status: 'suspended', plan: null, expires_on: null, usage: null, member_count: 1 }),
];

function setup(extra: Routes = {}) {
  const result = mockFetch({
    'GET /api/platform/tenants': makeTenantPage(TENANTS),
    'GET /api/platform/plans': [makePlan()],
    ...extra,
  });
  renderWithProviders(<TenantManager />);
  return result;
}

const findCall = (calls: RecordedCall[], method: string, url: string) =>
  calls.find((call) => call.method === method && call.url.split('?')[0] === url);

describe('账套列表', () => {
  test('显示套餐、状态、成员数、用量与到期日', async () => {
    setup();

    const row = await screen.findByTestId('tenant-row-alpha');
    expect(within(row).getByText('团队版')).toBeInTheDocument();
    expect(within(row).getByText('启用')).toBeInTheDocument();
    expect(within(row).getByText('2027-01-31')).toBeInTheDocument();
    expect(within(row).getByText('1.0 MB · 7 条')).toBeInTheDocument();
    const suspended = screen.getByTestId('tenant-row-beta');
    expect(within(suspended).getByText('已停用')).toBeInTheDocument();
    expect(within(suspended).getByText('未指定')).toBeInTheDocument();
    expect(within(suspended).getByText('永久')).toBeInTheDocument();
  });

  test('搜索词写进请求并回到第一页', async () => {
    const user = userEvent.setup();
    const { calls } = setup();
    await screen.findByTestId('tenant-row-alpha');

    await user.type(screen.getByPlaceholderText('搜索账套标识或名称'), 'bet');

    await waitFor(() => {
      const last = calls.filter((call) => call.url.startsWith('/api/platform/tenants')).at(-1);
      expect(last?.url).toContain('q=bet');
      expect(last?.url).toContain('page=1');
    });
  });
});

describe('开通账套', () => {
  test('校验标识并提交首个管理员', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'POST /api/platform/tenants': { ...makeTenant({ slug: 'gamma' }), admin: null, invite: null } });
    await user.click(await screen.findByRole('button', { name: '开通账套' }));
    const dialog = await screen.findByRole('dialog', { name: '开通账套' });
    const submit = within(dialog).getByRole('button', { name: '开通账套' });

    await user.type(within(dialog).getByLabelText('账套标识'), 'Gamma');
    expect(within(dialog).getByText(/只能使用小写字母/)).toBeInTheDocument();
    expect(submit).toBeDisabled();

    await user.clear(within(dialog).getByLabelText('账套标识'));
    await user.type(within(dialog).getByLabelText('账套标识'), 'gamma');
    await user.type(within(dialog).getByLabelText('名称'), '伽马学院');
    await user.type(within(dialog).getByLabelText('首个管理员用户名'), 'gamma-boss');
    await user.type(within(dialog).getByLabelText('初始密码'), 'gamma-pass-1');
    await user.type(within(dialog).getByLabelText('确认密码'), 'gamma-pass-1');
    await user.click(submit);

    await waitFor(() =>
      expect(findCall(calls, 'POST', '/api/platform/tenants')?.body).toEqual({
        slug: 'gamma',
        name: '伽马学院',
        admin_username: 'gamma-boss',
        admin_password: 'gamma-pass-1',
      }),
    );
  });

  test('改为签发邀请码时不需要填管理员，并展示邀请码', async () => {
    const user = userEvent.setup();
    const invite = { id: 1, code: 'INVITE-CODE', role: 'admin', expires_on: null, is_used: false, used_at: null, created_at: '' };
    const { calls } = setup({
      'POST /api/platform/tenants': { ...makeTenant({ slug: 'delta' }), admin: null, invite },
    });
    await user.click(await screen.findByRole('button', { name: '开通账套' }));
    const dialog = await screen.findByRole('dialog', { name: '开通账套' });

    await user.type(within(dialog).getByLabelText('账套标识'), 'delta');
    await user.click(within(dialog).getByRole('switch', { name: /签发管理员邀请码/ }));
    await user.click(within(dialog).getByRole('button', { name: '开通账套' }));

    expect(await screen.findByTestId('opened-invite')).toHaveTextContent('INVITE-CODE');
    expect(findCall(calls, 'POST', '/api/platform/tenants')?.body).toEqual({
      slug: 'delta',
      name: 'delta',
      with_invite: true,
    });
  });

  test('后端拒绝时在弹窗里显示原文', async () => {
    const user = userEvent.setup();
    setup({ 'POST /api/platform/tenants': () => ({ status: 409, error: '账套标识已被占用' }) });
    await user.click(await screen.findByRole('button', { name: '开通账套' }));
    const dialog = await screen.findByRole('dialog', { name: '开通账套' });

    await user.type(within(dialog).getByLabelText('账套标识'), 'alpha');
    await user.type(within(dialog).getByLabelText('首个管理员用户名'), 'boss');
    await user.type(within(dialog).getByLabelText('初始密码'), 'alpha-pass-1');
    await user.type(within(dialog).getByLabelText('确认密码'), 'alpha-pass-1');
    await user.click(within(dialog).getByRole('button', { name: '开通账套' }));

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('账套标识已被占用');
  });
});

describe('编辑账套', () => {
  test('只提交改动的字段（停用）', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'PATCH /api/platform/tenants/alpha': makeTenant({ status: 'suspended' }) });
    await user.click(within(await screen.findByTestId('tenant-row-alpha')).getByRole('button', { name: '编辑 alpha' }));
    const dialog = await screen.findByRole('dialog', { name: '编辑账套：alpha' });

    await user.click(within(dialog).getByRole('radio', { name: '停用' }));
    expect(within(dialog).getByText(/停用后成员只能登录查看与导出/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: '保存' }));

    await waitFor(() =>
      expect(findCall(calls, 'PATCH', '/api/platform/tenants/alpha')?.body).toEqual({ status: 'suspended' }),
    );
  });

  test('清空到期日表示长期有效', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'PATCH /api/platform/tenants/alpha': makeTenant({ expires_on: null }) });
    await user.click(within(await screen.findByTestId('tenant-row-alpha')).getByRole('button', { name: '编辑 alpha' }));
    const dialog = await screen.findByRole('dialog', { name: '编辑账套：alpha' });

    await user.clear(within(dialog).getByLabelText('到期日'));
    await user.click(within(dialog).getByRole('button', { name: '保存' }));

    await waitFor(() =>
      expect(findCall(calls, 'PATCH', '/api/platform/tenants/alpha')?.body).toEqual({ expires_on: null }),
    );
  });
});
