import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import { Box, BoxButton, DropButton, Icon, Text, useToast } from '@/components';
import { editInDocs } from '@/features/chat/api/useEditInDocs';

interface MoreActionsButtonProps {
  conversationId: string;
  messageId: string;
}

const DocsIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
  >
    <path
      fillRule="evenodd"
      clipRule="evenodd"
      d="M6 2C4.89543 2 4 2.89543 4 4V20C4 21.1046 4.89543 22 6 22H18C19.1046 22 20 21.1046 20 20V8L14 2H6ZM13 3.5V9H18.5L13 3.5ZM8 13C8 12.4477 8.44772 12 9 12H15C15.5523 12 16 12.4477 16 13C16 13.5523 15.5523 14 15 14H9C8.44772 14 8 13.5523 8 13ZM9 16C8.44772 16 8 16.4477 8 17C8 17.5523 8.44772 18 9 18H13C13.5523 18 14 17.5523 14 17C14 16.4477 13.5523 16 13 16H9Z"
      fill="var(--c--contextuals--content--semantic--neutral--secondary)"
    />
  </svg>
);

export const MoreActionsButton = ({
  conversationId,
  messageId,
}: MoreActionsButtonProps) => {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const handleEditInDocs = async () => {
    if (isLoading) return;
    setIsOpen(false);
    setIsLoading(true);
    try {
      const result = await editInDocs({ conversationId, message_id: messageId });
      window.open(result.docUrl, '_blank', 'noopener,noreferrer');
    } catch (error) {
      console.error('Error exporting to Docs:', error);
      showToast('error', t("Échec de l'export vers Docs"), 'error', 3000);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <DropButton
      isOpen={isOpen}
      onOpenChange={setIsOpen}
      label={t('More actions')}
      buttonCss={css`
        display: flex;
        align-items: center;
        justify-content: center;
        width: 24px;
        height: 24px;
        padding: 4px;
        border-radius: 4px;
        color: var(--c--contextuals--content--semantic--neutral--secondary);
        &:hover {
          background-color: var(
            --c--contextuals--background--semantic--contextual--primary
          ) !important;
        }
        &:focus-visible {
          outline: 2px solid var(--c--globals--colors--brand-400);
          outline-offset: 2px;
        }
      `}
      button={
        <Icon
          iconName="more_horiz"
          $theme="neutral"
          $variation="secondary"
          $size="16px"
          className="action-chat-button-icon"
        />
      }
    >
      <Box role="menu" $minWidth="180px" $maxWidth="280px">
        <BoxButton
          role="menuitem"
          aria-label={t('Edit in Docs')}
          $direction="row"
          $align="center"
          $justify="space-between"
          $padding={{ vertical: 'xs', horizontal: 'base' }}
          $width="100%"
          $gap="12px"
          disabled={isLoading}
          onClick={() => {
            void handleEditInDocs();
          }}
          $css={css`
            border: none;
            border-radius: 4px;
            font-size: var(--c--globals--font--sizes--sm);
            font-weight: var(--c--globals--font--weights--medium);
            color: var(--c--contextuals--content--semantic--brand--tertiary);
            cursor: ${isLoading ? 'not-allowed' : 'pointer'};
            user-select: none;

            &:hover {
              background-color: var(
                --c--contextuals--background--semantic--contextual--primary
              );
            }

            &:focus-visible {
              outline: 2px solid var(--c--globals--colors--brand-400);
              outline-offset: -2px;
              background-color: var(
                --c--contextuals--background--semantic--contextual--primary
              );
            }
          `}
        >
          <Box $direction="row" $align="center" $gap="12px">
            <DocsIcon />
            <Text $variation={isLoading ? '400' : '1000'}>{t('Edit in Docs')}</Text>
          </Box>
          <Icon
            iconName="open_in_new"
            $size="16px"
            $theme="neutral"
            $variation={isLoading ? 'tertiary' : 'primary'}
            aria-hidden="true"
          />
        </BoxButton>
      </Box>
    </DropButton>
  );
};
