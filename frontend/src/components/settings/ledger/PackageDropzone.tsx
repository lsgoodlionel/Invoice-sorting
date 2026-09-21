import { Stack, Text } from '@mantine/core';
import { Dropzone } from '@mantine/dropzone';
import { IconFileZip, IconUpload, IconX } from '@tabler/icons-react';

const ZIP_TYPES = {
  'application/zip': ['.zip'],
  'application/x-zip-compressed': ['.zip'],
};

interface PackageDropzoneProps {
  onFile: (file: File) => void;
  onReject: () => void;
  disabled: boolean;
}

/** 选择搬迁包：拖入或点选，只收一个 .zip。 */
export function PackageDropzone({ onFile, onReject, disabled }: PackageDropzoneProps) {
  return (
    <Dropzone
      onDrop={(files) => files[0] && onFile(files[0])}
      onReject={onReject}
      accept={ZIP_TYPES}
      multiple={false}
      disabled={disabled}
      className="import-dropzone"
      aria-label="选择账本搬迁包"
    >
      <Stack align="center" gap={4} py="lg" style={{ pointerEvents: 'none' }}>
        <Dropzone.Accept><IconUpload size={32} stroke={1.3} color="var(--accent)" /></Dropzone.Accept>
        <Dropzone.Reject><IconX size={32} stroke={1.3} color="var(--mantine-color-red-6)" /></Dropzone.Reject>
        <Dropzone.Idle><IconFileZip size={32} stroke={1.3} /></Dropzone.Idle>
        <Text size="sm" fw={600}>拖入账本搬迁包，或点击选择</Text>
        <Text size="xs" c="dimmed">只接受导出得到的 .zip 文件，单包不超过 2 GB</Text>
      </Stack>
    </Dropzone>
  );
}
