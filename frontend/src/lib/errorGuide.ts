import { ApiError } from '../api/client';

// 把请求失败翻译成“发生了什么、为什么、需要做什么”，供全局提示使用。

export type ErrorKind = 'stale' | 'network' | 'server' | 'input' | 'forbidden' | 'other';
export type ErrorAction = 'load' | 'save';

export interface ErrorGuide {
  kind: ErrorKind;
  title: string;
  message: string;
  /** 数据已在别处变更，应刷新相关列表 */
  shouldRefresh: boolean;
  /** 相同错误合并为一条提示 */
  dedupeKey: string;
}

const HTTP_BAD_REQUEST = 400;
const HTTP_FORBIDDEN = 403;
const HTTP_NOT_FOUND = 404;
const HTTP_CONFLICT = 409;
const HTTP_TOO_LARGE = 413;
const HTTP_UNPROCESSABLE = 422;
const HTTP_TOO_MANY = 429;
const HTTP_SERVER_ERROR = 500;
const STATUS_NETWORK = 0;

const STALE_HINT_NOT_FOUND = '可能已被删除，或已在其他页面、收件箱自动处理中变更。页面已自动刷新。';
const STALE_HINT_CONFLICT = '这通常是因为该数据刚在其他页面、另一个标签页或收件箱自动处理中被改动。页面已自动刷新，请确认最新状态后再操作。';
const NETWORK_HINT =
  '请确认发票账本服务仍在运行：本机运行时查看启动它的终端窗口；服务器上执行 sudo systemctl status invoice-sorting。服务恢复后页面会自动重试。';
const SERVER_HINT =
  '服务处理请求时出错，可以稍后重试；若反复出现，请查看服务日志（本机看终端输出，服务器执行 sudo journalctl -u invoice-sorting -n 50）并反馈。';
const FORBIDDEN_HINT = '该操作需要管理员权限，请联系管理员（admin）';
const TOO_LARGE_HINT = '单个文件不能超过 30MB，请压缩或拆分后再上传。';

function messageOf(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return '未知错误';
}

export function isStaleDataError(error: unknown): boolean {
  return error instanceof ApiError && (error.status === HTTP_NOT_FOUND || error.status === HTTP_CONFLICT);
}

function build(kind: ErrorKind, title: string, message: string, shouldRefresh = false): ErrorGuide {
  return { kind, title, message, shouldRefresh, dedupeKey: `${kind}:${title}:${message}` };
}

function describeApiError(error: ApiError, fallbackTitle: string): ErrorGuide {
  const original = error.message;
  if (error.status === STATUS_NETWORK) return build('network', '无法连接服务', `${original}。${NETWORK_HINT}`);
  if (error.status === HTTP_FORBIDDEN) return build('forbidden', '没有权限', FORBIDDEN_HINT);
  if (error.status === HTTP_NOT_FOUND) return build('stale', '数据已变更', `${original}。${STALE_HINT_NOT_FOUND}`, true);
  if (error.status === HTTP_CONFLICT) return build('stale', '数据已变更', `${original}。${STALE_HINT_CONFLICT}`, true);
  if (error.status === HTTP_TOO_LARGE) return build('input', '文件太大', TOO_LARGE_HINT);
  if (error.status === HTTP_BAD_REQUEST || error.status === HTTP_UNPROCESSABLE) {
    return build('input', '请检查填写内容', original);
  }
  if (error.status === HTTP_TOO_MANY) return build('input', '操作太频繁', original);
  if (error.status >= HTTP_SERVER_ERROR) return build('server', '服务内部错误', `${original}。${SERVER_HINT}`);
  return build('other', fallbackTitle, original);
}

export function describeError(error: unknown, action: ErrorAction): ErrorGuide {
  const fallbackTitle = action === 'load' ? '加载失败' : '操作未完成';
  if (error instanceof ApiError) return describeApiError(error, fallbackTitle);
  return build('other', fallbackTitle, messageOf(error));
}
