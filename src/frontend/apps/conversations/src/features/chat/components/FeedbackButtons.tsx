import { Button } from '@openfun/cunningham-react';
import React from 'react';
import { useTranslation } from 'react-i18next';

import { useToast } from '@/components';
import { scoreMessage } from '@/features/chat/api/useScoreMessage';

interface FeedbackButtonsProps {
  conversationId: string | undefined;
  messageId: string;
}

const ThumbUp = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="16"
    height="16"
    viewBox="0 0 16 16"
    fill="none"
  >
    <path
      fillRule="evenodd"
      clipRule="evenodd"
      d="M6.98683 2.2102C7.63449 1.13117 9.1595 1.02836 9.94591 2.01088C10.3165 2.47409 10.4362 3.09014 10.2658 3.65838L9.61836 5.81531H12.5963C13.9605 5.81547 14.9515 7.11253 14.5929 8.42873L13.2304 13.4242C12.9849 14.3246 12.167 14.9496 11.2338 14.9497H4.48701C4.48261 14.9498 4.4782 14.9504 4.47377 14.9504C4.46935 14.9504 4.46494 14.9498 4.46053 14.9497H2.40395C1.81297 14.9496 1.3336 14.4703 1.3335 13.8793V6.88577C1.33364 6.29479 1.81297 5.81546 2.40395 5.81531H4.37899C4.65463 5.81531 4.91031 5.67038 5.05221 5.4341L6.98683 2.2102ZM8.94306 2.81372C8.71594 2.53004 8.27512 2.55927 8.08795 2.87087L6.15402 6.09478C5.91175 6.49857 5.54322 6.80023 5.11632 6.96312V13.6653H11.2338C11.5877 13.6652 11.8975 13.4277 11.9906 13.0862L13.3531 8.09073C13.4889 7.59167 13.1136 7.09987 12.5963 7.09972H9.33123C8.61423 7.09972 8.1 6.40809 8.30608 5.72123L9.03505 3.28971C9.08409 3.12575 9.04993 2.94742 8.94306 2.81372ZM2.6186 7.09972V13.6653H3.83122V7.09972H2.6186Z"
      fill="#555E74"
    />
  </svg>
);

const ThumbDown = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="14"
    height="13"
    viewBox="0 0 14 13"
    fill="none"
  >
    <path
      fillRule="evenodd"
      clipRule="evenodd"
      d="M10.2337 0C11.1669 7.56911e-05 11.9848 0.581603 12.2304 1.41911L13.5928 6.06606C13.9516 7.29054 12.9605 8.49766 11.5962 8.4978H8.61901L9.26573 10.5036C9.43623 11.0323 9.31647 11.6052 8.94585 12.0362C8.15943 12.9505 6.63442 12.8547 5.98679 11.8508L4.05218 8.85177C3.91028 8.63201 3.65459 8.4978 3.37897 8.4978H1.40394C0.812993 8.49766 0.333647 8.05181 0.333496 7.50203V0.995775C0.333647 0.44603 0.812973 0.000140027 1.40394 0H10.2337ZM4.1163 7.42877C4.54333 7.58028 4.91166 7.86149 5.15399 8.23719L7.0879 11.2362C7.27505 11.5263 7.71589 11.5535 7.94301 11.2893L7.97994 11.2414C8.05762 11.1242 8.07805 10.9809 8.035 10.8472L7.30604 8.58467C7.09997 7.9457 7.6142 7.30235 8.33118 7.30235H11.5962C12.1136 7.30221 12.4891 6.84482 12.353 6.38048L10.9906 1.73353C10.8975 1.41589 10.5876 1.19552 10.2337 1.19545H4.1163V7.42877ZM1.61859 7.30235H2.83121V1.19545H1.61859V7.30235Z"
      fill="#555E74"
    />
  </svg>
);

export const FeedbackButtons = ({
  conversationId,
  messageId,
}: FeedbackButtonsProps) => {
  const { t } = useTranslation();
  const { showToast } = useToast();

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

      showToast(
        'success',
        value === 'positive'
          ? t('Positive feedback sent')
          : t('Negative feedback sent'),
        'check_circle',
        3000,
      );
    } catch (error) {
      console.error('Error sending feedback:', error);
      showToast('error', t('Failed to send feedback'), 'error', 3000);
    }
  };

  return (
    <>
      <Button
        size="small"
        onClick={() => {
          void handleScore('positive');
        }}
        aria-label={t('Feedback positif')}
        icon={<ThumbUp />}
        className="c__button--neutral c__button--neutral--icon action-chat-button"
      />
      <Button
        size="small"
        onClick={() => {
          void handleScore('negative');
        }}
        aria-label={t('Feedback Négatif')}
        icon={<ThumbDown />}
        className="c__button--neutral c__button--neutral--icon action-chat-button"
      />
    </>
  );
};
