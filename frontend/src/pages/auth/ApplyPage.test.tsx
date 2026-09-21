import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import { AuthGate } from '../../components/auth/AuthGate';
import { createQueryClient } from '../../queryClient';
import { NEEDS_LOGIN, SAAS_NEEDS_LOGIN } from '../../test/authStatus';
import { mockFetch } from '../../test/fetchMock';
import { renderWithProviders } from '../../test/render';

type Routes = Record<string, unknown>;

const receipt = (number: string, status: string) => ({ id: 1, number, status, referrer_name: null, message: '' });
type User = ReturnType<typeof userEvent.setup>;

function setup(routes: Routes, route = '/apply') {
  const result = mockFetch({ 'GET /api/auth/status': SAAS_NEEDS_LOGIN, ...routes });
  renderWithProviders(
    <AuthGate>
      <div>应用内容</div>
    </AuthGate>,
    { client: createQueryClient(), route },
  );
  return result;
}

async function fillRequired(user: User) {
  await user.type(await screen.findByLabelText('姓名'), '张三');
  await user.type(screen.getByLabelText('邮箱'), 'zhangsan@example.com');
  await user.type(screen.getByLabelText('单位或身份'), '某某大学');
  await user.type(screen.getByLabelText('使用需求简介'), '课题组报销');
}

describe('登录页的申请入口', () => {
  test('单账套部署的登录页没有申请入口', async () => {
    setup({ 'GET /api/auth/status': NEEDS_LOGIN }, '/');
    expect(await screen.findByRole('heading', { name: '登录' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '还没有账号？申请使用' })).not.toBeInTheDocument();
  });

  test('单账套部署打开 /apply 仍是登录页', async () => {
    setup({ 'GET /api/auth/status': NEEDS_LOGIN });
    expect(await screen.findByRole('heading', { name: '登录' })).toBeInTheDocument();
  });

  test('多账套登录页可进入申请页并返回', async () => {
    const user = userEvent.setup();
    setup({}, '/');
    await user.click(await screen.findByRole('link', { name: '还没有账号？申请使用' }));
    expect(await screen.findByRole('heading', { name: '申请使用' })).toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: '已有账号？直接登录' }));
    expect(await screen.findByRole('heading', { name: '登录' })).toBeInTheDocument();
  });
});

describe('申请表', () => {
  test('必填项齐全且邮箱有效才能提交', async () => {
    const user = userEvent.setup();
    setup({});
    const submit = await screen.findByRole('button', { name: '提交申请' });
    expect(submit).toBeDisabled();

    await user.type(screen.getByLabelText('姓名'), '张三');
    await user.type(screen.getByLabelText('邮箱'), 'bad-mail');
    await user.type(screen.getByLabelText('单位或身份'), '某某大学');
    await user.type(screen.getByLabelText('使用需求简介'), '课题组报销');
    expect(screen.getByText('请填写有效的邮箱地址')).toBeInTheDocument();
    expect(submit).toBeDisabled();

    await user.clear(screen.getByLabelText('邮箱'));
    await user.type(screen.getByLabelText('邮箱'), 'zhangsan@example.com');
    expect(submit).toBeEnabled();
  });

  test('提交契约载荷（含空诱饵字段）并显示申请编号', async () => {
    const user = userEvent.setup();
    const { calls } = setup({
      'POST /api/signup/applications': receipt('SQ000001', 'pending'),
    });
    await fillRequired(user);
    await user.type(screen.getByLabelText('期望账本名称'), '课题组账本');
    await user.click(screen.getByRole('button', { name: '提交申请' }));

    expect(await screen.findByTestId('application-no')).toHaveTextContent('SQ000001');
    expect(screen.getByText(/审批结果会发到你的邮箱/)).toBeInTheDocument();
    expect(calls.find((call) => call.url === '/api/signup/applications')?.body).toEqual({
      name: '张三',
      email: 'zhangsan@example.com',
      identity: '某某大学',
      needs: '课题组报销',
      ledger_name: '课题组账本',
      website: '',
    });
  });

  test('限流或重复申请时展示后端原文', async () => {
    const user = userEvent.setup();
    setup({
      'POST /api/signup/applications': () => ({ status: 409, error: '该邮箱已有待审批的申请，请耐心等待' }),
    });
    await fillRequired(user);
    await user.click(screen.getByRole('button', { name: '提交申请' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('该邮箱已有待审批的申请，请耐心等待');
  });
});

describe('带推荐码的申请页', () => {
  test('有效推荐码显示推荐人，并随申请提交', async () => {
    const user = userEvent.setup();
    const { calls } = setup(
      {
        'GET /api/signup/referral/REF123': { code: 'REF123', referrer_name: '李四', require_approval: true },
        'POST /api/signup/applications': receipt('SQ-2', 'pending'),
      },
      '/apply?ref=REF123',
    );
    expect(await screen.findByTestId('referral-by')).toHaveTextContent('由 李四 推荐');
    expect(screen.queryByRole('textbox', { name: '推荐人' })).not.toBeInTheDocument();

    await fillRequired(user);
    await user.click(screen.getByRole('button', { name: '提交申请' }));
    await screen.findByTestId('application-no');
    const body = calls.find((call) => call.url === '/api/signup/applications')?.body as Record<string, unknown>;
    expect(body.ref).toBe('REF123');
  });

  test('推荐码无效时友好提示，仍可普通申请且不带推荐码', async () => {
    const user = userEvent.setup();
    const { calls } = setup(
      {
        'GET /api/signup/referral/NOPE': () => ({ status: 404, error: '推荐码无效' }),
        'POST /api/signup/applications': receipt('SQ-3', 'pending'),
      },
      '/apply?ref=NOPE',
    );
    expect(await screen.findByTestId('referral-invalid')).toHaveTextContent('仍可以直接提交申请');

    await fillRequired(user);
    await user.click(screen.getByRole('button', { name: '提交申请' }));
    await screen.findByTestId('application-no');
    const body = calls.find((call) => call.url === '/api/signup/applications')?.body as Record<string, unknown>;
    expect(body).not.toHaveProperty('ref');
  });

  test('直接注册模式：提示注册链接已发往邮箱', async () => {
    const user = userEvent.setup();
    setup(
      {
        'GET /api/signup/referral/REF123': { code: 'REF123', referrer_name: '李四', require_approval: true },
        'POST /api/signup/applications': receipt('SQ-4', 'approved'),
      },
      '/apply?ref=REF123',
    );
    await screen.findByTestId('referral-by');
    await fillRequired(user);
    await user.click(screen.getByRole('button', { name: '提交申请' }));
    await waitFor(() => expect(screen.getByText(/注册链接已发到你的邮箱/)).toBeInTheDocument());
  });
});
