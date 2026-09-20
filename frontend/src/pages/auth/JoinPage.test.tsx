import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, test } from 'vitest';
import { AuthGate } from '../../components/auth/AuthGate';
import { createQueryClient } from '../../queryClient';
import {
  ADMIN_USER,
  NEEDS_LOGIN,
  SAAS_AUTHENTICATED,
  SAAS_NEEDS_LOGIN,
  authStatusRoute,
} from '../../test/authStatus';
import { mockFetch } from '../../test/fetchMock';
import { renderWithProviders } from '../../test/render';

type Routes = Record<string, unknown>;

const renderGate = () =>
  renderWithProviders(
    <AuthGate>
      <div>应用内容</div>
    </AuthGate>,
    { client: createQueryClient() },
  );

function setup(routes: Routes) {
  const result = mockFetch(routes);
  renderGate();
  return result;
}

const fill = async (user: ReturnType<typeof userEvent.setup>, label: string, value: string) =>
  user.type(await screen.findByLabelText(label), value);

afterEach(() => window.localStorage.clear());

describe('JoinPage 入口', () => {
  test('单租户部署的登录页没有邀请码入口', async () => {
    setup({ 'GET /api/auth/status': NEEDS_LOGIN });
    expect(await screen.findByRole('heading', { name: '登录' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '有邀请码？加入账套' })).not.toBeInTheDocument();
  });

  test('多租户部署可在登录页与加入页之间来回切换', async () => {
    const user = userEvent.setup();
    setup({ 'GET /api/auth/status': SAAS_NEEDS_LOGIN });

    await user.click(await screen.findByRole('button', { name: '有邀请码？加入账套' }));
    expect(await screen.findByRole('heading', { name: '加入账套' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '已有账号，直接登录' }));
    expect(await screen.findByRole('heading', { name: '登录' })).toBeInTheDocument();
  });
});

describe('JoinPage 表单', () => {
  const open = async (user: ReturnType<typeof userEvent.setup>) =>
    user.click(await screen.findByRole('button', { name: '有邀请码？加入账套' }));

  test('邀请码或密码不完整时不能提交', async () => {
    const user = userEvent.setup();
    setup({ 'GET /api/auth/status': SAAS_NEEDS_LOGIN });
    await open(user);

    const submit = await screen.findByRole('button', { name: '加入并进入' });
    expect(submit).toBeDisabled();
    await fill(user, '邀请码', 'INVITE-1');
    await fill(user, '用户名', 'zhaoliu');
    await fill(user, '密码', 'joiner-pass-123');
    expect(submit).toBeDisabled(); // 确认密码还没填
    await fill(user, '确认密码', 'joiner-pass-123');
    expect(submit).toBeEnabled();
  });

  test('提交契约载荷并进入应用', async () => {
    const user = userEvent.setup();
    const status = authStatusRoute(SAAS_NEEDS_LOGIN);
    const { calls } = setup({
      'GET /api/auth/status': status.route,
      'POST /api/auth/join': () => {
        status.set(SAAS_AUTHENTICATED);
        return { data: { authenticated: true, user: ADMIN_USER, tenant: { slug: 'alpha', name: '阿尔法账套' } } };
      },
    });
    await open(user);

    await fill(user, '邀请码', 'INVITE-1');
    await fill(user, '用户名', 'zhaoliu');
    await fill(user, '姓名', '赵六');
    await fill(user, '密码', 'joiner-pass-123');
    await fill(user, '确认密码', 'joiner-pass-123');
    await user.click(screen.getByRole('button', { name: '加入并进入' }));

    await waitFor(() => expect(screen.getByText('应用内容')).toBeInTheDocument());
    const call = calls.find((item) => item.url === '/api/auth/join');
    expect(call?.body).toEqual({
      code: 'INVITE-1',
      username: 'zhaoliu',
      password: 'joiner-pass-123',
      display_name: '赵六',
    });
  });

  test('邀请码无效时原样展示后端文案', async () => {
    const user = userEvent.setup();
    setup({
      'GET /api/auth/status': SAAS_NEEDS_LOGIN,
      'POST /api/auth/join': () => ({ status: 404, error: '邀请码无效，请向管理员重新索取' }),
    });
    await open(user);

    await fill(user, '邀请码', 'nope');
    await fill(user, '用户名', 'zhaoliu');
    await fill(user, '密码', 'joiner-pass-123');
    await fill(user, '确认密码', 'joiner-pass-123');
    await user.click(screen.getByRole('button', { name: '加入并进入' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('邀请码无效，请向管理员重新索取');
  });
});
