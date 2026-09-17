import { ApiError } from '../api/client';
import type { ImportStartResult } from '../api/types';

const SESSION_EXPIRED_STATUS = 404;

export const isSessionExpired = (error: unknown): boolean =>
  error instanceof ApiError && error.status === SESSION_EXPIRED_STATUS;

export interface SessionKeeper {
  /** 返回当前会话 id；尚无会话时开始一个（并发调用共用同一个请求）。 */
  ensure: () => Promise<string>;
  /** 会话过期后重新开始；多个上传同时发现同一会话过期时只重开一次。 */
  renew: (expiredId: string) => Promise<string>;
  currentId: () => string | null;
  clear: () => void;
}

/** 管理分文件导入的会话 id（IO 句柄，非渲染状态）。 */
export function createSessionKeeper(start: () => Promise<ImportStartResult>, onRenewed: () => void): SessionKeeper {
  let pending: Promise<string> | null = null;
  let sessionId: string | null = null;
  let generation = 0;

  const ensure = () => {
    if (pending) return pending;
    const startedIn = generation;
    const request = start().then(({ session_id }) => {
      if (startedIn === generation) sessionId = session_id;
      return session_id;
    });
    pending = request.catch((error: unknown) => {
      if (startedIn === generation) pending = null;
      throw error;
    });
    return pending;
  };

  const clear = () => {
    generation += 1;
    pending = null;
    sessionId = null;
  };

  const renew = (expiredId: string) => {
    if (sessionId === expiredId) {
      clear();
      onRenewed();
    }
    return ensure();
  };

  return { ensure, renew, currentId: () => sessionId, clear };
}
