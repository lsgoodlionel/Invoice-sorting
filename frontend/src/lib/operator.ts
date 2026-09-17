import type { StatusEvent, UserRef } from '../api/types';

// 上传人/操作人展示文案（契约 0.3）。

export const INBOX_LABEL = '收件箱';
export const SYSTEM_LABEL = '系统';

/** 附件上传人：null 表示收件箱自动导入。 */
export function uploaderName(ref: UserRef | null): string {
  return ref?.display_name ?? INBOX_LABEL;
}

/** 时间线操作人：无操作人的自动变化显示“系统”，手动且无操作人（关闭认证）不显示。 */
export function eventActorLabel(event: Pick<StatusEvent, 'actor' | 'is_manual'>): string | null {
  if (event.actor) return event.actor.display_name;
  return event.is_manual ? null : SYSTEM_LABEL;
}
