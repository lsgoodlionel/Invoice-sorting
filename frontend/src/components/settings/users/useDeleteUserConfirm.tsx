import { Text } from '@mantine/core';
import { modals } from '@mantine/modals';
import { notifications } from '@mantine/notifications';
import type { UseMutationResult } from '@tanstack/react-query';
import { errorMessage } from '../../../api/client';
import type { DeletedUser, User } from '../../../api/types';

/** account：单账套，真正删除账号；tenant：多账套，把此人移出账套。 */
export type DeleteScope = 'account' | 'tenant';

export interface DeleteCopyOptions {
  scope: DeleteScope;
  /** 多账套文案里的账套称呼，默认“本账套” */
  tenantLabel?: string;
}

const KEEP_HISTORY = '其上传与操作记录仍保留并显示原姓名';

interface DeleteCopy {
  title: string;
  body: string;
  confirm: string;
  done: string;
}

export function deleteCopy(name: string, { scope, tenantLabel = '本账套' }: DeleteCopyOptions): DeleteCopy {
  if (scope === 'account') {
    return {
      title: `删除用户「${name}」？`,
      body: `删除后无法登录，用户名可再次使用；${KEEP_HISTORY}。`,
      confirm: '删除',
      done: `已删除「${name}」`,
    };
  }
  return {
    title: `将「${name}」移出${tenantLabel}？`,
    body: `将此人移出${tenantLabel}：之后无法再进入${tenantLabel}，${KEEP_HISTORY}。若他不再属于任何账套，账号会一并删除，用户名可再次使用。`,
    confirm: '移出',
    done: `已将「${name}」移出${tenantLabel}`,
  };
}

type DeleteMutation = UseMutationResult<DeletedUser, Error, number>;

/** 删除（移出）前二次确认；成功与失败都给出提示，失败时展示后端原文（如“最后一名管理员”）。 */
export function useDeleteUserConfirm(mutation: DeleteMutation, options: DeleteCopyOptions) {
  return (user: User) => {
    const copy = deleteCopy(user.display_name, options);
    modals.openConfirmModal({
      title: copy.title,
      children: <Text size="sm">{copy.body}</Text>,
      labels: { confirm: copy.confirm, cancel: '取消' },
      confirmProps: { color: 'red' },
      onConfirm: () =>
        mutation.mutate(user.id, {
          onSuccess: () => notifications.show({ color: 'ink', message: copy.done }),
          onError: (error) => notifications.show({ color: 'red', title: '操作未完成', message: errorMessage(error) }),
        }),
    });
  };
}
