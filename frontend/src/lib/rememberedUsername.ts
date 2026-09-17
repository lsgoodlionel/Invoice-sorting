// 登录页记住上次成功登录的用户名；存储不可用（隐私模式、被禁用）时静默回退到默认值。
export const REMEMBERED_USERNAME_KEY = 'invoice-sorting:last-username';
export const DEFAULT_USERNAME = 'admin';

export function loadRememberedUsername(): string {
  try {
    return window.localStorage.getItem(REMEMBERED_USERNAME_KEY) || DEFAULT_USERNAME;
  } catch {
    return DEFAULT_USERNAME;
  }
}

export function saveRememberedUsername(username: string): void {
  try {
    window.localStorage.setItem(REMEMBERED_USERNAME_KEY, username);
  } catch {
    // 仅为便利功能，写入失败不影响登录
  }
}
