import { Group, Stack, Text } from '@mantine/core';
import { Dropzone } from '@mantine/dropzone';
import { IconFileInvoice, IconUpload, IconX } from '@tabler/icons-react';
import { ACCEPTED_FILE_TYPES } from '../UploadDrop';

interface ImportDropzoneProps {
  onFiles: (files: File[]) => void;
  isLoading: boolean;
  inboxDir?: string;
}

export function ImportDropzone({ onFiles, isLoading, inboxDir }: ImportDropzoneProps) {
  return (
    <Dropzone
      onDrop={onFiles}
      loading={isLoading}
      multiple
      accept={ACCEPTED_FILE_TYPES}
      className="import-dropzone"
      aria-label="拖入发票与附件"
    >
      <Stack align="center" gap={6} py={36} style={{ pointerEvents: 'none' }}>
        <Dropzone.Accept><IconUpload size={40} stroke={1.3} color="var(--accent)" /></Dropzone.Accept>
        <Dropzone.Reject><IconX size={40} stroke={1.3} color="var(--mantine-color-red-6)" /></Dropzone.Reject>
        <Dropzone.Idle><IconFileInvoice size={40} stroke={1.3} /></Dropzone.Idle>
        <Text size="lg" fw={600}>将发票、订单截图、支付记录拖到这里</Text>
        <Group gap={4}>
          <Text size="sm" c="dimmed">支持 PDF / OFD / XML / 图片，可多选；或点击选择文件</Text>
        </Group>
        {inboxDir && (
          <Text size="xs" c="dimmed">
            也可以直接把文件放进收件箱：<span className="num">{inboxDir}</span>
          </Text>
        )}
      </Stack>
    </Dropzone>
  );
}
