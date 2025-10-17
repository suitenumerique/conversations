import { Button, Modal, ModalSize } from '@openfun/cunningham-react';
import { useRouter } from 'next/router';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import { fetchAPI } from '@/api';
import { Box, Text } from '@/components';
import { useToast } from '@/components/ToastProvider';
import { Footer } from '@/features/footer';
import {
  HomeHeader,
  getHeaderHeight,
} from '@/features/home/components/HomeHeader';
import { LeftPanel } from '@/features/left-panel';
import { useResponsiveStore } from '@/stores';

import { useActivationStatus, useRegisterNotification } from '../api';
import IllustrationCode from '../assets/assistant-code.svg';
import DocsIcon from '../assets/docs.svg';
import FichiersIcon from '../assets/fichiers.svg';
import TchapIcon from '../assets/tchap.svg';
import VisioIcon from '../assets/visio.svg';
import { useAuth } from '../hooks';

export const ActivationPage = () => {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const [code, setCode] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isNotifyModalOpen, setIsNotifyModalOpen] = useState(false);
  const [isOthersAppModalOpen, setIsOthersAppModalOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { data: activationStatus, refetch } = useActivationStatus();
  const { mutate: registerNotification } = useRegisterNotification();
  const { isSmallMobile, isDesktop } = useResponsiveStore();
  const router = useRouter();
  const { authenticated, user } = useAuth();

  const IconKey = () => {
    return (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="13"
        height="23"
        viewBox="0 0 13 23"
      >
        <path
          d="M5.82351 21.9396L4.38209 20.6839C4.2465 20.566 4.14923 20.4215 4.09027 20.2506C4.03721 20.0855 4.01069 19.9234 4.01069 19.7642V11.4606C3.29145 11.1363 2.66949 10.6971 2.1448 10.143C1.62012 9.5888 1.21334 8.958 0.924466 8.25055C0.641489 7.53721 0.5 6.78261 0.5 5.98674C0.5 5.15549 0.653279 4.3773 0.959838 3.65217C1.2664 2.92704 1.69381 2.29329 2.24208 1.75092C2.79624 1.20265 3.43589 0.775239 4.16102 0.468681C4.88615 0.156227 5.66728 0 6.50442 0C7.32977 0 8.10501 0.156227 8.83014 0.468681C9.56116 0.775239 10.2008 1.20265 10.7491 1.75092C11.2973 2.29919 11.7248 2.93589 12.0313 3.66102C12.3438 4.38615 12.5 5.16139 12.5 5.98674C12.5 7.15991 12.1758 8.22697 11.5273 9.18791C10.8788 10.143 9.95615 10.9182 8.75939 11.5136L10.5192 13.2822C10.7078 13.4768 10.8021 13.7038 10.8021 13.9632C10.808 14.2225 10.7167 14.4466 10.528 14.6352L8.59138 16.563L9.90015 17.8629C10.0888 18.0516 10.1831 18.2756 10.1831 18.535C10.189 18.7944 10.0976 19.0214 9.90899 19.2159L7.17649 21.9484C6.98195 22.1371 6.75792 22.2255 6.50442 22.2137C6.25682 22.2019 6.02985 22.1105 5.82351 21.9396ZM6.50442 20.3744L8.32609 18.5262L7.13228 17.35V15.7583L8.9451 13.972L7.25608 12.2653V10.364C7.9871 10.199 8.62675 9.9042 9.17502 9.47973C9.72329 9.04937 10.1478 8.53353 10.4484 7.9322C10.755 7.33088 10.9083 6.68239 10.9083 5.98674C10.9083 5.17318 10.7108 4.43331 10.3158 3.76713C9.92668 3.10096 9.39609 2.57038 8.72402 2.17539C8.05785 1.7804 7.31798 1.5829 6.50442 1.5829C5.8913 1.5829 5.31651 1.69786 4.78003 1.92778C4.24355 2.1577 3.77192 2.47605 3.36514 2.88283C2.96426 3.28371 2.64886 3.74945 2.41894 4.28003C2.18902 4.81061 2.07406 5.37951 2.07406 5.98674C2.07406 6.69418 2.22144 7.34856 2.51621 7.94989C2.81688 8.54532 3.2266 9.05232 3.74539 9.47089C4.27008 9.88357 4.86846 10.1636 5.54053 10.311V19.4193L6.50442 20.3744ZM6.50442 5.74797C6.10354 5.74797 5.76455 5.60943 5.48747 5.33235C5.21039 5.04937 5.07185 4.71039 5.07185 4.3154C5.07185 3.92041 5.21039 3.58438 5.48747 3.3073C5.76455 3.03021 6.10354 2.89167 6.50442 2.89167C6.89941 2.89167 7.23545 3.03021 7.51253 3.3073C7.7955 3.58438 7.93699 3.92041 7.93699 4.3154C7.93699 4.71039 7.7955 5.04937 7.51253 5.33235C7.23545 5.60943 6.89941 5.74797 6.50442 5.74797Z"
          fill="currentColor"
        />
      </svg>
    );
  };

  const laSuiteApps = [
    {
      name: 'Tchap',
      icon: TchapIcon,
      url: 'https://tchap.gouv.fr',
    },
    {
      name: 'Docs',
      icon: DocsIcon,
      url: 'https://docs.numerique.gouv.fr',
    },
    {
      name: 'Visio',
      icon: VisioIcon,
      url: 'https://visio.numerique.gouv.fr',
    },
    {
      name: 'Fichiers',
      icon: FichiersIcon,
      url: 'https://fichiers.numerique.gouv.fr/',
    },
  ];

  useEffect(() => {
    // Redirect to home if user is authenticated and already activated
    if (authenticated && activationStatus?.is_activated) {
      void router.push('/');
    }
  }, [authenticated, activationStatus, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!code.trim()) {
      setError(t('Please enter an activation code'));
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

      const data = (await response.json()) as {
        detail?: string;
        code?: string;
      };

      if (response.ok) {
        showToast(
          'success',
          data.detail || t('Account activated successfully!'),
        );
        setCode('');
        setError(null);
        // Refetch activation status to update the UI
        void refetch();
      } else {
        setError(
          data.code === 'invalid-code'
            ? t('Invalid activation code. Please check and try again.')
            : data.code === 'account-already-activated'
              ? t('Your account is already activated.')
              : t('Failed to activate account. Please try again.'),
        );
      }
    } catch {
      setError(t('An error occurred. Please try again.'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleNotificationRegister = () => {
    void registerNotification(undefined, {
      onSuccess: () => {
        showToast('success', t('You will be notified!'));
        setIsNotifyModalOpen(false);
        setIsOthersAppModalOpen(true);
      },
      onError: () => {
        showToast(
          'error',
          t('Failed to register for notifications. Please try again.'),
        );
      },
    });
  };

  return (
    <Box as="main">
      <HomeHeader />
      {isSmallMobile && (
        <Box $css="& .--docs--left-panel-header{display: none;}">
          <LeftPanel />
        </Box>
      )}
      <Box
        $css={css`
          height: calc(100vh - ${getHeaderHeight(isSmallMobile)}px);
          overflow-y: auto;
        `}
      >
        <Box
          $direction={isDesktop ? 'row' : 'column'}
          $css={css`
            margin: 0 auto;
          `}
        >
          <Box
            $align="center"
            $justify="center"
            $margin={{ top: isDesktop ? '0' : '50px' }}
            $css={css`
              height: ${isDesktop
                ? `calc(80vh - ${getHeaderHeight(isSmallMobile)}px)`
                : '120px'};
            `}
          >
            <Box
              $css={css`
                transform: ${isDesktop ? 'scale(1)' : 'scale(0.50)'};
                transform-origin: center;
              `}
            >
              <IllustrationCode />
            </Box>
          </Box>

          <Box $padding="large" $align="center" $justify="center">
            <Box $direction="column" $align="left" $maxWidth="600px">
              <Text $size="h6" $weight="700" $margin={{ bottom: 'xs' }}>
                {t('The Assistant is in Beta')}
              </Text>
              <Text
                $size="sm"
                $weight="400"
                $theme="greyscale"
                $variation="600"
              >
                {t(
                  'Access is limited to people who have an invitation code. If you have one, please enter it below.',
                )}
              </Text>

              <form onSubmit={(e) => void handleSubmit(e)}>
                <Box
                  $direction={isDesktop ? 'row' : 'column'}
                  $gap={isDesktop ? '8px' : '1rem'}
                  $margin={{ vertical: '24px' }}
                  $align={isDesktop ? 'flex-start' : 'stretch'}
                >
                  <Box $direction="column" $width="100%">
                    <Box
                      $css={`
                        input {
                          width: 100%;
                          height: 40px;
                          padding: 6px 8px;
                          border: 1px solid ${error ? 'var(--c--theme--colors--danger-600)' : 'var(--c--theme--colors--greyscale-150)'};
                          border-radius: 4px;
                          fontSize: 14px;
                          outline: none;
                          
                          &:focus {
                            border: 1px solid ${error ? 'var(--c--theme--colors--danger-600)' : 'var(--c--theme--colors--greyscale-150)'};
                            box-shadow: none;
                          }
                        }
                      `}
                    >
                      <input
                        type="text"
                        value={code}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                          setCode(e.target.value.toUpperCase());
                          setError(null);
                        }}
                        placeholder={t('ABC-1234-XY')}
                        disabled={isSubmitting}
                      />
                    </Box>
                    {error && (
                      <Text
                        $size="xs"
                        $theme="danger"
                        $variation="600"
                        $margin={{ top: '4px' }}
                      >
                        {error}
                      </Text>
                    )}
                  </Box>

                  <Button
                    type="submit"
                    fullWidth={isDesktop ? false : true}
                    color="primary"
                    icon={<IconKey />}
                    disabled={isSubmitting || !code.trim()}
                    style={{
                      width: isDesktop ? 'auto' : '100%',
                      whiteSpace: 'nowrap',
                      padding: '12px 24px',
                    }}
                  >
                    {isSubmitting ? t('Unlocking...') : t('Unlock access')}
                  </Button>
                </Box>
              </form>

              <Box
                $display="block"
                $gap="4px"
                $margin={{ top: 'medium' }}
                $align="center"
              >
                <Text
                  $display="inline-block"
                  $size="sm"
                  $theme="greyscale"
                  $variation="600"
                  as="span"
                  $margin={{ right: '4px' }}
                >
                  {t('No code? ')}
                </Text>
                <Box
                  as="button"
                  type="button"
                  onClick={() => setIsNotifyModalOpen(true)}
                  $css={css`
                    display: inline-block;
                    cursor: pointer;
                    text-decoration: underline;
                    background: none;
                    border: none;
                    padding: 0;
                    font-size: 14px;
                    font-weight: 400;
                    color: var(--c--theme--colors--greyscale-600);
                    font-family: inherit;

                    &:hover {
                      text-decoration: none;
                    }
                  `}
                >
                  {t('Get notified about the Public Beta.')}
                </Box>
              </Box>
            </Box>
          </Box>
        </Box>
        <Footer />

        {/* Notify Modal */}
        <Modal
          isOpen={isNotifyModalOpen}
          onClose={() => setIsNotifyModalOpen(false)}
          size={ModalSize.SMALL}
          hideCloseButton={false}
        >
          <Box>
            <Text
              as="span"
              $size="h6"
              $weight="700"
              $margin={{ bottom: '6px' }}
            >
              {t('Get notified for the public beta')}
            </Text>
            <Text $margin={{ bottom: 'md' }} $size="sm" $variation="600">
              {
                user
                  ? t(
                      "We'll email you at {{email}} when the public beta opens.",
                      {
                        email: user.email,
                      },
                    )
                  : t("We'll email you when the public beta opens.") // should not happen
              }
            </Text>
            <Box $direction="column" $gap="1rem" $justify="flex-end">
              <Button
                fullWidth
                color="primary"
                onClick={handleNotificationRegister}
              >
                {t('Notify me')}
              </Button>
              <Button
                fullWidth
                color="tertiary"
                onClick={() => {
                  setIsNotifyModalOpen(false);
                }}
              >
                {t('Cancel')}
              </Button>
            </Box>
          </Box>
        </Modal>

        {/* Others App Modal */}
        <Modal
          isOpen={isOthersAppModalOpen}
          onClose={() => setIsOthersAppModalOpen(false)}
          size={ModalSize.SMALL}
          hideCloseButton={false}
        >
          <Box>
            <Text
              as="span"
              $size="h6"
              $weight="700"
              $margin={{ bottom: '6px' }}
            >
              {t('You are on the list')}
            </Text>
            <Text $margin={{ bottom: 'md' }} $size="sm" $variation="600">
              {t('Explore other LaSuite apps')}
            </Text>
            <Box $direction="row" $gap="1rem" $justify="center">
              {laSuiteApps.map((app) => {
                const AppIcon = app.icon;
                return (
                  <Box
                    key={app.name}
                    as="a"
                    href={app.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={`${t('Open')} ${app.name}`}
                    $css={css`
                      display: flex;
                      width: 72px;
                      height: 72px;
                      flex-direction: column;
                      justify-content: center;
                      align-items: center;
                      gap: 6px;
                      border-radius: 4px;
                      transition: background-color 0.2s;
                      text-decoration: none;
                      color: inherit;

                      &:hover {
                        background-color: var(
                          --c--theme--colors--secondary-050
                        );
                        cursor: pointer !important;
                      }
                    `}
                  >
                    <Box
                      $css={css`
                        width: 56px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                      `}
                    >
                      <AppIcon />
                    </Box>
                    <Text
                      $size="xs"
                      $weight="700"
                      $theme="primary"
                      $variation="650"
                      $align="center"
                    >
                      {app.name}
                    </Text>
                  </Box>
                );
              })}
            </Box>
          </Box>
        </Modal>
      </Box>
    </Box>
  );
};
