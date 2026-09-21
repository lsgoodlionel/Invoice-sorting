import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { api } from '../client';
import type {
  Category,
  CategoryInput,
  ChecklistRule,
  ChecklistRuleInput,
  Project,
  ProjectInput,
  Settings,
  SettingsPatch,
} from '../types';
import { queryKeys } from './keys';

export const settingsApi = {
  get: () => api.get<Settings>('/settings'),
  update: (patch: SettingsPatch) => api.put<Settings>('/settings', patch),
  categories: () => api.get<Category[]>('/categories'),
  createCategory: (input: CategoryInput) => api.post<Category>('/categories', input),
  updateCategory: (id: number, patch: Partial<CategoryInput>) => api.patch<Category>(`/categories/${id}`, patch),
  archiveCategory: (id: number) => api.del<null>(`/categories/${id}`),
  projects: () => api.get<Project[]>('/projects'),
  createProject: (input: ProjectInput) => api.post<Project>('/projects', input),
  updateProject: (id: number, patch: Partial<ProjectInput & { active: boolean }>) =>
    api.patch<Project>(`/projects/${id}`, patch),
  deactivateProject: (id: number) => api.del<null>(`/projects/${id}`),
  rules: () => api.get<ChecklistRule[]>('/checklist-rules'),
  createRule: (input: ChecklistRuleInput) => api.post<ChecklistRule>('/checklist-rules', input),
  updateRule: (id: number, patch: Partial<ChecklistRuleInput>) => api.patch<ChecklistRule>(`/checklist-rules/${id}`, patch),
  removeRule: (id: number) => api.del<null>(`/checklist-rules/${id}`),
};

export const useSettings = () => useQuery({ queryKey: queryKeys.settings, queryFn: settingsApi.get });
export const useCategories = () => useQuery({ queryKey: queryKeys.categories, queryFn: settingsApi.categories });
export const useProjects = () => useQuery({ queryKey: queryKeys.projects, queryFn: settingsApi.projects });
export const useChecklistRules = () => useQuery({ queryKey: queryKeys.checklistRules, queryFn: settingsApi.rules });

function useConfigMutation<TVars, TResult>(key: QueryKey, fn: (vars: TVars) => Promise<TResult>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: key });
      await client.invalidateQueries({ queryKey: queryKeys.expenses });
    },
  });
}

export const useUpdateSettings = () => useConfigMutation(queryKeys.settings, settingsApi.update);

export const useSaveCategory = () =>
  useConfigMutation(queryKeys.categories, ({ id, input }: { id: number | null; input: CategoryInput }) =>
    id === null ? settingsApi.createCategory(input) : settingsApi.updateCategory(id, input),
  );
export const useArchiveCategory = () => useConfigMutation(queryKeys.categories, settingsApi.archiveCategory);

export const useSaveProject = () =>
  useConfigMutation(queryKeys.projects, ({ id, input }: { id: number | null; input: ProjectInput & { active?: boolean } }) =>
    id === null ? settingsApi.createProject(input) : settingsApi.updateProject(id, input),
  );
export const useDeactivateProject = () => useConfigMutation(queryKeys.projects, settingsApi.deactivateProject);

export const useSaveRule = () =>
  useConfigMutation(queryKeys.checklistRules, ({ id, input }: { id: number | null; input: ChecklistRuleInput }) =>
    id === null ? settingsApi.createRule(input) : settingsApi.updateRule(id, input),
  );
export const useRemoveRule = () => useConfigMutation(queryKeys.checklistRules, settingsApi.removeRule);
