import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import type { MyReferrals } from '../../../api/signupTypes';
import { mockFetch } from '../../../test/fetchMock';
import { renderWithProviders } from '../../../test/render';
import { ReferralSection } from './ReferralSection';

const MINE: MyReferrals = {
  code: 'REF123',
  link: 'https://fapiao.example.com/apply?ref=REF123',
  is_disabled: false,
  require_approval: true,
  monthly_quota: 5,
  used_this_month: 0,
  total: 3,
  referrals: [
    { id: 3, email_masked: 'z***@example.com', status: 'registered', created_at: '2026-09-01T10:00:00+08:00', registered_at: null },
    { id: 2, email_masked: 'l***@example.org', status: 'pending', created_at: '2026-09-10T10:00:00+08:00', registered_at: null },
    { id: 1, email_masked: 'wangwu@example.net', status: 'rejected', created_at: '2026-09-12T10:00:00+08:00', registered_at: null },
  ],
};

function setup(routes: Record<string, unknown> = {}) {
  const result = mockFetch({ 'GET /api/referrals/me': MINE, ...routes });
  renderWithProviders(<ReferralSection />);
  return result;
}

describe('推荐好友', () => {
  test('显示推荐链接并一键复制', async () => {
    const user = userEvent.setup();
    setup();
    expect(await screen.findByLabelText('我的推荐链接')).toHaveValue(MINE.link);

    await user.click(screen.getByRole('button', { name: '复制链接' }));
    expect(await screen.findByRole('button', { name: '已复制' })).toBeInTheDocument();
    await expect(navigator.clipboard.readText()).resolves.toBe(MINE.link);
  });

  test('后端给的是站内路径时补上当前站点地址', async () => {
    setup({ 'GET /api/referrals/me': { ...MINE, link: '/apply?ref=REF123' } });
    expect(await screen.findByLabelText('我的推荐链接')).toHaveValue(`${window.location.origin}/apply?ref=REF123`);
  });

  test('被推荐人只显示脱敏邮箱与状态', async () => {
    setup();
    const rows = await screen.findAllByTestId('referral-invitee');
    expect(rows).toHaveLength(3);
    expect(within(rows[0]).getByText('z***@example.com')).toBeInTheDocument();
    expect(within(rows[0]).getByText('已注册')).toBeInTheDocument();
    expect(within(rows[1]).getByText('l***@example.org')).toBeInTheDocument();
    expect(within(rows[1]).getByText('待审批')).toBeInTheDocument();
    expect(within(rows[2]).getByText('w***@example.net')).toBeInTheDocument();
    expect(within(rows[2]).getByText('已否决')).toBeInTheDocument();
    expect(screen.queryByText('wangwu@example.net')).not.toBeInTheDocument();
    expect(screen.getByTestId('referral-summary')).toHaveTextContent('已推荐 3 人');
  });

  test('重置前二次确认，说明旧链接立即失效', async () => {
    const user = userEvent.setup();
    const next = { ...MINE, code: 'NEW456', link: 'https://fapiao.example.com/apply?ref=NEW456' };
    const { calls } = setup({ 'POST /api/referrals/me/reset': next });
    await user.click(await screen.findByRole('button', { name: '重置链接' }));

    expect(await screen.findByText(/旧链接会立即失效/)).toBeInTheDocument();
    expect(calls.some((call) => call.method === 'POST')).toBe(false);
    await user.click(screen.getByRole('button', { name: '重置' }));

    await waitFor(() => expect(screen.getByLabelText('我的推荐链接')).toHaveValue(next.link));
    expect(calls.filter((call) => call.url === '/api/referrals/me/reset')).toHaveLength(1);
  });

  test('取消确认不会重置', async () => {
    const user = userEvent.setup();
    const { calls } = setup();
    await user.click(await screen.findByRole('button', { name: '重置链接' }));
    await user.click(await screen.findByRole('button', { name: '取消' }));
    expect(calls.some((call) => call.url === '/api/referrals/me/reset')).toBe(false);
  });

  test('推荐资格被停用时显示说明，不再提供链接', async () => {
    setup({ 'GET /api/referrals/me': { ...MINE, is_disabled: true, code: null, link: null } });
    expect(await screen.findByTestId('referral-disabled')).toHaveTextContent('推荐资格已被平台停用');
    expect(screen.queryByLabelText('我的推荐链接')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重置链接' })).not.toBeInTheDocument();
  });

  test('直接注册模式显示本月名额', async () => {
    setup({ 'GET /api/referrals/me': { ...MINE, require_approval: false, used_this_month: 2 } });
    expect(await screen.findByText(/本月直接注册名额 2\/5/)).toBeInTheDocument();
  });

  test('还没有推荐记录时给出提示', async () => {
    setup({ 'GET /api/referrals/me': { ...MINE, total: 0, referrals: [] } });
    expect(await screen.findByText('还没有人通过你的链接申请。')).toBeInTheDocument();
  });
});
