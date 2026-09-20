import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test } from 'vitest';
import { mockFetch, type RecordedCall } from '../../test/fetchMock';
import { makePlan } from '../../test/platformFixtures';
import { renderWithProviders } from '../../test/render';
import { PlanManager } from './PlanManager';

type Routes = Record<string, unknown>;

const PLANS = [makePlan(), makePlan({ id: 2, code: 'free', name: '免费版', max_users: 0, max_storage_mb: 0, max_expenses_per_month: 0 })];

function setup(extra: Routes = {}) {
  const result = mockFetch({ 'GET /api/platform/plans': PLANS, ...extra });
  renderWithProviders(<PlanManager />);
  return result;
}

const findCall = (calls: RecordedCall[], method: string, url: string) =>
  calls.find((call) => call.method === method && call.url.split('?')[0] === url);

describe('套餐列表', () => {
  test('0 显示为不限', async () => {
    setup();

    const row = await screen.findByTestId('plan-row-free');
    expect(within(row).getAllByText('不限')).toHaveLength(3);
    expect(within(screen.getByTestId('plan-row-team')).getByText('2048')).toBeInTheDocument();
  });
});

describe('新建套餐', () => {
  test('提交代码与各项额度', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'POST /api/platform/plans': makePlan({ id: 3, code: 'pro' }) });
    await user.click(await screen.findByRole('button', { name: '新建套餐' }));
    const dialog = await screen.findByRole('dialog', { name: '新建套餐' });

    await user.type(within(dialog).getByLabelText('代码'), 'pro');
    await user.type(within(dialog).getByLabelText('名称'), '专业版');
    await user.clear(within(dialog).getByLabelText('用户数上限'));
    await user.type(within(dialog).getByLabelText('用户数上限'), '50');
    await user.click(within(dialog).getByRole('button', { name: '新建套餐' }));

    await waitFor(() =>
      expect(findCall(calls, 'POST', '/api/platform/plans')?.body).toEqual({
        code: 'pro',
        name: '专业版',
        max_users: 50,
        max_storage_mb: 0,
        max_expenses_per_month: 0,
      }),
    );
  });
});

describe('修改与删除套餐', () => {
  test('编辑时不显示代码字段', async () => {
    const user = userEvent.setup();
    const { calls } = setup({ 'PATCH /api/platform/plans/1': makePlan({ max_users: 20 }) });
    await user.click(within(await screen.findByTestId('plan-row-team')).getByRole('button', { name: '编辑套餐 team' }));
    const dialog = await screen.findByRole('dialog', { name: '编辑套餐：team' });

    expect(within(dialog).queryByLabelText('代码')).not.toBeInTheDocument();
    await user.clear(within(dialog).getByLabelText('用户数上限'));
    await user.type(within(dialog).getByLabelText('用户数上限'), '20');
    await user.click(within(dialog).getByRole('button', { name: '保存' }));

    await waitFor(() => expect(findCall(calls, 'PATCH', '/api/platform/plans/1')?.body).toMatchObject({ max_users: 20 }));
  });

  test('被账套使用时显示后端拒绝原因', async () => {
    const user = userEvent.setup();
    setup({ 'DELETE /api/platform/plans/1': () => ({ status: 409, error: '该套餐已被 2 个账套使用，请先改用其他套餐' }) });

    await user.click(within(await screen.findByTestId('plan-row-team')).getByRole('button', { name: '删除套餐 team' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('该套餐已被 2 个账套使用');
  });
});
