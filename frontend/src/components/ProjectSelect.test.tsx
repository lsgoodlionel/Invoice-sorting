import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, test, vi } from 'vitest';
import type { Project } from '../api/types';
import { mockFetch } from '../test/fetchMock';
import { makeProject } from '../test/fixtures';
import { renderWithProviders } from '../test/render';
import { ProjectSelect } from './ProjectSelect';

function Harness({ onChange, creatable }: { onChange: (id: number | null) => void; creatable?: boolean }) {
  const [value, setValue] = useState<number | null>(null);
  return (
    <ProjectSelect
      label="经费项目"
      creatable={creatable}
      value={value}
      onChange={(id) => {
        setValue(id);
        onChange(id);
      }}
    />
  );
}

function setupRoutes() {
  let projects: Project[] = [];
  const created = makeProject({ id: 9, code: 'KY-09', name: '科研B', owner: '张老师' });
  const mock = mockFetch({
    'GET /api/projects': () => ({ data: projects }),
    'POST /api/projects': () => {
      projects = [...projects, created];
      return { data: created };
    },
    'GET /api/expenses': { items: [], total: 0, total_cents: 0, status_counts: {} },
  });
  return mock;
}

describe('ProjectSelect', () => {
  test('shows create entry when there are no projects and uses the creatable placeholder', async () => {
    const user = userEvent.setup();
    setupRoutes();
    renderWithProviders(<Harness onChange={vi.fn()} />);
    const input = screen.getByRole('combobox', { name: '经费项目' });
    expect(input).toHaveAttribute('placeholder', '选择经费项目（可新建）');
    await user.click(input);
    expect(await screen.findByRole('option', { name: /新建经费项目/ })).toBeInTheDocument();
  });

  test('creates a project and selects it automatically', async () => {
    const user = userEvent.setup();
    const { calls } = setupRoutes();
    const onChange = vi.fn();
    renderWithProviders(<Harness onChange={onChange} />);
    await user.click(screen.getByRole('combobox', { name: '经费项目' }));
    await user.click(await screen.findByRole('option', { name: /新建经费项目/ }));
    await user.type(await screen.findByLabelText('经费号'), 'KY-09');
    await user.type(screen.getByLabelText(/名称/), ' 科研B ');
    await user.type(screen.getByLabelText('负责人'), '张老师');
    await user.click(screen.getByRole('button', { name: '创建并选中' }));

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(9));
    const post = calls.find((call) => call.method === 'POST' && call.url === '/api/projects');
    expect(post?.body).toEqual({ code: 'KY-09', name: '科研B', owner: '张老师' });
    expect(onChange).not.toHaveBeenCalledWith(expect.any(String));
    await waitFor(() => expect(screen.getByRole('combobox', { name: '经费项目' })).toHaveValue('KY-09 科研B'));
  });

  test('hides the create entry when not creatable', async () => {
    const user = userEvent.setup();
    setupRoutes();
    renderWithProviders(<Harness onChange={vi.fn()} creatable={false} />);
    await user.click(screen.getByRole('combobox', { name: '经费项目' }));
    expect(screen.queryByRole('option', { name: /新建经费项目/ })).not.toBeInTheDocument();
  });
});
