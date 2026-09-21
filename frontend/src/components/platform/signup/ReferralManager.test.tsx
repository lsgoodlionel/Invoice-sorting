import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import { mockFetch, type RecordedCall } from '../../../test/fetchMock';
import { renderWithProviders } from '../../../test/render';
import { SIGNUP_SETTINGS, makeReferral } from '../../../test/signupFixtures';
import { ReferralManager } from './ReferralManager';

type Routes = Record<string, unknown>;

const PAGE = { items: [makeReferral()], total: 1, page: 1, page_size: 20 };

function setup(extra: Routes = {}) {
  const result = mockFetch({
    'GET /api/platform/referrals': PAGE,
    'GET /api/platform/signup-settings': SIGNUP_SETTINGS,
    ...extra,
  });
  renderWithProviders(<ReferralManager />);
  return result;
}

const findCall = (calls: RecordedCall[], method: string, url: string) =>
  calls.find((call) => call.method === method && call.url === url);

describe('推荐记录', () => {
  test('显示推荐人账号与显示名、被推荐人邮箱、账套与结果', async () => {
    setup();
    const row = await screen.findByTestId('referral-row-1');
    expect(within(row).getByText('李四')).toBeInTheDocument();
    expect(within(row).getByText('lisi')).toBeInTheDocument();
    expect(within(row).getByText('wangwu@example.com')).toBeInTheDocument();
    expect(within(row).getByText('王五的账本（wangwu）')).toBeInTheDocument();
    expect(within(row).getByText('已注册')).toBeInTheDocument();
  });

  test('推荐资格已停用的推荐人有标记', async () => {
    setup({ 'GET /api/platform/referrals': { ...PAGE, items: [makeReferral({ is_referrer_disabled: true })] } });
    const row = await screen.findByTestId('referral-row-1');
    expect(within(row).getByText('推荐资格已停用')).toBeInTheDocument();
  });

  test('停用推荐资格需确认', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'PATCH /api/platform/referrers/7': { account_id: 7, is_disabled: true } });
    await user.click(await screen.findByRole('button', { name: '停用推荐资格：lisi' }));
    expect(await screen.findByText(/推荐链接立即失效/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '停用' }));

    await waitFor(() =>
      expect(findCall(calls, 'PATCH', '/api/platform/referrers/7')?.body).toEqual({ is_disabled: true }),
    );
  });

  test('已停用的推荐人可直接恢复', async () => {
    const user = userEvent.setup();
    const disabled = makeReferral({ is_referrer_disabled: true });
    const { calls } = setup({
      'GET /api/platform/referrals': { ...PAGE, items: [disabled] },
      'PATCH /api/platform/referrers/7': { account_id: 7, is_disabled: true },
    });
    await user.click(await screen.findByRole('button', { name: '恢复推荐资格：lisi' }));
    await waitFor(() =>
      expect(findCall(calls, 'PATCH', '/api/platform/referrers/7')?.body).toEqual({ is_disabled: false }),
    );
  });
});

describe('注册设置', () => {
  test('修改审批开关、每月名额与有效天数后保存', async () => {
    const user = userEvent.setup();
    const saved = { ...SIGNUP_SETTINGS, require_approval: false, monthly_referral_quota: 8, code_valid_days: 14 };
    const { calls } = setup({ 'PATCH /api/platform/signup-settings': saved });
    const save = await screen.findByRole('button', { name: '保存设置' });
    expect(save).toBeDisabled();

    await user.click(screen.getByText('直接注册'));
    const quota = screen.getByLabelText(/每月推荐名额/);
    await user.clear(quota);
    await user.type(quota, '8');
    const days = screen.getByLabelText(/注册码有效天数/);
    await user.clear(days);
    await user.type(days, '14');
    await user.click(save);

    await waitFor(() =>
      expect(findCall(calls, 'PATCH', '/api/platform/signup-settings')?.body).toEqual({
        require_approval: false,
        monthly_referral_quota: 8,
        code_valid_days: 14,
      }),
    );
    expect(await screen.findByText('注册设置已保存')).toBeInTheDocument();
  });

  test('未配置邮件服务时提示手动转告', async () => {
    setup({ 'GET /api/platform/signup-settings': { ...SIGNUP_SETTINGS, is_mail_configured: false } });
    expect(await screen.findByText(/未配置邮件服务/)).toBeInTheDocument();
  });
});
