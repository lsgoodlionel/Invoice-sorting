import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import { AUTHENTICATED, AUTHENTICATED_MEMBER, MEMBER_USER, SAAS_AUTHENTICATED } from '../test/authStatus';
import { mockFetch } from '../test/fetchMock';
import { makeProject, makeUser } from '../test/fixtures';
import { renderWithProviders } from '../test/render';
import { SettingsPage } from './SettingsPage';

const settings = {
  buyer_name: '某大学', buyer_tax_id: 'X1', overdue_days: 30, local_region: '上海',
  detail_platforms: [], data_dir: '/d', inbox_dir: '/d/收件箱',
};

const category = { id: 1, name: '差旅', color: '#1F5F4A', keywords: [], route_hint: '', sort: 1, archived: false };
const rule = { id: 1, category_id: null, attachment_kind: 'invoice', level: 'required', condition: {}, hint: '' };

function routes(status: unknown, extra: Record<string, unknown> = {}) {
  return mockFetch({
    ...extra,
    'GET /api/auth/status': status,
    'GET /api/settings': settings,
    'GET /api/categories': [category],
    'GET /api/projects': [makeProject()],
    'GET /api/checklist-rules': [rule],
    'GET /api/users': [makeUser()],
  });
}

const MEMBER_CONTEXT = { user: MEMBER_USER, isAdmin: false, authEnabled: true };

/** 侧栏导航里的分区按钮（窄屏下拉的同名 option 不算）。 */
const navButton = (name: string) => screen.queryByRole('button', { name });
const sectionTitle = (name: string) => screen.findByRole('heading', { level: 2, name });

describe('SettingsPage 分区导航', () => {
  test('默认显示「基本」，一次只渲染一个分区', async () => {
    routes(AUTHENTICATED);
    renderWithProviders(<SettingsPage />, { route: '/settings' });

    expect(await sectionTitle('基本')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: '保存设置' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '新增分类' })).not.toBeInTheDocument();
  });

  test('点击导航切换分区', async () => {
    const user = userEvent.setup();
    routes(AUTHENTICATED);
    renderWithProviders(<SettingsPage />, { route: '/settings' });

    await user.click(await screen.findByRole('button', { name: '用户管理' }));

    expect(await sectionTitle('用户管理')).toBeInTheDocument();
    expect(await screen.findByTestId('user-row-2')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '保存设置' })).not.toBeInTheDocument();
  });

  test('地址栏 ?section= 直达对应分区', async () => {
    routes(AUTHENTICATED);
    renderWithProviders(<SettingsPage />, { route: '/settings?section=categories' });

    expect(await sectionTitle('分类')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: '新增分类' })).toBeInTheDocument();
  });

  test('管理员能看到全部系统分区', async () => {
    routes(AUTHENTICATED);
    renderWithProviders(<SettingsPage />, { route: '/settings' });

    await sectionTitle('基本');
    for (const name of ['基本', '分类', '经费项目', '凭证清单规则', '分类整理', '用户管理', '登录与安全', '账本搬迁', '运行日志与诊断']) {
      expect(navButton(name)).toBeInTheDocument();
    }
  });
});

describe('SettingsPage permissions', () => {
  test('member does not see admin sections and system settings are read-only', async () => {
    const { calls } = routes(AUTHENTICATED_MEMBER);
    renderWithProviders(<SettingsPage />, { route: '/settings', currentUser: MEMBER_CONTEXT });

    expect(await screen.findByDisplayValue('某大学')).toBeDisabled();
    expect(screen.getByText('仅管理员可修改')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '保存设置' })).not.toBeInTheDocument();
    for (const name of ['用户管理', '分类整理', '账本搬迁', '运行日志与诊断']) {
      expect(navButton(name)).not.toBeInTheDocument();
    }
    expect(calls.some((c) => c.url === '/api/users')).toBe(false);
  });

  test('member cannot reach admin sections through the address bar', async () => {
    const { calls } = routes(AUTHENTICATED_MEMBER);
    renderWithProviders(<SettingsPage />, { route: '/settings?section=users', currentUser: MEMBER_CONTEXT });

    expect(await sectionTitle('基本')).toBeInTheDocument();
    expect(calls.some((c) => c.url === '/api/users')).toBe(false);
  });

  test('member can still manage projects and change own password', async () => {
    const user = userEvent.setup();
    routes(AUTHENTICATED_MEMBER);
    renderWithProviders(<SettingsPage />, { route: '/settings', currentUser: MEMBER_CONTEXT });

    await user.click(await screen.findByRole('button', { name: '经费项目' }));
    expect(await screen.findByRole('button', { name: '新增项目' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '登录与安全' }));
    expect(await screen.findByRole('button', { name: '修改密码' })).toBeInTheDocument();
  });

  test('member sees categories read-only', async () => {
    routes(AUTHENTICATED_MEMBER);
    renderWithProviders(<SettingsPage />, { route: '/settings?section=categories', currentUser: MEMBER_CONTEXT });

    expect(await screen.findByText('差旅')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '新增分类' })).not.toBeInTheDocument();
  });
});

describe('SettingsPage 推荐好友', () => {
  const mine = { code: 'REF1', link: null, is_disabled: false, require_approval: true, monthly_quota: 5, used_this_month: 0, total: 0, referrals: [] };

  test('多账套部署的登录用户能看到推荐好友', async () => {
    routes({ ...SAAS_AUTHENTICATED, user: MEMBER_USER }, { 'GET /api/referrals/me': mine });
    renderWithProviders(<SettingsPage />, { route: '/settings?section=referral', currentUser: MEMBER_CONTEXT });
    expect(await sectionTitle('推荐好友')).toBeInTheDocument();
    expect(await screen.findByLabelText('我的推荐链接')).toBeInTheDocument();
  });

  test('单账套部署没有推荐好友，也不请求推荐接口', async () => {
    const { calls } = routes(AUTHENTICATED_MEMBER);
    renderWithProviders(<SettingsPage />, { route: '/settings?section=referral', currentUser: MEMBER_CONTEXT });
    expect(await sectionTitle('基本')).toBeInTheDocument();
    expect(navButton('推荐好友')).not.toBeInTheDocument();
    expect(calls.some((c) => c.url.startsWith('/api/referrals'))).toBe(false);
  });
});
