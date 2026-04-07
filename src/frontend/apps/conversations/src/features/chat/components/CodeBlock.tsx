import { useRef } from 'react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Icon, Text } from '@/components';
import { useClipboard } from '@/hook';

interface CopyCodeButtonProps {
  onCopy: () => void;
}

const CopyCodeButton = ({ onCopy }: CopyCodeButtonProps) => {
  const { t } = useTranslation();

  return (
    <Box
      as="button"
      onClick={onCopy}
      $css={`
        position: absolute;
        top: 8px;
        right: 8px;
        padding: 6px 10px;
        background: var(--c--contextuals--background--surface--primary);
        border: 0px solid var(--c--contextuals--border--semantic--neutral--tertiary);
        border-radius: 4px;
        cursor: pointer;
        font-size: 12px;
        border: 1px solid var(--c--contextuals--border--semantic--neutral--tertiary);
        font-weight: 500;
        color: var(--c--contextuals--content--semantic--neutral--tertiary);
        display: flex;
        flex-direction: row;
        align-items: center;
        gap: 4px;
        z-index: 10;
        transition: all 0.2s;
        width: fit-content;
        &:hover {
          background: var(--c--contextuals--background--semantic--neutral--tertiary);
          border: 1px solid var(--c--contextuals--border--semantic--neutral--tertiary);
        }
      `}
    >
      <Icon
        iconName="content_copy"
        $size="14px"
        $theme="greyscale"
        $variation="200"
      />
      <Text $size="xs" $theme="greyscale" $variation="200">
        {t('Copy code')}
      </Text>
    </Box>
  );
};

interface CodeBlockProps {
  children: ReactNode;
  [key: string]: unknown;
}

export const CodeBlock = ({ children, ...props }: CodeBlockProps) => {
  const preRef = useRef<HTMLPreElement>(null);
  const copyToClipboard = useClipboard();

  const handleCopy = () => {
    const code = preRef.current?.querySelector('code');
    copyToClipboard(code?.textContent || '');
  };

  return (
    <>
      <figure data-rehype-pretty-code-figure="">
        <CopyCodeButton onCopy={handleCopy} />
        <Box ref={preRef} $position="relative" as="pre" {...props}>
          {children}
        </Box>
      </figure>
    </>
  );
};
