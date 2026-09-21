import { screen, waitFor } from '@testing-library/react';
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

describe('SettingsPage permissions', () => {
  test('admin sees user management and editable system settings', async () => {
    routes(AUTHENTICATED);
    renderWithProviders(<SettingsPage />);
    expect(await screen.findByTestId('user-row-2')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '保存设置' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '新增分类' })).toBeInTheDocument();
    expect(screen.queryByText('仅管理员可修改')).not.toBeInTheDocument();
  });

  test('member cannot see user management and system settings are read-only', async () => {
    const { calls } = routes(AUTHENTICATED_MEMBER);
    renderWithProviders(<SettingsPage />, { currentUser: { user: MEMBER_USER, isAdmin: false, authEnabled: true } });

    expect(await screen.findByDisplayValue('某大学')).toBeDisabled();
    expect(await screen.findByText('差旅')).toBeInTheDocument();
    expect(screen.queryByText('用户管理')).not.toBeInTheDocument();
    expect(screen.getAllByText('仅管理员可修改')).toHaveLength(3);
    for (const name of ['保存设置', '立即备份', '新增分类', '新增规则', '归档', '删除']) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
    }
    expect(screen.getAllByRole('button', { name: '编辑' })).toHaveLength(1);
    expect(screen.getByRole('button', { name: '新增项目' })).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: '修改密码' })).toBeInTheDocument();
    await waitFor(() => expect(calls.some((c) => c.url === '/api/checklist-rules')).toBe(true));
    expect(calls.some((c) => c.url === '/api/users')).toBe(false);
  });
});

describe('SettingsPage 推荐好友', () => {
  const MEMBER_CONTEXT = { user: MEMBER_USER, isAdmin: false, authEnabled: true };
  const mine = { code: 'REF1', link: null, is_disabled: false, require_approval: true, monthly_quota: 5, used_this_month: 0, total: 0, referrals: [] };

  test('多账套部署的登录用户能看到推荐好友', async () => {
    routes({ ...SAAS_AUTHENTICATED, user: MEMBER_USER }, { 'GET /api/referrals/me': mine });
    renderWithProviders(<SettingsPage />, { currentUser: MEMBER_CONTEXT });
    expect(await screen.findByText('推荐好友')).toBeInTheDocument();
    expect(await screen.findByLabelText('我的推荐链接')).toBeInTheDocument();
  });

  test('单账套部署没有推荐好友，也不请求推荐接口', async () => {
    const { calls } = routes(AUTHENTICATED_MEMBER);
    renderWithProviders(<SettingsPage />, { currentUser: MEMBER_CONTEXT });
    expect(await screen.findByRole('button', { name: '修改密码' })).toBeInTheDocument();
    expect(screen.queryByText('推荐好友')).not.toBeInTheDocument();
    expect(calls.some((c) => c.url.startsWith('/api/referrals'))).toBe(false);
  });
});
