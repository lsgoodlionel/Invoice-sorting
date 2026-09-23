import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import { mockFetch, type RecordedCall } from '../../../test/fetchMock';
import { UNCONFIGURED_MAIL, makeMailSettings } from '../../../test/mailFixtures';
import { renderWithProviders } from '../../../test/render';
import { MailSettingsManager } from './MailSettingsManager';

type Routes = Record<string, unknown>;

const PATH = '/api/platform/mail-settings';

function setup(settings = makeMailSettings(), extra: Routes = {}) {
  const result = mockFetch({ [`GET ${PATH}`]: settings, ...extra });
  renderWithProviders(<MailSettingsManager />);
  return result;
}

const lastCall = (calls: RecordedCall[], method: string, url: string) =>
  calls.filter((call) => call.method === method && call.url === url).at(-1);

async function pickOption(user: ReturnType<typeof userEvent.setup>, label: RegExp, option: string) {
  await user.click(screen.getByRole('combobox', { name: label }));
  await user.click(await screen.findByRole('option', { name: option }));
}

describe('邮件设置表单', () => {
  test('环境变量只配了一半时显示后端给出的提醒', async () => {
    setup(makeMailSettings({ warning: '服务器环境变量只配置了 SMTP_HOST 与 SMTP_FROM 中的一项' }));

    expect(await screen.findByText(/只配置了 SMTP_HOST 与 SMTP_FROM 中的一项/)).toBeInTheDocument();
  });

  test('选择常用邮箱预设只填服务器参数', async () => {
    const user = userEvent.setup();
    const { calls } = setup(UNCONFIGURED_MAIL, { [`PATCH ${PATH}`]: makeMailSettings() });
    await screen.findByLabelText('SMTP 服务器');

    await pickOption(user, /常用邮箱/, 'Gmail');
    expect(screen.getByLabelText('SMTP 服务器')).toHaveValue('smtp.gmail.com');
    expect(screen.getByLabelText('端口')).toHaveValue('587');
    await user.type(screen.getByLabelText('发件人'), 'me@gmail.com');
    await user.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() => expect(lastCall(calls, 'PATCH', PATH)?.body).toMatchObject({
      host: 'smtp.gmail.com', port: 587, tls: 'starttls', sender: 'me@gmail.com', username: '',
    }));
    expect(lastCall(calls, 'PATCH', PATH)?.body).not.toHaveProperty('password');
  });

  test('切换加密方式时端口随之变为默认值', async () => {
    const user = userEvent.setup();
    setup();
    await screen.findByLabelText('SMTP 服务器');

    await pickOption(user, /加密方式/, 'STARTTLS（常用 587）');
    expect(screen.getByLabelText('端口')).toHaveValue('587');
    await pickOption(user, /加密方式/, 'SSL/TLS（常用 465）');
    expect(screen.getByLabelText('端口')).toHaveValue('465');
  });

  test('已设置的密码显示“留空不修改”，可清除', async () => {
    const user = userEvent.setup();
    const { calls } = setup(makeMailSettings(), { [`PATCH ${PATH}`]: makeMailSettings({ password_set: false }) });
    const password = await screen.findByLabelText(/密码 \/ 授权码/);
    expect(password).toHaveAttribute('placeholder', '已设置，留空不修改');
    expect(screen.getByText(/授权码/, { selector: 'p' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '清除' }));
    expect(screen.getByText('保存后将清除已保存的密码。')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() => expect(lastCall(calls, 'PATCH', PATH)?.body).toMatchObject({ password: '' }));
  });

  test('填写新密码后随保存提交', async () => {
    const user = userEvent.setup();
    const { calls } = setup(makeMailSettings(), { [`PATCH ${PATH}`]: makeMailSettings() });
    await user.type(await screen.findByLabelText(/密码 \/ 授权码/), 'auth-code-1');
    await user.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() => expect(lastCall(calls, 'PATCH', PATH)?.body).toMatchObject({ password: 'auth-code-1' }));
  });

  test('「使用当前地址」填入站点地址', async () => {
    const user = userEvent.setup();
    setup(UNCONFIGURED_MAIL);
    await user.click(await screen.findByRole('button', { name: '使用当前地址' }));
    expect(screen.getByLabelText('站点地址')).toHaveValue(window.location.origin);
  });

  test('填写通知接收邮箱后随保存提交', async () => {
    const user = userEvent.setup();
    const { calls } = setup(makeMailSettings(), { [`PATCH ${PATH}`]: makeMailSettings() });
    const field = await screen.findByLabelText('通知接收邮箱');

    await user.clear(field);
    await user.type(field, 'ops@example.com,boss@example.com');
    await user.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() =>
      expect(lastCall(calls, 'PATCH', PATH)?.body).toMatchObject({ notify_emails: 'ops@example.com,boss@example.com' }));
    expect(screen.getByText(/多个用英文逗号分隔/)).toBeInTheDocument();
  });

  test('密码无法解密时提示重新填写', async () => {
    setup(makeMailSettings({ password_error: 'SMTP 密码无法解密，请重新填写 SMTP 密码' }));
    expect(await screen.findByText(/请重新填写 SMTP 密码/)).toBeInTheDocument();
  });
});

