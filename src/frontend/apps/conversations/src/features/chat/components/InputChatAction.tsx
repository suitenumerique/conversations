import { Button } from '@gouvfr-lasuite/cunningham-react';
import { DropdownMenu, type DropdownMenuItem } from '@gouvfr-lasuite/ui-kit';
import { memo, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import DatagouvIcon from '@/assets/icons/uikit-custom/datagouv.svg?react';
import { Box, Icon, Text } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
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
  /** Whether the DataGouv connector is available to this user */
  datagouvEnabled: boolean;
  /** Whether the DataGouv connector is forced for the next message */
  forceDatagouv: boolean;
  /** Handler for attach button click */
  onAttachClick: () => void;
  /** Handler for web search toggle - if undefined, option is hidden */
  onWebSearchToggle?: () => void;
  /** Handler for the DataGouv toggle - if undefined, option is hidden */
  onDatagouvToggle?: () => void;
  /** Handler for model selection - if undefined, selector is hidden */
  onModelSelect?: (model: LLMModel) => void;
  /** Currently selected model */
  selectedModel: LLMModel | null;
  /** Current chat status */
  status: string | null;
  /** Whether input has content (for send button) */
  inputHasContent: boolean;
  /** Whether sending is blocked (e.g. during an inference-load cooldown) */
  sendDisabled?: boolean;
  /** Handler for stop button */
  onStop?: () => void;
}

const STYLES = {
  actionsGap: { bottom: 'base' },
  horizontalPadding: { horizontal: 'base' },
  horizontalPaddingXs: { horizontal: 'xs' },
} as const;

const ACTIONS_OPACITY_CSS = 'opacity: 1;';

const ACTIVE_CHIP_CSS = `
  .research-web-chip,
  .datagouv-chip {
    background-color: var(--c--contextuals--background--semantic--brand--secondary) !important;
    color: var(--c--contextuals--content--semantic--brand--secondary) !important;
  }
`;

/**
 * Action buttons for the chat input.
 * Includes: Attach/Web-search/DataGouv dropdown, Model selector, Send button.
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
    datagouvEnabled,
    forceDatagouv,
    onAttachClick,
    onWebSearchToggle,
    onDatagouvToggle,
    onModelSelect,
    selectedModel,
    status,
    inputHasContent,
    sendDisabled = false,
    onStop,
  }: InputChatActionsProps) => {
    const { t } = useTranslation();
    const { spacingsTokens } = useCunninghamTheme();
    const [isMenuOpen, setIsMenuOpen] = useState(false);

    const options: DropdownMenuItem[] = useMemo(() => {
      const items: DropdownMenuItem[] = [
        {
          label: t('Attach file'),
          icon: (
            <Icon iconName="upload" $theme="neutral" $variation="tertiary" />
          ),
          isDisabled: !fileUploadEnabled || isUploadingFiles,
          callback: onAttachClick,
        },
      ];

      if (onWebSearchToggle) {
        items.push(
          { type: 'separator' },
          {
            label: t('Research on the web'),
            icon: (
              <Icon
                iconName="language"
                $theme="neutral"
                $variation="tertiary"
              />
            ),
            isChecked: forceWebSearch,
            isDisabled: !webSearchEnabled || isUploadingFiles,
            callback: onWebSearchToggle,
          },
        );
      }

      // Hidden outside the beta cohort: no option, no way to force it.
      if (datagouvEnabled && onDatagouvToggle) {
        items.push(
          { type: 'separator' },
          {
            label: 'DataGouv',
            icon: <DatagouvIcon width={16} height={16} />,
            isChecked: forceDatagouv,
            isDisabled: isUploadingFiles,
            callback: onDatagouvToggle,
          },
        );
      }

      return items;
    }, [
      t,
      fileUploadEnabled,
      isUploadingFiles,
      onAttachClick,
      onWebSearchToggle,
      forceWebSearch,
      webSearchEnabled,
      datagouvEnabled,
      onDatagouvToggle,
      forceDatagouv,
    ]);

    return (
      <Box
        $direction="row"
        $gap={spacingsTokens.sm}
        $padding={STYLES.actionsGap}
        $align="center"
        $justify="space-between"
        $css={ACTIONS_OPACITY_CSS}
      >
        {/* Left side: Menu + active chips */}
        <Box
          $flex="1"
          $direction="row"
          $align="center"
          $padding={STYLES.horizontalPadding}
          $gap={spacingsTokens.sm}
        >
          <Box $shrink="0">
            <DropdownMenu
              options={options}
              isOpen={isMenuOpen}
              onOpenChange={setIsMenuOpen}
            >
              <Button
                size="nano"
                type="button"
                color="neutral"
                className="c__button--neutral"
                variant="tertiary"
                disabled={isUploadingFiles}
                onClick={() => setIsMenuOpen((prev) => !prev)}
                aria-label={t('Open input actions menu')}
                aria-haspopup="menu"
                aria-expanded={isMenuOpen}
                icon={
                  <Icon $theme="neutral" $variation="tertiary" iconName="add" />
                }
              />
            </DropdownMenu>
          </Box>

          {forceWebSearch && onWebSearchToggle && (
            <Box $css={ACTIVE_CHIP_CSS} $shrink="0">
              <Button
                size="nano"
                color="brand"
                variant="tertiary"
                type="button"
                disabled={!webSearchEnabled || isUploadingFiles}
                onClick={onWebSearchToggle}
                aria-label={t('Research on the web')}
                aria-pressed={true}
                className="c__button--neutral research-web-chip"
                icon={
                  <Icon
                    iconName="language"
                    $theme="brand"
                    $variation="tertiary"
                  />
                }
              >
                <Text $theme="brand" $variation="tertiary">
                  {isMobile ? t('Web') : t('Research on the web')}
                </Text>
              </Button>
            </Box>
          )}

          {forceDatagouv && datagouvEnabled && onDatagouvToggle && (
            <Box $css={ACTIVE_CHIP_CSS} $shrink="0">
              <Button
                size="nano"
                color="brand"
                variant="tertiary"
                type="button"
                disabled={isUploadingFiles}
                onClick={onDatagouvToggle}
                aria-label="DataGouv"
                aria-pressed={true}
                className="c__button--neutral datagouv-chip"
                icon={<DatagouvIcon width={16} height={16} />}
              >
                <Text $theme="brand" $variation="tertiary">
                  {isMobile ? 'Data' : 'DataGouv'}
                </Text>
              </Button>
            </Box>
          )}
        </Box>

        {/* Right side: Model selector + Send */}
        <Box
          $direction="row"
          $align="center"
          $padding={STYLES.horizontalPadding}
          $gap={spacingsTokens.xs}
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
            disabled={!inputHasContent || isUploadingFiles || sendDisabled}
            onClick={onStop}
          />
        </Box>
      </Box>
    );
  },
);

InputChatActions.displayName = 'InputChatActions';
