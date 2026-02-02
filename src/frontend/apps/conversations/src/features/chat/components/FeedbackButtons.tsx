import { Button } from '@openfun/cunningham-react';
import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Box, useToast } from '@/components';
import { scoreMessage } from '@/features/chat/api/useScoreMessage';

interface FeedbackButtonsProps {
  conversationId: string | undefined;
  messageId: string;
}

const ThumbUp = () => (
  <svg
    width="24"
    height="24"
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    <path
      fill-rule="evenodd"
      clip-rule="evenodd"
      d="M10.48 3.31533C11.4515 1.69679 13.739 1.54257 14.9186 3.01635C15.4744 3.71116 15.654 4.63525 15.3984 5.4876L14.4273 8.723H18.8941C20.9405 8.72323 22.427 10.6688 21.8891 12.6431L19.8454 20.1363C19.4771 21.4869 18.2502 22.4245 16.8505 22.4246H6.73028C6.72367 22.4247 6.71705 22.4256 6.71041 22.4256C6.70377 22.4256 6.69716 22.4247 6.69055 22.4246H3.60568C2.71921 22.4244 2.00016 21.7055 2 20.8189V10.3287C2.00022 9.44222 2.71921 8.72323 3.60568 8.723H6.56824C6.9817 8.723 7.36522 8.5056 7.57807 8.15119L10.48 3.31533ZM13.4143 4.22061C13.0737 3.79509 12.4124 3.83894 12.1317 4.30633L9.23079 9.14219C8.86738 9.74788 8.31458 10.2004 7.67424 10.4447V20.498H16.8505C17.3813 20.4979 17.846 20.1415 17.9857 19.6293L20.0294 12.1361C20.2331 11.3875 19.6701 10.6498 18.8941 10.6496H13.9966C12.9211 10.6496 12.1498 9.61217 12.4589 8.58188L13.5523 4.9346C13.6259 4.68866 13.5747 4.42117 13.4143 4.22061ZM3.92765 10.6496V20.498H5.74659V10.6496H3.92765Z"
      fill="var(--c--contextuals--content--semantic--neutral--secondary)"
    />
  </svg>
);

const ThumbDown = () => (
  <svg
    width="24"
    height="24"
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    <path
      fill-rule="evenodd"
      clip-rule="evenodd"
      d="M16.8504 3C18.2501 3.00011 19.477 3.8724 19.8453 5.12866L21.889 12.0991C22.4272 13.9358 20.9405 15.7465 18.894 15.7467H14.4283L15.3984 18.7554C15.6541 19.5485 15.4745 20.4078 14.9185 21.0543C13.7389 22.4257 11.4514 22.2821 10.4799 20.7761L7.57803 16.2777C7.36518 15.948 6.98164 15.7467 6.56822 15.7467H3.60567C2.71925 15.7465 2.00023 15.0777 2 14.253V4.49366C2.00023 3.66904 2.71922 3.00021 3.60567 3H16.8504ZM7.6742 14.1432C8.31475 14.3704 8.86725 14.7922 9.23074 15.3558L12.1316 19.8543C12.4123 20.2894 13.0736 20.3302 13.4143 19.934L13.4697 19.8621C13.5862 19.6864 13.6168 19.4713 13.5523 19.2708L12.4588 15.877C12.1497 14.9185 12.9211 13.9535 13.9965 13.9535H18.894C19.6701 13.9533 20.2334 13.2672 20.0293 12.5707L17.9856 5.6003C17.8459 5.12383 17.3812 4.79329 16.8504 4.79317H7.6742V14.1432ZM3.92764 13.9535H5.74656V4.79317H3.92764V13.9535Z"
      fill="var(--c--contextuals--content--semantic--neutral--secondary)"
    />
  </svg>
);

