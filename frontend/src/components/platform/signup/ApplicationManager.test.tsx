import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import { mockFetch, type RecordedCall } from '../../../test/fetchMock';
import { makePlan } from '../../../test/platformFixtures';
import { renderWithProviders } from '../../../test/render';
import { makeApplication, makeApplicationPage, makeReview } from '../../../test/signupFixtures';
import { ApplicationManager } from './ApplicationManager';

type Routes = Record<string, unknown>;

const REFERRED = makeApplication({
  id: 2,
  number: 'SQ000002',
  name: '赵六',
  email: 'zhaoliu@example.org',
  ledger_name: '赵六课题组',
  referrer: { account_id: 7, username: 'lisi', display_name: '李四' },
});

const APPROVED = makeApplication({ status: 'approved', reviewed_at: '2026-09-21T10:00:00+08:00' });
const NOTICE_TEXT = '张三：\n\n你提交的使用申请已通过。\n\n/register?code=REG-9\n';

function setup(extra: Routes = {}) {
  const result = mockFetch({
    'GET /api/platform/applications': makeApplicationPage([makeApplication(), REFERRED]),
    'GET /api/platform/plans': [makePlan()],
    ...extra,
  });
  renderWithProviders(<ApplicationManager />);
  return result;
}

const lastListCall = (calls: RecordedCall[]) => calls.filter((call) => call.url.startsWith('/api/platform/applications?')).at(-1);
const postTo = (calls: RecordedCall[], url: string) => calls.find((call) => call.method === 'POST' && call.url === url);

async function openDrawer(user: ReturnType<typeof userEvent.setup>, no: string) {
  await user.click(await screen.findByRole('button', { name: `查看申请 ${no}` }));
  return screen.findByTestId('application-details');
}

async function approveWithDefaults(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: '批准' }));
  const dialog = await screen.findByRole('dialog', { name: /批准申请/ });
  await user.click(within(dialog).getByRole('button', { name: '批准' }));
}

describe('申请列表', () => {
  test('默认只看待审批，显示推荐人', async () => {
    const { calls } = setup();
    const row = await screen.findByTestId('application-row-2');
    expect(within(row).getByText('李四')).toBeInTheDocument();
    expect(within(row).getByText('待审批')).toBeInTheDocument();
    expect(lastListCall(calls)?.url).toContain('status=pending');
  });

  test('切换状态与搜索都会回到第一页重新查询', async () => {
    const user = userEvent.setup();
    const { calls } = setup();
    await screen.findByTestId('application-row-1');

    await user.click(screen.getByText('全部'));
    await waitFor(() => expect(lastListCall(calls)?.url).not.toContain('status='));

    await user.click(screen.getByText('已否决'));
    await waitFor(() => expect(lastListCall(calls)?.url).toContain('status=rejected'));

    await user.type(screen.getByPlaceholderText('搜索姓名、邮箱或编号'), 'zhao');
    await waitFor(() => {
      expect(lastListCall(calls)?.url).toContain('q=zhao');
      expect(lastListCall(calls)?.url).toContain('page=1');
    });
  });

  test('详情抽屉显示全部资料与推荐人', async () => {
    const user = userEvent.setup();
    setup();
    const details = await openDrawer(user, 'SQ000002');
    expect(within(details).getByText('zhaoliu@example.org')).toBeInTheDocument();
    expect(within(details).getByText('课题组差旅报销，约 5 人使用')).toBeInTheDocument();
    expect(within(details).getByText('赵六课题组')).toBeInTheDocument();
    expect(within(details).getByText('由 李四（lisi）推荐')).toBeInTheDocument();
  });
});

