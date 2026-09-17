import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import type { User } from '../../../api/types';
import { mockFetch, type RecordedCall } from '../../../test/fetchMock';
import { makeUser } from '../../../test/fixtures';
import { renderWithProviders } from '../../../test/render';
import { UserManager } from './UserManager';

const USERS: User[] = [
  makeUser({ id: 1, username: 'admin', display_name: '管理员', role: 'admin' }),
  makeUser({ id: 2 }),
  makeUser({ id: 3, username: 'lisi', display_name: '李四', is_active: false, last_login_at: null }),
];

type Routes = Record<string, unknown>;

function setup(extra: Routes = {}) {
  const result = mockFetch({ 'GET /api/users': USERS, ...extra });
  renderWithProviders(<UserManager />);
  return result;
}

const findCall = (calls: RecordedCall[], method: string, url: string) => calls.find((c) => c.method === method && c.url === url);

describe('UserManager list', () => {
  test('renders username, name, role, status and last login', async () => {
    setup();
    const row = await screen.findByTestId('user-row-3');
    expect(within(row).getByText('lisi')).toBeInTheDocument();
    expect(within(row).getByText('李四')).toBeInTheDocument();
    expect(within(row).getByText('普通用户')).toBeInTheDocument();
    expect(within(row).getByText('已停用')).toBeInTheDocument();
    expect(within(row).getByText('从未登录')).toBeInTheDocument();
    expect(within(screen.getByTestId('user-row-1')).getByText('管理员', { selector: '.mantine-Badge-label' })).toBeInTheDocument();
    expect(within(screen.getByTestId('user-row-1')).getByText('（我）')).toBeInTheDocument();
    expect(within(row).getByRole('button', { name: '启用 李四' })).toBeInTheDocument();
  });
});

describe('UserManager add user', () => {
  test('validates input and sends contract payload', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'POST /api/users': makeUser({ id: 4, username: 'wangwu' }) });
    await user.click(await screen.findByRole('button', { name: '添加用户' }));
    const dialog = await screen.findByRole('dialog', { name: '添加用户' });
    const submit = within(dialog).getByRole('button', { name: '创建用户' });

    await user.type(within(dialog).getByLabelText('用户名'), '王五wu');
    expect(within(dialog).getByText('只能包含字母、数字、下划线、点、连字符')).toBeInTheDocument();
    expect(submit).toBeDisabled();

    await user.clear(within(dialog).getByLabelText('用户名'));
    await user.type(within(dialog).getByLabelText('用户名'), 'wangwu');
    await user.type(within(dialog).getByLabelText('姓名'), ' 王五 ');
    await user.click(within(dialog).getByRole('radio', { name: '管理员' }));
    await user.type(within(dialog).getByLabelText('初始密码'), 'password-123');
    await user.type(within(dialog).getByLabelText('确认密码'), 'password-12');
    expect(submit).toBeDisabled();
    await user.type(within(dialog).getByLabelText('确认密码'), '3');
    await user.click(submit);

    await waitFor(() =>
      expect(findCall(calls, 'POST', '/api/users')?.body).toEqual({
        username: 'wangwu',
        display_name: '王五',
        password: 'password-123',
        role: 'admin',
      }),
    );
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '添加用户' })).not.toBeInTheDocument());
  });

  test('omits empty display name and shows backend conflict inline', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'POST /api/users': () => ({ status: 409, error: '用户名已存在' }) });
    await user.click(await screen.findByRole('button', { name: '添加用户' }));
    const dialog = await screen.findByRole('dialog', { name: '添加用户' });
    await user.type(within(dialog).getByLabelText('用户名'), 'zhangsan');
    await user.type(within(dialog).getByLabelText('初始密码'), 'password-123');
    await user.type(within(dialog).getByLabelText('确认密码'), 'password-123');
    await user.click(within(dialog).getByRole('button', { name: '创建用户' }));

    expect(await within(dialog).findByText('用户名已存在')).toBeInTheDocument();
    expect(findCall(calls, 'POST', '/api/users')?.body).toEqual({ username: 'zhangsan', password: 'password-123', role: 'member' });
  });
});

describe('UserManager row actions', () => {
  test('edits display name with only changed fields', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'PATCH /api/users/2': makeUser({ display_name: '张三丰' }) });
    await user.click(await screen.findByRole('button', { name: '编辑 张三' }));
    const dialog = await screen.findByRole('dialog', { name: '编辑用户：zhangsan' });
    await user.type(within(dialog).getByLabelText('姓名'), '丰');
    await user.click(within(dialog).getByRole('button', { name: '保存' }));
    await waitFor(() => expect(findCall(calls, 'PATCH', '/api/users/2')?.body).toEqual({ display_name: '张三丰' }));
  });

  test('resets password with confirmation fields and re-login hint', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'POST /api/users/2/password': null });
    await user.click(await screen.findByRole('button', { name: '重置 张三 的密码' }));
    const dialog = await screen.findByRole('dialog', { name: '重置密码：张三' });
    expect(within(dialog).getByText('该用户需使用新密码重新登录')).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText('新密码'), 'new-password-1');
    await user.type(within(dialog).getByLabelText('确认密码'), 'new-password-1');
    await user.click(within(dialog).getByRole('button', { name: '重置密码' }));
    await waitFor(() => expect(findCall(calls, 'POST', '/api/users/2/password')?.body).toEqual({ password: 'new-password-1' }));
  });

  test('deactivates only after confirmation', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'PATCH /api/users/2': makeUser({ is_active: false }) });
    await user.click(await screen.findByRole('button', { name: '停用 张三' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/该用户将立即退出登录/)).toBeInTheDocument();
    expect(findCall(calls, 'PATCH', '/api/users/2')).toBeUndefined();
    await user.click(within(dialog).getByRole('button', { name: '停用' }));
    await waitFor(() => expect(findCall(calls, 'PATCH', '/api/users/2')?.body).toEqual({ is_active: false }));
  });

  test('re-enables without confirmation and shows backend constraint message', async () => {
    const user = userEvent.setup();
    setup({ 'PATCH /api/users/3': () => ({ status: 400, error: '系统必须至少保留一名启用中且已设置密码的管理员' }) });
    await user.click(await screen.findByRole('button', { name: '启用 李四' }));
    expect(await screen.findByText('系统必须至少保留一名启用中且已设置密码的管理员')).toBeInTheDocument();
  });

  test('disables deactivating and demoting the signed-in user', async () => {
    const user = userEvent.setup();
    setup();
    const deactivate = await screen.findByRole('button', { name: '停用 管理员' });
    expect(deactivate).toBeDisabled();
    await user.hover(deactivate.parentElement as HTMLElement);
    expect(await screen.findByText('不能停用当前登录的账户')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '编辑 管理员' }));
    const dialog = await screen.findByRole('dialog', { name: '编辑用户：admin' });
    expect(within(dialog).getByRole('radio', { name: '普通用户' })).toBeDisabled();
    expect(within(dialog).getByText('不能把自己改为普通用户')).toBeInTheDocument();
  });
});
