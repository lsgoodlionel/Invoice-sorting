import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, test } from 'vitest';
import { AuthGate } from '../../components/auth/AuthGate';
import { REMEMBERED_USERNAME_KEY } from '../../lib/rememberedUsername';
import { createQueryClient } from '../../queryClient';
import { ADMIN_USER, SAAS_AUTHENTICATED, SAAS_NEEDS_LOGIN, authStatusRoute } from '../../test/authStatus';
import { mockFetch } from '../../test/fetchMock';
import { renderWithProviders } from '../../test/render';

type Routes = Record<string, unknown>;

const CODE_INFO = { email: 'zhangsan@example.com', name: '张三', ledger_name: '张三课题组', expires_at: '2026-09-28T10:00:00+08:00' };

function setup(routes: Routes, route = '/register?code=REG-1') {
  const result = mockFetch({ 'GET /api/auth/status': SAAS_NEEDS_LOGIN, ...routes });
  renderWithProviders(
    <AuthGate>
      <div>应用内容</div>
    </AuthGate>,
    { client: createQueryClient(), route },
  );
  return result;
}

afterEach(() => window.localStorage.clear());

describe('注册页', () => {
  test('校验注册码后显示只读邮箱', async () => {
    const { calls } = setup({ 'GET /api/signup/register': CODE_INFO });
    const email = await screen.findByLabelText('邮箱');
    expect(email).toHaveValue('zhangsan@example.com');
    expect(email).toHaveAttribute('readonly');
    expect(screen.getByText(/2026-09-28 10:00/)).toHaveTextContent('「张三课题组」');
    expect(calls.find((call) => call.url.startsWith('/api/signup/register'))?.url).toBe('/api/signup/register?code=REG-1');
  });

  test('设置用户名与密码后提交并直接进入应用', async () => {
    const user = userEvent.setup();
    const status = authStatusRoute(SAAS_NEEDS_LOGIN);
    const { calls } = setup({
      'GET /api/auth/status': status.route,
      'GET /api/signup/register': CODE_INFO,
      'POST /api/signup/register': () => {
        status.set(SAAS_AUTHENTICATED);
        return { data: { authenticated: true, user: ADMIN_USER, tenant: { slug: 'zhangsan', name: '张三的账本' } } };
      },
    });
    const submit = await screen.findByRole('button', { name: '注册并进入' });
    expect(submit).toBeDisabled();

    await user.type(screen.getByLabelText('用户名'), 'zhangsan');
    await user.type(screen.getByLabelText('密码'), 'register-pass-1');
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText('确认密码'), 'register-pass-1');
    await user.click(submit);

    expect(await screen.findByText('应用内容')).toBeInTheDocument();
    expect(calls.find((call) => call.method === 'POST' && call.url === '/api/signup/register')?.body).toEqual({
      code: 'REG-1',
      email: 'zhangsan@example.com',
      username: 'zhangsan',
      password: 'register-pass-1',
    });
    expect(window.localStorage.getItem(REMEMBERED_USERNAME_KEY)).toBe('zhangsan');
  });

  test('注册码过期时说明原因并给出重新申请入口', async () => {
    const user = userEvent.setup();
    setup({ 'GET /api/signup/register': () => ({ status: 410, error: '注册链接已过期，请联系平台重新发送' }) });

    expect(await screen.findByRole('heading', { name: '注册链接不可用' })).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('注册链接已过期，请联系平台重新发送');
    await user.click(screen.getByRole('link', { name: '重新申请' }));
    expect(await screen.findByRole('heading', { name: '申请使用' })).toBeInTheDocument();
  });

  test('链接缺少注册码时不请求后端', async () => {
    const { calls } = setup({}, '/register');
    expect(await screen.findByRole('heading', { name: '注册链接不可用' })).toBeInTheDocument();
    expect(calls.some((call) => call.url.startsWith('/api/signup'))).toBe(false);
  });

  test('用户名已被占用时展示后端原文', async () => {
    const user = userEvent.setup();
    setup({
      'GET /api/signup/register': CODE_INFO,
      'POST /api/signup/register': () => ({ status: 409, error: '用户名已被使用' }),
    });
    await user.type(await screen.findByLabelText('用户名'), 'zhangsan');
    await user.type(screen.getByLabelText('密码'), 'register-pass-1');
    await user.type(screen.getByLabelText('确认密码'), 'register-pass-1');
    await user.click(screen.getByRole('button', { name: '注册并进入' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('用户名已被使用');
  });
});