const ThumbDownFilled = () => (
  <svg
    width="24"
    height="24"
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    <path
      fill-rule="evenodd"
      clip-rule="evenodd"
      d="M16.8504 3C18.2501 3.00011 19.477 3.8724 19.8453 5.12866L21.889 12.0991C22.4272 13.9358 20.9405 15.7465 18.894 15.7467H14.4283L15.3984 18.7554C15.6541 19.5485 15.4745 20.4078 14.9185 21.0543C13.7389 22.4257 11.4514 22.2821 10.4799 20.7761L7.57803 16.2777C7.36518 15.948 6.98163 15.7467 6.56822 15.7467H3.60567C2.71925 15.7465 2.00023 15.0777 2 14.253V4.49366C2.00023 3.66904 2.71922 3.00021 3.60567 3H16.8504ZM5.92764 13.4535C5.92764 13.7297 6.1515 13.9535 6.42764 13.9535H7.07803C7.35417 13.9535 7.57803 13.7297 7.57803 13.4535V5.29317C7.57803 5.01703 7.35417 4.79317 7.07803 4.79317H6.42764C6.1515 4.79317 5.92764 5.01703 5.92764 5.29317V13.4535Z"
      fill="var(--c--contextuals--content--semantic--brand--tertiary)"
    />
  </svg>
);

const ThumbUpFilled = () => (
  <svg
    width="24"
    height="24"
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    <path
      fill-rule="evenodd"
      clip-rule="evenodd"
      d="M10.48 3.31533C11.4515 1.69679 13.739 1.54257 14.9186 3.01635C15.4744 3.71116 15.654 4.63525 15.3984 5.4876L14.4273 8.723H18.8941C20.9405 8.72323 22.427 10.6688 21.8891 12.6431L19.8454 20.1363C19.4771 21.4869 18.2502 22.4245 16.8505 22.4246H6.73028C6.72367 22.4247 6.71705 22.4256 6.71041 22.4256C6.70378 22.4256 6.69716 22.4247 6.69055 22.4246H3.60568C2.71921 22.4244 2.00016 21.7055 2 20.8189V10.3287C2.00022 9.44222 2.71921 8.72323 3.60568 8.723H6.56824C6.9817 8.723 7.36522 8.5056 7.57807 8.15119L10.48 3.31533ZM6.42765 10.6496C6.15151 10.6496 5.92765 10.8735 5.92765 11.1496V19.998C5.92765 20.2741 6.15151 20.498 6.42765 20.498H7C7.27614 20.498 7.5 20.2741 7.5 19.998V11.1496C7.5 10.8735 7.27614 10.6496 7 10.6496H6.42765Z"
      fill="var(--c--contextuals--content--semantic--brand--tertiary)"
    />
  </svg>
);

export const FeedbackButtons = ({
  conversationId,
  messageId,
}: FeedbackButtonsProps) => {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const [selectedFeedback, setSelectedFeedback] = useState<
    'positive' | 'negative' | null
  >(null);

  const handleScore = async (value: 'positive' | 'negative') => {
    if (!conversationId) {
      return;
    }

    try {
      await scoreMessage({
        conversationId,
        message_id: messageId,
        value,
      });

      setSelectedFeedback(value);
    } catch (error) {
      setSelectedFeedback(value);
      console.error('Error sending feedback:', error);
      showToast('error', t('Failed to send feedback'), 'error', 3000);
    }
  };

  return (
    <Box
      $direction="row"
      $gap="4px"
      $css={`
        button svg {
          width: 16px !important;
          height: 16px !important;
        }
      `}
    >
      <Button
        size="small"
        onClick={() => {
          void handleScore('positive');
        }}
        aria-label={t('Feedback positif')}
        icon={selectedFeedback === 'positive' ? <ThumbUpFilled /> : <ThumbUp />}
        className="c__button--neutral c__button--neutral--icon action-chat-button"
      />
      <Button
        size="small"
        onClick={() => {
          void handleScore('negative');
        }}
        aria-label={t('Feedback Négatif')}
        icon={
          selectedFeedback === 'negative' ? <ThumbDownFilled /> : <ThumbDown />
        }
        className="c__button--neutral c__button--neutral--icon action-chat-button"
      />
    </Box>
  );
};
