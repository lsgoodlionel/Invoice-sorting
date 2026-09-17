import { IconFile, IconFileTypePdf, IconFileTypeXml, IconPhoto } from '@tabler/icons-react';
import { fileTypeOf, type FileTypeKind } from '../../../lib/fileMeta';

const ICONS: Record<FileTypeKind, typeof IconFile> = {
  pdf: IconFileTypePdf,
  image: IconPhoto,
  xml: IconFileTypeXml,
  other: IconFile,
};

const LABELS: Record<FileTypeKind, string> = { pdf: 'PDF', image: '图片', xml: 'XML', other: '文件' };

export function FileTypeIcon({ name, mime }: { name: string; mime?: string }) {
  const kind = fileTypeOf(name, mime);
  const Icon = ICONS[kind];
  return <Icon size={18} stroke={1.5} aria-label={LABELS[kind]} role="img" color="var(--ink-muted)" />;
}