describe('测试连接与测试邮件', () => {
  test('测试连接成功后显示结果', async () => {
    const user = userEvent.setup();
    const { calls } = setup(makeMailSettings(), {
      [`POST ${PATH}/test-connection`]: { ok: true, category: 'ok', message: '连接并登录成功', checked_at: '2026-09-21T10:00:00+08:00' },
    });
    await user.click(await screen.findByRole('button', { name: '测试连接' }));

    const result = await screen.findByTestId('mail-last-check');
    expect(result).toHaveTextContent('测试连接 · 成功');
    expect(result).toHaveTextContent('连接并登录成功');
    expect(lastCall(calls, 'POST', `${PATH}/test-connection`)).toBeDefined();
  });

  test('发送测试邮件失败时直接展示原因', async () => {
    const user = userEvent.setup();
    const { calls } = setup(makeMailSettings(), {
      [`POST ${PATH}/test-email`]: { ok: false, category: 'auth', message: '邮件服务器登录失败，请检查 SMTP 用户名与密码配置', checked_at: null },
    });
    const send = await screen.findByRole('button', { name: '发送测试邮件' });
    expect(send).toBeDisabled();
    await user.type(screen.getByLabelText('测试收件地址'), 'me@example.org');
    await user.click(send);

    const result = await screen.findByRole('alert');
    expect(result).toHaveTextContent('认证失败');
    expect(result).toHaveTextContent('邮件服务器登录失败');
    expect(lastCall(calls, 'POST', `${PATH}/test-email`)?.body).toEqual({ to: 'me@example.org' });
  });

  test('限流等接口错误显示后端文案', async () => {
    const user = userEvent.setup();
    setup(makeMailSettings(), {
      [`POST ${PATH}/test-connection`]: () => ({ status: 429, error: '测试过于频繁，请 1 分钟后再试' }),
    });
    await user.click(await screen.findByRole('button', { name: '测试连接' }));
    expect(await screen.findByText('测试过于频繁，请 1 分钟后再试')).toBeInTheDocument();
  });

  test('有未保存的修改时不能测试', async () => {
    const user = userEvent.setup();
    setup();
    await user.type(await screen.findByLabelText('SMTP 服务器'), 'x');
    expect(screen.getByRole('button', { name: '测试连接' })).toBeDisabled();
    expect(screen.getByText(/保存后再测试/)).toBeInTheDocument();
  });

  test('显示最近一次验证结果与时间', async () => {
    setup(makeMailSettings({
      last_check: { kind: 'email', ok: false, category: 'timeout', message: '连接邮件服务器超时', checked_at: '2026-09-20T08:30:00+08:00', checked_by: 'ops-admin' },
    }));
    const last = await screen.findByTestId('mail-last-check');
    expect(last).toHaveTextContent('测试邮件 · 连接超时');
    expect(last).toHaveTextContent('2026-09-20 08:30');
    expect(last).toHaveTextContent('ops-admin');
  });
});

describe('环境变量配置', () => {
  test('整个表单只读并说明来源，没有保存按钮，仍可测试', async () => {
    setup(makeMailSettings({ source: 'env', updated_at: null }));
    expect(await screen.findByText(/由服务器环境变量配置/)).toBeInTheDocument();
    expect(screen.getByLabelText('SMTP 服务器')).toBeDisabled();
    expect(screen.getByLabelText('发件人')).toBeDisabled();
    expect(screen.queryByRole('button', { name: '保存' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '使用当前地址' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '清除' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '测试连接' })).toBeEnabled();
  });
});

describe('未配置', () => {
  test('提示未配置且测试按钮不可用', async () => {
    setup(UNCONFIGURED_MAIL);
    expect(await screen.findByText(/尚未配置邮件/)).toBeInTheDocument();
    const panel = screen.getByText(/填写 SMTP 服务器与发件人并保存后即可测试/).parentElement!;
    expect(within(panel).getByRole('button', { name: '测试连接' })).toBeDisabled();
  });
});
