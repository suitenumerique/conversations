import { Button } from '@openfun/cunningham-react';
import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Icon, Text } from '@/components';
import { useChatPreferencesStore } from '@/features/chat/stores/useChatPreferencesStore';

interface ToolSelectorProps {
  className?: string;
}

// Define available tools with their display names
const AVAILABLE_TOOLS = [
  {
    id: 'service_public',
    name: 'Service Public',
    icon: 'public',
  },
];

export const ToolSelector = ({ className }: ToolSelectorProps) => {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const { selectedTools, toggleSelectedTool } = useChatPreferencesStore();

  const handleToolToggle = (toolId: string) => {
    toggleSelectedTool(toolId);
  };

  const selectedToolsCount = selectedTools.length;
  const hasSelectedTools = selectedToolsCount > 0;

  return (
    <Box
      $position="relative"
      className={className}
      $css={`
        display: inline-block;
        z-index: ${isOpen ? 1000 : 'auto'};
      `}
    >
      <Box
        $css={`
          ${
            hasSelectedTools
              ? `
            .tool-selector-button {
              background-color: var(--c--theme--colors--primary-100) !important;
            }
          `
              : ''
          }
        `}
      >
        <Button
          size="small"
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          aria-label={t('More tools')}
          className="c__button--neutral tool-selector-button"
          icon={
            <Icon
              iconName="build"
              $theme="greyscale"
              $variation="550"
              $size="16px"
              $css={`
                color: ${hasSelectedTools ? 'var(--c--theme--colors--primary-600) !important' : 'var(--c--theme--colors--greyscale-600)'}
              `}
            />
          }
        >
          <Text
            $theme={hasSelectedTools ? 'primary' : 'greyscale'}
            $variation="550"
          >
            {hasSelectedTools ? `${selectedToolsCount} outil${selectedToolsCount > 1 ? 's' : ''}` : t('More tools')}
          </Text>
        </Button>
      </Box>

      {isOpen && (
        <>
          {/* Backdrop to close the dropdown */}
          <Box
            $position="fixed"
            $css={`
              top: 0;
              left: 0;
              width: 100vw;
              height: 100vh;
              z-index: 999;
            `}
            onClick={() => setIsOpen(false)}
          />
          
          {/* Dropdown menu */}
          <Box
            $position="absolute"
            $css={`
              bottom: 100%;
              left: 0;
              margin-bottom: 6px;
              background: white;
              border: 1px solid var(--c--theme--colors--greyscale-200);
              border-radius: 8px;
              box-shadow: 0 -4px 12px rgba(0, 0, 0, 0.1);
              z-index: 1000;
              min-width: 160px;
              overflow: hidden;
            `}
          >
            <Box $padding={{ all: 'xs' }}>
              <Box $css="display: flex; flex-direction: column; gap: 1px;">
                {AVAILABLE_TOOLS.map((tool) => {
                  const isSelected = selectedTools.includes(tool.id);
                  
                  return (
                    <Box
                      key={tool.id}
                      $css={`
                        display: flex;
                        align-items: left;
                        justify-content: space-between;
                        padding: 6px 8px;
                        border-radius: 6px;
                        cursor: pointer;
                        transition: all 0.2s ease;
                        background-color: ${isSelected ? 'var(--c--theme--colors--primary-100)' : 'transparent'};
                        
                        &:hover {
                          background-color: ${isSelected ? 'var(--c--theme--colors--primary-200)' : 'var(--c--theme--colors--greyscale-100)'};
                        }
                      `}
                      onClick={() => handleToolToggle(tool.id)}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', flex: 1 }}>
                        <Icon
                          iconName={tool.icon}
                          $theme="greyscale"
                          $variation="600"
                          $size="16px"
                          $css="margin-right: 8px;"
                        />
                        
                        <span style={{ 
                          fontSize: '12px', 
                          fontWeight: '500',
                          color: isSelected ? 'var(--c--theme--colors--primary-600)' : 'var(--c--theme--colors--greyscale-600)',
                          whiteSpace: 'nowrap'
                        }}>
                          {tool.name}
                        </span>
                      </div>
                    </Box>
                  );
                })}
              </Box>
            </Box>
          </Box>
        </>
      )}
    </Box>
  );
};