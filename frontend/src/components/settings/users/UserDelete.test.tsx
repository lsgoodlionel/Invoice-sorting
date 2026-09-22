import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import type { User } from '../../../api/types';
import { SAAS_AUTHENTICATED } from '../../../test/authStatus';
import { mockFetch, type RecordedCall } from '../../../test/fetchMock';
import { makeUser } from '../../../test/fixtures';
import { renderWithProviders } from '../../../test/render';
import { UserManager } from './UserManager';

const USERS: User[] = [
  makeUser({ id: 1, username: 'admin', display_name: '管理员', role: 'admin' }),
  makeUser({ id: 2 }),
];
const DELETED = { id: 2, username: 'zhangsan', is_account_removed: true };

function setup(extra: Record<string, unknown> = {}) {
  const result = mockFetch({ 'GET /api/users': USERS, ...extra });
  renderWithProviders(<UserManager />);
  return result;
}

const findCall = (calls: RecordedCall[], method: string, url: string) => calls.find((c) => c.method === method && c.url === url);

describe('UserManager delete user', () => {
  test('hides delete on the signed-in user row', async () => {
    setup();
    const self = await screen.findByTestId('user-row-1');
    expect(within(self).queryByRole('button', { name: /^删除/ })).not.toBeInTheDocument();
    expect(within(screen.getByTestId('user-row-2')).getByRole('button', { name: '删除 张三' })).toBeInTheDocument();
  });

  test('deletes only after confirmation and explains what is kept', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'DELETE /api/users/2': DELETED });
    await user.click(await screen.findByRole('button', { name: '删除 张三' }));

    const dialog = await screen.findByRole('dialog', { name: '删除用户「张三」？' });
    expect(within(dialog).getByText('删除后无法登录，用户名可再次使用；其上传与操作记录仍保留并显示原姓名。')).toBeInTheDocument();
    expect(findCall(calls, 'DELETE', '/api/users/2')).toBeUndefined();
    await user.click(within(dialog).getByRole('button', { name: '删除' }));

    await waitFor(() => expect(findCall(calls, 'DELETE', '/api/users/2')).toBeDefined());
    expect(await screen.findByText('已删除「张三」')).toBeInTheDocument();
  });

  test('cancel keeps the user', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'DELETE /api/users/2': DELETED });
    await user.click(await screen.findByRole('button', { name: '删除 张三' }));
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: '取消' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(findCall(calls, 'DELETE', '/api/users/2')).toBeUndefined();
  });

  test('shows the backend message when the last admin cannot be deleted', async () => {
    const user = userEvent.setup();
    setup({ 'DELETE /api/users/2': () => ({ status: 409, error: '不能删除账套里最后一名可用的管理员' }) });
    await user.click(await screen.findByRole('button', { name: '删除 张三' }));
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: '删除' }));

    expect(await screen.findByText('不能删除账套里最后一名可用的管理员')).toBeInTheDocument();
  });

  test('multi-tenant wording removes the member from this tenant', async () => {
    const user = userEvent.setup();
    const { calls } = setup({
      'GET /api/auth/status': SAAS_AUTHENTICATED,
      'DELETE /api/users/2': { ...DELETED, is_account_removed: false },
    });
    await screen.findByRole('button', { name: '邀请码' });
    await user.click(screen.getByRole('button', { name: '删除 张三' }));

    const dialog = await screen.findByRole('dialog', { name: '将「张三」移出本账套？' });
    expect(within(dialog).getByText(/之后无法再进入本账套/)).toBeInTheDocument();
    expect(within(dialog).queryByText(/删除后无法登录/)).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: '移出' }));

    await waitFor(() => expect(findCall(calls, 'DELETE', '/api/users/2')).toBeDefined());
    expect(await screen.findByText('已将「张三」移出本账套')).toBeInTheDocument();
  });
});