describe('审批', () => {
  test('批准时可修改账套标识、名称、套餐与到期日', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'POST /api/platform/applications/1/approve': makeReview(APPROVED) });
    await openDrawer(user, 'SQ000001');
    await user.click(screen.getByRole('button', { name: '批准' }));

    const slug = await screen.findByLabelText(/账套标识/);
    expect(slug).toHaveValue('');
    expect(slug).toHaveAttribute('placeholder', 'zhang-san-xxxxxx');
    expect(screen.getByLabelText('账套名称')).toHaveValue('张三的账本');

    await user.type(slug, 'Bad Slug');
    expect(screen.getByText(/只能使用小写字母/)).toBeInTheDocument();
    await user.clear(slug);
    await user.type(slug, 'zs-lab');
    await user.clear(screen.getByLabelText('账套名称'));
    await user.type(screen.getByLabelText('账套名称'), '张三课题组');
    await user.click(screen.getByLabelText('套餐', { selector: 'input' }));
    await user.click(await screen.findByRole('option', { name: '团队版' }));
    await user.type(screen.getByLabelText(/到期日/), '2027-09-30');

    const dialog = screen.getByRole('dialog', { name: /批准申请/ });
    await user.click(within(dialog).getByRole('button', { name: '批准' }));

    await waitFor(() =>
      expect(postTo(calls, '/api/platform/applications/1/approve')?.body).toEqual({
        slug: 'zs-lab',
        name: '张三课题组',
        plan_code: 'team',
        expires_on: '2027-09-30',
      }),
    );
    expect(await screen.findByText('已批准，已发邮件通知申请人')).toBeInTheDocument();
    expect(screen.queryByTestId('manual-notice')).not.toBeInTheDocument();
  });

  test('标识留空时不传，由后端自动生成', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'POST /api/platform/applications/1/approve': makeReview(APPROVED) });
    await openDrawer(user, 'SQ000001');
    await approveWithDefaults(user);
    await waitFor(() =>
      expect(postTo(calls, '/api/platform/applications/1/approve')?.body).toEqual({ name: '张三的账本' }),
    );
  });

  test('否决可填原因', async () => {
    const user = userEvent.setup();
    const rejected = makeApplication({ status: 'rejected', mail_status: 'sent', reject_reason: '资料不全' });
    const { calls } = setup({ 'POST /api/platform/applications/1/reject': makeReview(rejected) });
    await openDrawer(user, 'SQ000001');
    await user.click(screen.getByRole('button', { name: '否决' }));
    await user.type(await screen.findByLabelText('原因（可选）'), '资料不全');
    const dialog = screen.getByRole('dialog', { name: /否决申请/ });
    await user.click(within(dialog).getByRole('button', { name: '否决' }));

    await waitFor(() => expect(postTo(calls, '/api/platform/applications/1/reject')?.body).toEqual({ reason: '资料不全' }));
    const details = await screen.findByTestId('application-details');
    await waitFor(() => expect(within(details).getByText('已否决')).toBeInTheDocument());
    expect(within(details).getByText('资料不全')).toBeInTheDocument();
  });

  test('未配置邮件时显示可复制的注册链接与通知文字，重新发信后消失', async () => {
    const user = userEvent.setup();
    const skipped = makeReview({ ...APPROVED, mail_status: 'skipped' }, {
      mail_status: 'skipped', link: '/register?code=REG-9', text: NOTICE_TEXT,
    });
    const { calls } = setup({
      'POST /api/platform/applications/1/approve': skipped,
      'POST /api/platform/applications/1/resend': makeReview({ ...APPROVED, mail_status: 'sent' }),
    });
    await openDrawer(user, 'SQ000001');
    await approveWithDefaults(user);

    const notice = await screen.findByTestId('manual-notice');
    const fullLink = `${window.location.origin}/register?code=REG-9`;
    expect(notice).toHaveTextContent('请手动转告申请人（zhang.san@example.com）');
    expect(within(notice).getByTestId('register-url')).toHaveTextContent(fullLink);
    expect(within(notice).getByLabelText('通知文字')).toHaveValue(NOTICE_TEXT.replace('/register?code=REG-9', fullLink));

    await user.click(within(notice).getByRole('button', { name: '复制注册链接' }));
    await expect(navigator.clipboard.readText()).resolves.toBe(fullLink);

    await user.click(screen.getByRole('button', { name: '重新发信' }));
    await waitFor(() => expect(screen.queryByTestId('manual-notice')).not.toBeInTheDocument());
    expect(postTo(calls, '/api/platform/applications/1/resend')).toBeDefined();
  });

  test('发送失败时显示原因', async () => {
    const user = userEvent.setup();
    const failed = makeReview({ ...APPROVED, mail_status: 'failed', mail_error: 'SMTP 连接超时' }, {
      mail_status: 'failed', mail_error: 'SMTP 连接超时', link: 'https://fp.test/register?code=C', text: '通过',
    });
    setup({ 'POST /api/platform/applications/1/approve': failed });
    await openDrawer(user, 'SQ000001');
    await approveWithDefaults(user);
    const notice = await screen.findByTestId('manual-notice');
    expect(notice).toHaveTextContent('通知邮件发送失败');
    expect(notice).toHaveTextContent('SMTP 连接超时');
    expect(within(notice).getByTestId('register-url')).toHaveTextContent('https://fp.test/register?code=C');
  });

  test('之前未送达的申请提示可重新发信换发链接', async () => {
    const user = userEvent.setup();
    const earlier = makeApplication({ status: 'approved', mail_status: 'skipped' });
    setup({ 'GET /api/platform/applications': makeApplicationPage([earlier]) });
    await openDrawer(user, 'SQ000001');
    expect(screen.getByText(/上次通知没有送达申请人/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新发信' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '批准' })).not.toBeInTheDocument();
  });

  test('已注册的申请不能重新发信', async () => {
    const user = userEvent.setup();
    const registered = makeApplication({ status: 'registered', mail_status: 'sent', tenant: { slug: 'zs', name: '张三的账本' } });
    setup({ 'GET /api/platform/applications': makeApplicationPage([registered]) });
    const details = await openDrawer(user, 'SQ000001');
    expect(within(details).getByText('张三的账本（zs）已开通')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重新发信' })).not.toBeInTheDocument();
  });
});
