import { vi } from 'vitest';

interface ProgressLike {
  loaded: number;
  total: number;
  lengthComputable: boolean;
}

/** 可控的假 XMLHttpRequest：测试中手动触发进度、响应、网络错误。 */
export class FakeXhr {
  static instances: FakeXhr[] = [];

  method = '';
  url = '';
  body: unknown = null;
  headers: Record<string, string> = {};
  status = 0;
  responseText = '';
  isAborted = false;
  upload: { onprogress: ((event: ProgressLike) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;

  constructor() {
    FakeXhr.instances = [...FakeXhr.instances, this];
  }

  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }

  setRequestHeader(name: string, value: string) {
    this.headers = { ...this.headers, [name]: value };
  }

  send(body: unknown) {
    this.body = body;
  }

  abort() {
    this.isAborted = true;
    this.onabort?.();
  }

  emitProgress(loaded: number, total: number, lengthComputable = true) {
    this.upload.onprogress?.({ loaded, total, lengthComputable });
  }

  respond(status: number, body: unknown) {
    this.status = status;
    this.responseText = typeof body === 'string' ? body : JSON.stringify(body);
    this.onload?.();
  }

  failNetwork() {
    this.onerror?.();
  }
}

export function installFakeXhr(): typeof FakeXhr {
  FakeXhr.instances = [];
  vi.stubGlobal('XMLHttpRequest', FakeXhr);
  return FakeXhr;
}

export const lastXhr = (): FakeXhr => {
  const xhr = FakeXhr.instances.at(-1);
  if (!xhr) throw new Error('没有发出 XMLHttpRequest');
  return xhr;
};
