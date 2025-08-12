import { useEffect, useState } from 'react';
import { css } from 'styled-components';

import { Box, Text } from '@/components';
import { Icon } from '@/components/Icon';

export type ToastType = 'success' | 'error' | 'info' | 'warning';

export interface ToastProps {
  id: string;
  message: string;
  type: ToastType;
  icon?: string;
  duration?: number;
  onClose: (id: string) => void;
}

const getToastConfig = (type: ToastType) => {
  switch (type) {
    case 'success':
      return {
        icon: 'check_circle',
        color: '#223E9E',
        bgColor: '#EDF0FF',
        borderColor: '#C8D3FF',
      };
    case 'error':
      return {
        icon: 'error',
        color: '#EF4444',
        bgColor: '#FEF2F2',
        borderColor: '#FECACA',
      };
    case 'warning':
      return {
        icon: 'warning',
        color: '#F59E0B',
        bgColor: '#FFFBEB',
        borderColor: '#FED7AA',
      };
    case 'info':
      return {
        icon: 'info',
        color: '#3B82F6',
        bgColor: '#EFF6FF',
        borderColor: '#BFDBFE',
      };
    default:
      return {
        icon: 'info',
        color: '#6B7280',
        bgColor: '#F9FAFB',
        borderColor: '#E5E7EB',
      };
  }
};

export const Toast = ({
  id,
  message,
  type,
  icon,
  duration = 4000,
  onClose,
}: ToastProps) => {
  const [isVisible, setIsVisible] = useState(false);
  const [isLeaving, setIsLeaving] = useState(false);
  const config = getToastConfig(type);
  const iconToUse = icon || config.icon;

  useEffect(() => {
    const timer = setTimeout(() => setIsVisible(true), 100);

    const autoCloseTimer = setTimeout(() => {
      setIsLeaving(true);
      setTimeout(() => onClose(id), 300);
    }, duration);

    return () => {
      clearTimeout(timer);
      clearTimeout(autoCloseTimer);
    };
  }, [id, duration, onClose]);

  return (
    <Box
      $css={css`
        background-color: ${config.bgColor};
        border: 1px solid ${config.borderColor};
        color: ${config.color};
        border-radius: 4px;
        padding: 8px 12px;
        width: auto;
        margin-bottom: 8px;
        box-shadow: 0 6px 18px 0 rgba(0, 0, 145, 0.05);
        transform: translateY(${isVisible ? '0' : '100%'});
        opacity: ${isVisible ? '1' : '0'};
        transition: all 0.3s ease-in-out;
        position: relative;
        overflow: hidden;

        ${isLeaving &&
        css`
          transform: translateY(-100%);
          opacity: 0;
        `}
      `}
    >
      <Box $direction="row" $align="center" $gap="12px">
        <Icon
          iconName={iconToUse}
          $variation="600"
          $size="20px"
          $css={css`
            color: ${config.color} !important;
          `}
        />
        <Text
          $weight="500"
          $size="14px"
          $css={css`
            color: ${config.color} !important;
            padding: 4px;
          `}
        >
          {message}
        </Text>
      </Box>
    </Box>
  );
};
