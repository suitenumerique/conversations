import { Button } from '@openfun/cunningham-react';
import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Icon, Text } from '@/components';
import {
  LLMModel,
  useLLMConfiguration,
} from '@/features/chat/api/useLLMConfiguration';
import { useResponsiveStore } from '@/stores';

interface ModelSelectorProps {
  selectedModel: LLMModel | null;
  onModelSelect: (model: LLMModel) => void;
}

export const ModelSelector = ({
  selectedModel,
  onModelSelect,
}: ModelSelectorProps) => {
  const { t } = useTranslation();
  const { isMobile } = useResponsiveStore();
  const { data: llmConfig, isLoading } = useLLMConfiguration();
  const [isOpen, setIsOpen] = useState(false);

  if (isLoading || !llmConfig?.models || llmConfig.models.length <= 1) {
    return null;
  }

  const defaultModel = llmConfig.models.find((model) => model.is_default);
  const currentModel = selectedModel || defaultModel;

  const getModelIcon = (
    model: LLMModel,
    size: 'small' | 'medium' = 'small',
  ) => {
    const iconSize = size === 'small' ? '20px' : '24px';

    if (model.icon) {
      return (
        <Box
          $css={`
            width: ${iconSize};
            height: ${iconSize};
            border-radius: 6px;
            overflow: hidden;
            display: flex;
            align-items: center;
            justify-content: center;
            background: var(--c--theme--colors--greyscale-100);
            border: 1px solid var(--c--theme--colors--greyscale-200);
          `}
        >
          <img
            src={`${model.icon}`}
            alt={model.human_readable_name}
            style={{
              width: '100%',
              height: '100%',
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
          border-radius: 6px;
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
            padding: 8px 12px;

            
            .c__button__icon {
              transition: transform 0.2s ease;
            }
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
            <Box $css="display: flex; align-items: center; gap: 8px;">
              {currentModel && getModelIcon(currentModel, 'small')}
            </Box>
          }
        >
          {!isMobile && currentModel && (
            <>
              <Text
                $theme="greyscale"
                $variation="700"
                $weight="500"
                $size="sm"
              >
                {currentModel.human_readable_name}
              </Text>
              <Icon
                iconName={isOpen ? 'keyboard_arrow_up' : 'keyboard_arrow_down'}
                $theme="greyscale"
                $variation="600"
                $size="18px"
              />
            </>
          )}
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
          />

          <Box
            $css={`
              position: absolute;
              bottom: 100%;
              left: 0;
              min-width: 280px;
              background: white;
              border: 1px solid var(--c--theme--colors--greyscale-200);
              border-radius: 12px;
              box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12), 0 2px 8px rgba(0, 0, 0, 0.08);
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
            {llmConfig.models.map((model, index) => (
              <Box
                key={model.hrid}
                $css={`
                  padding: 12px 16px;
                  cursor: pointer;
                  display: flex;
                  align-items: center;
                  justify-content: space-between;
                  transition: all 0.2s ease;
                  position: relative;
                  
                    &:hover {
                      background-color: var(--c--theme--colors--primary-100);
                    }
                  
                  ${
                    currentModel?.hrid === model.hrid
                      ? `
                    background-color: var(--c--theme--colors--primary-50);
                    border-left: 3px solid var(--c--theme--colors--primary-500);
                    

                  `
                      : ''
                  }
                  
                  ${index === 0 ? 'border-radius: 12px 12px 0 0;' : ''}
                  ${index === llmConfig.models.length - 1 ? 'border-radius: 0 0 12px 12px;' : ''}
                `}
                onClick={() => {
                  onModelSelect(model);
                  setIsOpen(false);
                }}
              >
                <Box $align="center" $direction="row" $gap="1rem" $width="100%">
                  {getModelIcon(model, 'medium')}
                  <Box $css="display: flex; flex-direction: column; gap: 2px; flex: 1;">
                    <Box
                      $direction="row"
                      $css="display: flex; align-items: center; gap: 8px;"
                    >
                      <Text
                        $theme={
                          currentModel?.hrid === model.hrid
                            ? 'primary'
                            : 'greyscale'
                        }
                        $variation={
                          currentModel?.hrid === model.hrid ? '700' : '600'
                        }
                        $weight={
                          currentModel?.hrid === model.hrid ? '600' : '500'
                        }
                        $size="sm"
                      >
                        {model.human_readable_name}
                      </Text>
                      {model.is_default && (
                        <Box
                          $css={`
                        padding: 2px 8px;
                        background: var(--c--theme--colors--primary-100);
                        border-radius: 12px;
                        border: 1px solid var(--c--theme--colors--primary-200);
                      `}
                        >
                          <Text
                            $theme="primary"
                            $variation="600"
                            $size="xs"
                            $weight="500"
                          >
                            {t('Default')}
                          </Text>
                        </Box>
                      )}
                    </Box>

                    <Box
                      $direction="row"
                      $css="display: flex; align-items: center; gap: 8px;"
                    >
                      <Text $theme="greyscale" $variation="400" $size="xs">
                        {model.model_name}
                      </Text>
                    </Box>
                  </Box>
                  {currentModel?.hrid === model.hrid && (
                    <Icon
                      iconName="check"
                      $theme="primary"
                      $variation="600"
                      $size="16px"
                    />
                  )}
                </Box>
              </Box>
            ))}
          </Box>
        </>
      )}
    </Box>
  );
};
