import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import DocsIcon from '@/assets/icons/icon-docs.svg';
import { Box, BoxButton, DropButton, Icon, Text, useToast } from '@/components';
import { editInDocs } from '@/features/chat/api/useEditInDocs';

interface MoreActionsButtonProps {
  conversationId: string;
  messageId: string;
}

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
    // Open the tab synchronously inside the click handler so browsers don't treat
    // it as a non-user-initiated popup once the await below resolves.
    const docsTab = window.open('', '_blank');
    // Sever the opener reference to prevent the opened page from navigating this
    // one via window.opener (reverse tabnabbing), while keeping the handle so we
    // can still set its location once the async call below resolves.
    if (docsTab) {
      docsTab.opener = null;
    }
    try {
      const result = await editInDocs({
        conversationId,
        message_id: messageId,
      });
      if (docsTab) {
        docsTab.location.href = result.docUrl;
      }
    } catch (error) {
      console.error('Error editing in Docs:', error);
      docsTab?.close();
      showToast('error', t('Failed to open in Docs'), 'error', 3000);
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
            <DocsIcon width={20} height={20} />
            <Text $variation={isLoading ? '400' : '1000'}>
              {t('Edit in Docs')}
            </Text>
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
