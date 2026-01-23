import { Button } from '@openfun/cunningham-react';
import { memo, useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Icon, Text } from '@/components';
import { LLMModel } from '@/features/chat/api/useLLMConfiguration';

import { ModelSelector } from './ModelSelector';
import { SendButton } from './SendButton';
interface InputChatActionsProps {
  /** Whether file upload feature is enabled */
  fileUploadEnabled: boolean;
  /** Whether web search feature is enabled */
  webSearchEnabled: boolean;
  /** Whether files are currently being uploaded */
  isUploadingFiles: boolean;
  /** Whether the device is mobile */
  isMobile: boolean;
  /** Whether web search is forced/active */
  forceWebSearch: boolean;
  /** Handler for attach button click */
  onAttachClick: () => void;
  /** Handler for web search toggle - if undefined, button is hidden */
  onWebSearchToggle?: () => void;
  /** Handler for model selection - if undefined, selector is hidden */
  onModelSelect?: (model: LLMModel) => void;
  /** Currently selected model */
  selectedModel: LLMModel | null;
  /** Current chat status */
  status: string | null;
  /** Whether input has content (for send button) */
  inputHasContent: boolean;
  /** Handler for stop button */
  onStop?: () => void;
}

const STYLES = {
  actionsGap: { bottom: 'base' },
  horizontalPadding: { horizontal: 'base' },
  horizontalPaddingXs: { horizontal: 'xs' },
  webSearchMargin: { left: '4px' },
} as const;

const MOBILE_WEB_BUTTON_CSS = `
  .research-web-button {
    padding-right: 8px !important;
  }
`;

const ACTIVE_WEB_BUTTON_CSS = `
  .research-web-button {
    background-color: var(--c--contextuals--background--semantic--brand--secondary) !important;
    color: var(--c--contextuals--content--semantic--brand--secondary) !important;
  }
`;

const MOBILE_TEXT_WRAPPER_CSS = `
  display: flex;
  align-items: center;
  line-height: 1;
`;

const MOBILE_TEXT_CSS = `
  display: flex;
  align-items: center;
`;

const CLOSE_ICON_CSS = `
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  padding-left: 4px;
`;

/**
 * Action buttons for the chat input.
 * Includes: Attach file, Web search toggle, Model selector, Send button.
 *
 * Memoized to prevent re-renders when parent updates but props haven't changed.
 */
export const InputChatActions = memo(
  ({
    fileUploadEnabled,
    webSearchEnabled,
    isUploadingFiles,
    isMobile,
    forceWebSearch,
    onAttachClick,
    onWebSearchToggle,
    onModelSelect,
    selectedModel,
    status,
    inputHasContent,
    onStop,
  }: InputChatActionsProps) => {
    const { t } = useTranslation();

    // Memoized dynamic styles
    const actionsOpacityCss = useMemo(
      () => `opacity: ${status === 'error' ? '0.5' : '1'};`,
      [status],
    );

    const webSearchWrapperCss = useMemo(() => {
      let css = '';
      if (isMobile) {
        css += MOBILE_WEB_BUTTON_CSS;
      }
      if (forceWebSearch) {
        css += ACTIVE_WEB_BUTTON_CSS;
      }
      return css;
    }, [isMobile, forceWebSearch]);

    const webSearchIconCss = useMemo(
      () =>
        `color: ${forceWebSearch ? 'var(--c--theme--colors--primary-600) !important' : 'var(--c--theme--colors--greyscale-600)'}`,
      [forceWebSearch],
    );

    const attachIconSize = isMobile ? '24px' : '16px';

    return (
      <Box
        $direction="row"
        $gap="sm"
        $padding={STYLES.actionsGap}
        $align="space-between"
        $css={actionsOpacityCss}
      >
        {/* Left side: Attach + Web Search */}
        <Box
          $flex="1"
          $direction="row"
          $padding={STYLES.horizontalPadding}
          $gap="xs"
        >
          {/* Attach file button */}
          <Button
            size="nano"
            type="button"
            color="neutral"
            className="c__button--neutral"
            variant="tertiary"
            disabled={!fileUploadEnabled || isUploadingFiles}
            onClick={onAttachClick}
            aria-label={t('Add attach file')}
            icon={<Icon iconName="attach_file" $size={attachIconSize} />}
          >
            {!isMobile && <Text $weight="500">{t('Attach file')}</Text>}
          </Button>

          {/* Web search toggle button */}
          {onWebSearchToggle && (
            <Box $margin={STYLES.webSearchMargin} $css={webSearchWrapperCss}>
              <Button
                size="nano"
                type="button"
                disabled={!webSearchEnabled || isUploadingFiles}
                onClick={onWebSearchToggle}
                aria-label={t('Research on the web')}
                className="c__button--neutral research-web-button"
                icon={<Icon iconName="language" $css={webSearchIconCss} />}
              >
                {!isMobile && (
                  <Text
                    $theme={forceWebSearch ? 'primary' : 'greyscale'}
                    $variation="550"
                  >
                    {t('Research on the web')}
                  </Text>
                )}
                {isMobile && forceWebSearch && (
                  <Box
                    $direction="row"
                    $align="space-between"
                    $gap="xs"
                    $css={MOBILE_TEXT_WRAPPER_CSS}
                  >
                    <Text
                      $theme="brand"
                      $variation="secondary"
                      $weight="500"
                      $css={MOBILE_TEXT_CSS}
                    >
                      {t('Web')}
                    </Text>
                    <Icon
                      iconName="close"
                      $theme="brand"
                      $variation="secondary"
                      $size="md"
                      $css={CLOSE_ICON_CSS}
                    />
                  </Box>
                )}
              </Button>
            </Box>
          )}
        </Box>

        {/* Right side: Model selector + Send */}
        <Box
          $direction="row"
          $align="center"
          $padding={STYLES.horizontalPadding}
          $gap="xs"
        >
          {onModelSelect && (
            <Box $padding={STYLES.horizontalPaddingXs}>
              <ModelSelector
                selectedModel={selectedModel}
                onModelSelect={onModelSelect}
              />
            </Box>
          )}

          <SendButton
            status={status}
            disabled={!inputHasContent || isUploadingFiles}
            onClick={onStop}
          />
        </Box>
      </Box>
    );
  },
);

InputChatActions.displayName = 'InputChatActions';
