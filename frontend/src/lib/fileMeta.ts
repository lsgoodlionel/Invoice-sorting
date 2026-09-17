// 文件展示辅助：大小、类型、中间省略的文件名。

export type FileTypeKind = 'pdf' | 'image' | 'xml' | 'other';

const KB = 1024;
const MB = KB * 1024;
const IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'webp', 'heic', 'gif', 'bmp'];

export function formatFileSize(bytes: number): string {
  if (bytes < KB) return `${Math.max(0, bytes)} B`;
  if (bytes < MB) return `${(bytes / KB).toFixed(1)} KB`;
  return `${(bytes / MB).toFixed(1)} MB`;
}

function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot < 0 ? '' : name.slice(dot + 1).toLowerCase();
}

export function fileTypeOf(name: string, mime = ''): FileTypeKind {
  const extension = extensionOf(name);
  if (extension === 'pdf') return 'pdf';
  if (extension === 'xml') return 'xml';
  if (IMAGE_EXTENSIONS.includes(extension) || mime.startsWith('image/')) return 'image';
  return 'other';
}

/** 超过 maxChars 个字符时保留首尾、中间用省略号，便于看到扩展名与日期后缀。 */
export function middleEllipsis(name: string, maxChars: number): string {
  const chars = Array.from(name);
  if (chars.length <= maxChars) return name;
  const head = Math.ceil(maxChars / 2);
  const tail = Math.floor(maxChars / 2);
  return `${chars.slice(0, head).join('')}…${chars.slice(chars.length - tail).join('')}`;
}
