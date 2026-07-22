import { Button } from '@gouvfr-lasuite/cunningham-react';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';

import img401 from '@/assets/icons/icon-401.png';
import { Box, Text } from '@/components';
import { gotoLogin, useAuth } from '@/features/auth';

const Page = () => {
  const { t } = useTranslation();
  const { authenticated } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (authenticated) {
      void navigate('/', { replace: true });
    }
  }, [authenticated, navigate]);

  return (
    <Box
      $align="center"
      $margin="auto"
      $gap="1rem"
      $padding={{ bottom: '2rem' }}
    >
      <img
        className="c__image-system-filter"
        src={img401}
        alt={t('Image 401')}
        style={{
          maxWidth: '100%',
          height: 'auto',
        }}
      />

      <Box $align="center" $gap="0.8rem">
        <Text as="p" $textAlign="center" $maxWidth="350px" $theme="primary">
          {t('Log in to access this page.')}
        </Text>

        <Button onClick={() => gotoLogin(false)} aria-label={t('Login')}>
          {t('Login')}
        </Button>
      </Box>
    </Box>
  );
};

export default Page;
