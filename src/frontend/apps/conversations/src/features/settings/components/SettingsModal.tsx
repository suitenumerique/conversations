import { Modal, ModalSize } from '@openfun/cunningham-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Icon, Text } from '@/components';

interface SettingsModalProps {
  onClose: () => void;
  isOpen: boolean;
}

export const SettingsModal = ({ onClose, isOpen }: SettingsModalProps) => {
  const { t } = useTranslation();
  const [isToggleEnabled, setIsToggleEnabled] = useState(false);

  const handleToggleChange = () => {
    setIsToggleEnabled(!isToggleEnabled);
  };

  return (
    <Modal
      isOpen={isOpen}
      closeOnClickOutside
      onClose={onClose}
      size={ModalSize.MEDIUM}
      title={
        <Text
          $size="h6"
          as="h6"
          $margin={{ all: '0' }}
          $align="flex-start"
          $variation="1000"
        >
          {t('Assistant settings')}
        </Text>
      }
    >
      <Box aria-label={t('Assistant settings')}>
        <Box $align="center" $justify="space-between">
          <Box $gap="2xs">
            <Text
              $size="xs"
              $weight="400"
              $variation="700"
              $padding={{ top: 'sm', bottom: 'sm' }}
            >
              {t(
                'The Assistant is a sovereign conversational AI designed for public servants. It helps you save time on daily tasks like rephrasing, summarising, translating, or searching information. Your data never leaves France and is stored on secure, state-compliant infrastructures. It is never used for commercial purposes.',
              )}
            </Text>
            <Text
              $size="md"
              $weight="500"
              $variation="1000"
              $padding={{ top: 'xs' }}
            >
              {t('Allow conversation analysis')}
            </Text>
          </Box>
          <Box $direction="row" $justify="space-between" $align="flex-start">
            <Box $css="max-width: 70%;">
              <Text $size="xs" $weight="400" $variation="700">
                {t(
                  'If enabled, this allows us to analyse your exchanges to improve the Assistant. If disabled, all conversations remain confidential and are not used in any way. Learn more about data usage.',
                )}
              </Text>
            </Box>
            <Box $css="padding-top: 2px;">
              <Box
                $css={`
                    position: relative;
                    width: 44px;
                    height: 24px;
                    background-color: ${isToggleEnabled ? 'var(--c--theme--colors--primary-500)' : 'var(--c--theme--colors--greyscale-300)'};
                    border-radius: 12px;
                    cursor: pointer;
                    transition: all 0.2s ease;
                    
                    &:hover {
                      background-color: ${isToggleEnabled ? 'var(--c--theme--colors--primary-600)' : 'var(--c--theme--colors--greyscale-400)'};
                    }
                  `}
                onClick={handleToggleChange}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    handleToggleChange();
                  }
                }}
                role="button"
                tabIndex={0}
              >
                <Box
                  $css={`
                    position: absolute;
                    top: 2px;
                    left: ${isToggleEnabled ? '22px' : '2px'};
                    width: 20px;
                    height: 20px;
                    background-color: white;
                    border-radius: 50%;
                    transition: left 0.2s ease;
                    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                  `}
                >
                  <Icon
                    iconName={isToggleEnabled ? 'check' : 'close'}
                    $size="12px"
                    $theme="primary"
                    $variation="600"
                  />
                </Box>
              </Box>
            </Box>
          </Box>
        </Box>
      </Box>
    </Modal>
  );
};
