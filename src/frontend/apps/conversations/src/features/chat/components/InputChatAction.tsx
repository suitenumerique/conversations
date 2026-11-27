import { Button } from '@gouvfr-lasuite/cunningham-react';
import { DropdownMenu, type DropdownMenuItem } from '@gouvfr-lasuite/ui-kit';
import { memo, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Icon, Text } from '@/components';
import type { ConnectorConfig } from '@/core/config/api/useConfig';
import { useCunninghamTheme } from '@/cunningham';
import { LLMModel } from '@/features/chat/api/useLLMConfiguration';

import { ConnectorIcon } from './ConnectorIcon';
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
  /** The connectors available to this user, in declaration order */
  connectors: ConnectorConfig[];
  /** Slugs of the connectors forced for the next message */
  forcedConnectors: string[];
  /** Handler for attach button click */
  onAttachClick: () => void;
  /** Handler for web search toggle - if undefined, option is hidden */
  onWebSearchToggle?: () => void;
  /** Handler for a connector's force toggle - if undefined, options are hidden */
  onConnectorToggle?: (slug: string) => void;
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
  .connector-chip {
    background-color: var(--c--contextuals--background--semantic--brand--secondary) !important;
    color: var(--c--contextuals--content--semantic--brand--secondary) !important;
  }
`;

/**
 * Action buttons for the chat input.
 * Includes: Attach/Web-search/connectors dropdown, Model selector, Send button.
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
    connectors,
    forcedConnectors,
    onAttachClick,
    onWebSearchToggle,
    onConnectorToggle,
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

      // Only the connectors available to this user: one outside its cohort
      // has no option, so no way to force it.
      if (onConnectorToggle && connectors.length > 0) {
        items.push({ type: 'separator' });
        for (const connector of connectors) {
          items.push({
            label: connector.name,
            // Same 24px slot as the Material glyphs above, so labels align.
            icon: (
              <Box
                $width="24px"
                $align="center"
                $justify="center"
                $theme="neutral"
                $variation="tertiary"
              >
                <ConnectorIcon icon={connector.icon} />
              </Box>
            ),
            isChecked: forcedConnectors.includes(connector.slug),
            isDisabled: isUploadingFiles,
            callback: () => onConnectorToggle(connector.slug),
          });
        }
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
      connectors,
      onConnectorToggle,
      forcedConnectors,
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

          {onConnectorToggle &&
            connectors
              .filter((connector) => forcedConnectors.includes(connector.slug))
              .map((connector) => (
                <Box key={connector.slug} $css={ACTIVE_CHIP_CSS} $shrink="0">
                  <Button
                    size="nano"
                    color="brand"
                    variant="tertiary"
                    type="button"
                    disabled={isUploadingFiles}
                    onClick={() => onConnectorToggle(connector.slug)}
                    aria-label={connector.name}
                    aria-pressed={true}
                    className="c__button--neutral connector-chip"
                    icon={<ConnectorIcon icon={connector.icon} />}
                  >
                    <Text $theme="brand" $variation="tertiary">
                      {connector.name}
                    </Text>
                  </Button>
                </Box>
              ))}
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
