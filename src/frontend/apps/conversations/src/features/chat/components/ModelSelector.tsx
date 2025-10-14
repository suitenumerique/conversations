import { Button } from '@openfun/cunningham-react';
import Image from 'next/image';
import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Icon, Text } from '@/components';
import {
  LLMModel,
  useLLMConfiguration,
} from '@/features/chat/api/useLLMConfiguration';

interface ModelSelectorProps {
  selectedModel: LLMModel | null;
  onModelSelect: (model: LLMModel) => void;
}

export const ModelSelector = ({
  selectedModel,
  onModelSelect,
}: ModelSelectorProps) => {
  const { t } = useTranslation();
  const { data: llmConfig, isLoading } = useLLMConfiguration();
  const [isOpen, setIsOpen] = useState(false);

  if (isLoading || !llmConfig?.models) {
    return null;
  }

  const activeModels = llmConfig.models.filter(
    (model) => model.is_active !== false,
  );

  if (activeModels.length <= 1) {
    return null;
  }

  const defaultModel = activeModels.find((model) => model.is_default);
  const currentModel = selectedModel || defaultModel;

  const getModelIcon = (
    model: LLMModel,
    size: 'small' | 'medium' = 'small',
  ) => {
    const iconSize = size === 'small' ? '16px' : '24px';

    if (model.icon) {
      return (
        <Box
          $radius="sm"
          $css={`
            width: ${iconSize};
            height: ${iconSize};
            overflow: hidden;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
          `}
        >
          <Image
            src={`${model.icon}`}
            alt={model.human_readable_name}
            fill
            style={{
              objectFit: 'cover',
            }}
          />
        </Box>
      );
    }

    return (
      <Box
        $css={`
          width: ${iconSize};
          height: ${iconSize};
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: ${size === 'small' ? '12px' : '25px'};
        `}
      >
        🤖
      </Box>
    );
  };

  return (
    <Box
      $position="relative"
      $css={`
        display: inline-block;
        z-index: ${isOpen ? 1000 : 'auto'};
      `}
    >
      <Box
        $css={`
          .model-selector-button {
            background: white;
            transition: all 0.2s ease;
            padding-right: 0 !important;
          }
        `}
      >
        <Button
          size="small"
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          aria-label={t('Select model')}
          className="c__button--neutral model-selector-button"
          icon={
            <Box $css="display: flex; align-items: center;">
              {currentModel && getModelIcon(currentModel, 'small')}
            </Box>
          }
        >
          <Icon
            iconName={isOpen ? 'keyboard_arrow_up' : 'keyboard_arrow_down'}
            $theme="greyscale"
            $variation="600"
            $size="18px"
          />
        </Button>
      </Box>

      {isOpen && (
        <>
          {/* Backdrop to close dropdown when clicking outside */}
          <Box
            $css={`
              position: fixed;
              top: 0;
              left: 0;
              right: 0;
              bottom: 0;
              z-index: 999;
            `}
            onClick={() => setIsOpen(false)}
            onKeyDown={(e: React.KeyboardEvent) => {
              if (e.key === 'Escape') {
                setIsOpen(false);
              }
            }}
            role="button"
            tabIndex={0}
            aria-label={t('Close model selector')}
          />

          <Box
            $css={`
              position: absolute;
              bottom: 100%;
              right: -30px;
              width: 300px;
              background: white;
              border: 1px solid var(--c--theme--colors--greyscale-100);
              border-radius: 4px;
              box-shadow: 0 0 6px 0 rgba(0, 0, 145, 0.10);
              z-index: 1000;
              margin-bottom: 8px;
              max-height: 320px;
              overflow-y: auto;
              overflow-x: hidden;
              justify-content: space-between;
              
              /* Custom scrollbar */
              &::-webkit-scrollbar {
                width: 6px;
              }
              &::-webkit-scrollbar-track {
                background: transparent;
              }
              &::-webkit-scrollbar-thumb {
                background: var(--c--theme--colors--greyscale-300);
                border-radius: 3px;
              }
              &::-webkit-scrollbar-thumb:hover {
                background: var(--c--theme--colors--greyscale-400);
              }
            `}
          >
            {activeModels.map((model) => (
              <Box
                key={model.hrid}
                $css={`
                  padding: 8px 16px;
                  cursor: pointer;
                  display: flex;
                  align-items: center;
                  justify-content: space-between;
                  transition: all 0.2s ease;
                  position: relative;
                  
                    &:hover {
                      background-color: #f2f5f4;
                    }
                  
                  ${
                    currentModel?.hrid === model.hrid
                      ? `
                    background-color: #f2f5f4;
                  `
                      : ''
                  }
                  
                `}
                onClick={() => {
                  onModelSelect(model);
                  setIsOpen(false);
                }}
                onKeyDown={(e: React.KeyboardEvent) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onModelSelect(model);
                    setIsOpen(false);
                  }
                }}
                role="button"
                tabIndex={0}
                aria-label={`${t('Select')} ${model.human_readable_name}`}
              >
                <Box $align="center" $direction="row" $gap="1rem" $width="100%">
                  {getModelIcon(model, 'medium')}
                  <Box $css="display: flex; flex-direction: column; gap: 2px; flex: 1;">
                    <Box
                      $direction="row"
                      $css="display: flex; align-items: center; justify-content: space-between; gap: 16px;"
                    >
                      <Text
                        $theme="greyscale"
                        $variation="850"
                        $weight="500"
                        $size="s"
                      >
                        {model.human_readable_name}
                      </Text>
                      {model.is_default && (
                        <Box>
                          <Text
                            $theme="greyscale"
                            $variation="550"
                            $size="xs"
                            $weight="400"
                          >
                            {t('Default')}
                          </Text>
                        </Box>
                      )}
                    </Box>
                  </Box>
                </Box>
              </Box>
            ))}
          </Box>
        </>
      )}
    </Box>
  );
};
