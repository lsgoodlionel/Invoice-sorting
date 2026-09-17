import { Box, Image, Text } from '@mantine/core';
import type { Attachment } from '../api/types';

interface AttachmentPreviewProps {
  attachment: Attachment;
  height?: number;
}

const DEFAULT_HEIGHT = 420;

export function AttachmentPreview({ attachment, height = DEFAULT_HEIGHT }: AttachmentPreviewProps) {
  if (attachment.mime.startsWith('image/')) {
    return <Image src={attachment.url} alt={attachment.original_name} mah={height} fit="contain" />;
  }
  if (attachment.mime === 'application/pdf') {
    return (
      <Box component="object" data={attachment.url} type="application/pdf" w="100%" h={height} aria-label={attachment.original_name}>
        <Text size="sm">
          无法内嵌预览，<a href={attachment.url} target="_blank" rel="noreferrer">在新窗口打开</a>
        </Text>
      </Box>
    );
  }
  return (
    <Text size="sm" c="dimmed">
      该格式不支持预览，<a href={attachment.url} target="_blank" rel="noreferrer">打开文件</a>
    </Text>
  );
}
