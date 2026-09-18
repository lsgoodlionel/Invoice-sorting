import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test, vi } from 'vitest';
import { selectUploadStats, type UploadItem } from '../../../lib/uploadQueue';
import { renderWithProviders } from '../../../test/render';
import { UploadPanel, type UploadPanelProps } from './UploadPanel';

const item = (id: string, overrides: Partial<UploadItem> = {}): UploadItem => {
  const name = overrides.name ?? `${id}.pdf`;
  return {
    id, file: new File(['x'], name), name, size: 2048, phase: 'waiting', progress: 0,
    recognizedAs: '', message: '', attachmentId: null, existingExpenseId: null, ...overrides,
  };
};

const items: UploadItem[] = [
  item('w', { name: '等待.pdf' }),
  item('u', { name: '上传.pdf', phase: 'uploading', progress: 42 }),
  item('p', { name: '识别.png', phase: 'processing', progress: 100 }),
  item('d', { name: '完成.pdf', phase: 'done', progress: 100, recognizedAs: '发票', message: '无法识别发票内容，已作为附件导入', attachmentId: 3 }),
  item('dup', { name: '重复.xml', phase: 'duplicate', progress: 100, message: '发票号码重复', existingExpenseId: 7 }),
  item('e', { name: '失败.ofd', phase: 'error', message: '无法解析' }),
  item('c', { name: '取消.pdf', phase: 'cancelled' }),
];

function renderPanel(overrides: Partial<UploadPanelProps> = {}) {
  const list = overrides.items ?? items;
  const props: UploadPanelProps = {
    items: list,
    stats: selectUploadStats({ items: list }),
    overallProgress: 58,
    isSettled: false,
    isFinishing: false,
    finishError: null,
    onRetry: vi.fn(),
    onCancel: vi.fn(),
    onClear: vi.fn(),
    onRefinish: vi.fn(),
    ...overrides,
  };
  renderWithProviders(<UploadPanel {...props} />);
  return props;
}

const row = (name: string) => screen.getByRole('listitem', { name });

describe('UploadPanel', () => {
  test('summary text and overall progress while importing', () => {
    renderPanel();
    expect(screen.getByText('正在导入 7 个文件 · 已完成 1 · 重复 1 · 失败 1 · 已取消 1')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: '整体导入进度' })).toHaveAttribute('aria-valuenow', '58');
    expect(screen.queryByRole('button', { name: '清空列表' })).not.toBeInTheDocument();
  });

  test('each row shows a textual status', () => {
    renderPanel();
    expect(screen.getByRole('list', { name: '导入文件列表' })).toBeInTheDocument();
    expect(within(row('等待.pdf')).getByText('等待中')).toBeInTheDocument();
    expect(within(row('等待.pdf')).getByText('2.0 KB')).toBeInTheDocument();

    expect(within(row('上传.pdf')).getByText('上传中 42%')).toBeInTheDocument();
    expect(within(row('上传.pdf')).getByRole('progressbar', { name: '上传.pdf 上传进度' })).toHaveAttribute('aria-valuenow', '42');

    expect(within(row('识别.png')).getByText('识别中…')).toBeInTheDocument();
    expect(within(row('识别.png')).getByRole('progressbar', { name: '识别.png 识别进度' })).toBeInTheDocument();

    expect(within(row('完成.pdf')).getByText('识别为：发票')).toBeInTheDocument();
    expect(within(row('完成.pdf')).getByText('无法识别发票内容，已作为附件导入')).toBeInTheDocument();

    const duplicate = row('重复.xml');
    expect(within(duplicate).getByText('已存在')).toBeInTheDocument();
    expect(within(duplicate).getByText('发票号码重复')).toBeInTheDocument();
    expect(within(duplicate).getByRole('link', { name: '查看 #7' })).toHaveAttribute('href', '/expenses?period=all&open=7');

    expect(within(row('失败.ofd')).getByText('失败：无法解析')).toBeInTheDocument();
    expect(within(row('取消.pdf')).getByText('已取消')).toBeInTheDocument();
  });

  test('cancel buttons only on active rows; retry on failed and cancelled rows', async () => {
    const user = userEvent.setup();
    const props = renderPanel();
    expect(screen.getAllByRole('button', { name: /^取消 / }).map((button) => button.getAttribute('aria-label'))).toEqual([
      '取消 等待.pdf', '取消 上传.pdf', '取消 识别.png',
    ]);
    await user.click(screen.getByRole('button', { name: '取消 上传.pdf' }));
    expect(props.onCancel).toHaveBeenCalledWith('u');

    expect(within(row('完成.pdf')).queryByRole('button')).not.toBeInTheDocument();
    await user.click(within(row('失败.ofd')).getByRole('button', { name: '重试 失败.ofd' }));
    expect(props.onRetry).toHaveBeenCalledWith('e');
    expect(within(row('取消.pdf')).getByRole('button', { name: '重试 取消.pdf' })).toBeInTheDocument();
  });

  test('long names are shortened in the middle with the full name in title', () => {
    const longName = '这是一个非常非常非常非常非常非常非常长的发票文件名称-2026年3月12日.pdf';
    renderPanel({ items: [item('l', { name: longName })] });
    const name = within(row(longName)).getByTitle(longName);
    expect(name.textContent).toContain('…');
  });

  test('settled summary, clear list, finishing and finish error states', async () => {
    const user = userEvent.setup();
    const settled = items.filter((entry) => !['waiting', 'uploading', 'processing'].includes(entry.phase));
    const props = renderPanel({ items: settled, isSettled: true, finishError: '分组失败' });
    expect(screen.getByText('导入完成：新增 1 · 重复 1 · 失败 1 · 已取消 1')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '清空列表' }));
    expect(props.onClear).toHaveBeenCalled();
    expect(screen.getByText('分组失败')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '重新分组' }));
    expect(props.onRefinish).toHaveBeenCalled();
  });

  test('shows grouping hint while finishing', () => {
    renderPanel({ items: [item('d', { phase: 'done', recognizedAs: '' })], isSettled: true, isFinishing: true });
    expect(screen.getByText('正在分组匹配…')).toBeInTheDocument();
    expect(screen.getByText('已导入')).toBeInTheDocument();
  });

  test('done row shows travel detail next to recognized type', () => {
    const ticket = item('t', { name: '车票.pdf', phase: 'done', progress: 100, recognizedAs: '往来交通凭证', recognizedDetail: '火车 G7123 · 上海虹桥 → 苏州园区' });
    renderPanel({ items: [ticket] });
    expect(screen.getByText('识别为：往来交通凭证 · 火车 G7123 · 上海虹桥 → 苏州园区')).toBeInTheDocument();
  });
});
