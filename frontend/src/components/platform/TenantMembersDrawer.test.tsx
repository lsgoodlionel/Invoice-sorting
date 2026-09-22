import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import { mockFetch, type RecordedCall } from '../../test/fetchMock';
import { makeUser } from '../../test/fixtures';
import { makeExportJob, makeTenant } from '../../test/platformFixtures';
import { renderWithProviders } from '../../test/render';
import { TenantMembersDrawer } from './TenantMembersDrawer';

type Routes = Record<string, unknown>;

const MEMBERS = [
  makeUser({ id: 1, username: 'alpha-admin', display_name: '账套管理员', role: 'admin' }),
  makeUser({ id: 2, username: 'zhangsan', display_name: '张三', role: 'member', is_active: false }),
];

function setup(extra: Routes = {}) {
  const result = mockFetch({
    'GET /api/platform/tenants/alpha/members': MEMBERS,
    ...extra,
  });
  renderWithProviders(<TenantMembersDrawer tenant={makeTenant()} onClose={() => {}} />);
  return result;
}

const findCall = (calls: RecordedCall[], method: string, url: string) =>
  calls.find((call) => call.method === method && call.url.split('?')[0] === url);

describe('账套成员', () => {
  test('列出成员与状态', async () => {
    setup();

    const row = await screen.findByTestId('member-row-2');
    expect(within(row).getByText('张三')).toBeInTheDocument();
    expect(within(row).getByText('已停用')).toBeInTheDocument();
    expect(within(row).getByRole('button', { name: '启用 张三' })).toBeInTheDocument();
  });

  test('停用成员发出正确的请求', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'PATCH /api/platform/tenants/alpha/members/1': MEMBERS[0] });

    const row = await screen.findByTestId('member-row-1');
    await user.click(within(row).getByRole('button', { name: '停用 账套管理员' }));

    await waitFor(() =>
      expect(findCall(calls, 'PATCH', '/api/platform/tenants/alpha/members/1')?.body).toEqual({ is_active: false }),
    );
  });

  test('删除成员：确认后移出该账套', async () => {
    const user = userEvent.setup();
    const { calls } = setup({
      'DELETE /api/platform/tenants/alpha/members/2': { id: 2, username: 'zhangsan', is_account_removed: true },
    });
    const row = await screen.findByTestId('member-row-2');
    await user.click(within(row).getByRole('button', { name: '删除 张三' }));

    const dialog = await screen.findByRole('dialog', { name: '将「张三」移出账套「阿尔法账套」？' });
    expect(within(dialog).getByText(/其上传与操作记录仍保留并显示原姓名/)).toBeInTheDocument();
    expect(findCall(calls, 'DELETE', '/api/platform/tenants/alpha/members/2')).toBeUndefined();
    await user.click(within(dialog).getByRole('button', { name: '移出' }));

    await waitFor(() => expect(findCall(calls, 'DELETE', '/api/platform/tenants/alpha/members/2')).toBeDefined());
  });

  test('删除最后一名管理员时显示后端原因', async () => {
    const user = userEvent.setup();
    setup({
      'DELETE /api/platform/tenants/alpha/members/1': () => ({ status: 409, error: '不能删除账套里最后一名可用的管理员' }),
    });
    const row = await screen.findByTestId('member-row-1');
    await user.click(within(row).getByRole('button', { name: '删除 账套管理员' }));
    const dialog = await screen.findByRole('dialog', { name: '将「账套管理员」移出账套「阿尔法账套」？' });
    await user.click(within(dialog).getByRole('button', { name: '移出' }));

    expect(await screen.findByText('不能删除账套里最后一名可用的管理员')).toBeInTheDocument();
  });

  test('添加成员：已有账号可以不填密码', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'POST /api/platform/tenants/alpha/members': makeUser({ id: 3, username: 'lisi' }) });
    await user.click(await screen.findByRole('button', { name: '添加成员' }));
    const dialog = await screen.findByRole('dialog', { name: '添加成员：alpha' });

    await user.type(within(dialog).getByLabelText('用户名'), 'lisi');
    await user.click(within(dialog).getByRole('button', { name: '添加成员' }));

    await waitFor(() =>
      expect(findCall(calls, 'POST', '/api/platform/tenants/alpha/members')?.body).toEqual({
        username: 'lisi',
        role: 'member',
      }),
    );
  });

  test('重置密码需要两次一致', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'POST /api/platform/tenants/alpha/members/2/password': null });
    const row = await screen.findByTestId('member-row-2');
    await user.click(within(row).getByRole('button', { name: '重置 张三 的密码' }));
    const dialog = await screen.findByRole('dialog', { name: '重置密码：张三' });
    const submit = within(dialog).getByRole('button', { name: '重置密码' });

    await user.type(within(dialog).getByLabelText('新密码'), 'new-pass-1234');
    expect(submit).toBeDisabled();
    await user.type(within(dialog).getByLabelText('确认密码'), 'new-pass-1234');
    await user.click(submit);

    await waitFor(() =>
      expect(findCall(calls, 'POST', '/api/platform/tenants/alpha/members/2/password')?.body).toEqual({
        password: 'new-pass-1234',
      }),
    );
  });
});

describe('邀请码与导出', () => {
  test('生成邀请码后展示码值', async () => {
    const user = userEvent.setup();
    const invite = { id: 9, code: 'CODE-9', role: 'member', expires_on: '2026-10-01', is_used: false, used_at: null, created_at: '' };
    setup({ 'POST /api/platform/tenants/alpha/invites': invite });
    await screen.findByTestId('member-row-1');

    await user.click(screen.getByRole('button', { name: '生成邀请码' }));

    expect(await screen.findByTestId('tenant-invite-code')).toHaveTextContent('CODE-9');
    expect(screen.getByText(/2026-10-01 前有效/)).toBeInTheDocument();
  });

  test('导出完成后给出下载链接', async () => {
    const user = userEvent.setup();
    setup({
      'POST /api/platform/tenants/alpha/export': makeExportJob(),
      'GET /api/platform/tenants/alpha/export/job-1/status': makeExportJob({
        status: 'done',
        file: 'alpha.zip',
        size: 1024 * 1024,
      }),
    });
    await screen.findByTestId('member-row-1');

    await user.click(screen.getByRole('button', { name: '导出账套' }));

    const link = await screen.findByTestId('export-download');
    expect(link).toHaveTextContent('下载 alpha.zip（1.0 MB）');
    expect(link).toHaveAttribute('href', '/api/platform/tenants/alpha/export/job-1');
  });

  test('导出失败时显示后端原因', async () => {
    const user = userEvent.setup();
    setup({
      'POST /api/platform/tenants/alpha/export': makeExportJob(),
      'GET /api/platform/tenants/alpha/export/job-1/status': makeExportJob({ status: 'failed', error: '磁盘空间不足' }),
    });
    await screen.findByTestId('member-row-1');

    await user.click(screen.getByRole('button', { name: '导出账套' }));

    expect(await screen.findByText('磁盘空间不足')).toBeInTheDocument();
  });
});
