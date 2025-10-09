import { Button } from '@openfun/cunningham-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { fetchAPI } from '@/api';
import { Box, Card, Text } from '@/components';
import { useToast } from '@/components/ToastProvider';

import { useActivationStatus } from '../api/useActivationStatus';

export const ActivationPage = () => {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const [code, setCode] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { data: activationStatus, refetch } = useActivationStatus();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!code.trim()) {
      showToast('error', t('Please enter an activation code'));
      return;
    }

    setIsSubmitting(true);

    try {
      const response = await fetchAPI('activation/validate/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({ code: code.trim() }),
      });

      const data = await response.json();

      if (response.ok) {
        showToast(
          'success',
          data.detail || t('Account activated successfully!'),
        );
        setCode('');
        // Refetch activation status to update the UI
        void refetch();
      } else {
        showToast(
          'error',
          data.code === 'invalid-code'
            ? t('Invalid activation code. Please check and try again.')
            : data.code === 'account-already-activated'
              ? t('Your account is already activated.')
              : t('Failed to activate account. Please try again.'),
        );
      }
    } catch (error) {
      showToast('error', t('An error occurred. Please try again.'));
    } finally {
      setIsSubmitting(false);
    }
  };

  // If already activated, show success message
  if (activationStatus?.is_activated) {
    return (
      <Box $padding="large" $align="center" $justify="center" $height="100vh">
        <Card $padding="large" $maxWidth="500px">
          <Text
            as="h1"
            $size="h2"
            $weight="bold"
            $margin={{ bottom: 'medium' }}
          >
            {t('Account Activated')}
          </Text>
          <Text $margin={{ bottom: 'large' }}>
            {t(
              'Your account has been successfully activated. You can now access all features.',
            )}
          </Text>
          <Button onClick={() => (window.location.href = '/')} color="primary">
            {t('Continue to App')}
          </Button>
        </Card>
      </Box>
    );
  }

  return (
    <Box $padding="large" $align="center" $justify="center" $height="100vh">
      <Card $padding="large" $maxWidth="500px">
        <Text as="h1" $size="h2" $weight="bold" $margin={{ bottom: 'medium' }}>
          {t('Account Activation Required')}
        </Text>
        <Text $margin={{ bottom: 'large' }}>
          {t(
            'Please enter your activation code to activate your account and access all features.',
          )}
        </Text>

        <form onSubmit={handleSubmit}>
          <Box $margin={{ bottom: 'large' }}>
            <Text as="span" $weight="bold" $margin={{ bottom: 'small' }}>
              {t('Activation Code')}
            </Text>
            <input
              type="text"
              value={code}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setCode(e.target.value.toUpperCase())
              }
              placeholder={t('Enter your activation code')}
              style={{
                width: '100%',
                padding: '8px 12px',
                border: '1px solid #ccc',
                borderRadius: '4px',
              }}
              disabled={isSubmitting}
            />
          </Box>

          <Button
            type="submit"
            color="primary"
            disabled={isSubmitting || !code.trim()}
            style={{ width: '100%' }}
          >
            {isSubmitting ? t('Activating...') : t('Activate Account')}
          </Button>
        </form>

        <Text $size="small" $color="text-weak" $margin={{ top: 'medium' }}>
          {t(
            "If you don't have an activation code, please contact your administrator.",
          )}
        </Text>
      </Card>
    </Box>
  );
};
