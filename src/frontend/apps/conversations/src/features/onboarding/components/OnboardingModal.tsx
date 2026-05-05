import {
  OnboardingModal,
  type OnboardingModalProps,
  type OnboardingStep,
} from '@gouvfr-lasuite/ui-kit';
import Image, { type StaticImageData } from 'next/image';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { createGlobalStyle } from 'styled-components';

import NewChatBoldIcon from '@/assets/icons/new-message-bold.svg';
import DocIcon from '@/assets/icons/uikit-custom/doc.svg';
import FolderIcon from '@/assets/icons/uikit-custom/folder.svg';

import step1En from '../assets/step1-en.png';
import step1Fr from '../assets/step1-fr.png';
import step2En from '../assets/step2-en.png';
import step2Fr from '../assets/step2-fr.png';
import step3En from '../assets/step3-en.png';
import step3Fr from '../assets/step3-fr.png';
import step4En from '../assets/step4-en.png';
import step4Fr from '../assets/step4-fr.png';

type OnboardingWelcomeModalProps = {
  isOpen: boolean;
  onClose: () => void;
} & Partial<OnboardingModalProps>;

const OnBoardingStyle = createGlobalStyle`
  .c__onboarding-modal__steps{
    height: auto;
  }
  .c__onboarding-modal__content {
    height: 350px;
  }

  .c__modal__scroller {
    overflow-x: hidden;
  }

  /* Uniform font for onboarding modal */
  .c__modal:has(.c__onboarding-modal__steps),
  .c__modal:has(.c__onboarding-modal__steps)
    *:not(.material-icons):not(.material-icons-filled):not(
      .material-symbols-outlined
    ) {
    font-family: var(--c--globals--font--families--base);
  }

  .c__onboarding-modal__step__content {
    margin-top: 0 !important;
  }

  .c__onboarding-modal__step__description {
    line-height: inherit;
  }

  /* Separator between content and footer actions/link */
  .c__modal__footer {
    position: relative;
    border-top: 0;
    padding-top: var(--c--globals--spacings--md);
  }

  .c__modal__footer::before {
    content: '';
    position: absolute;
    inset: 0 calc(-1 * var(--c--globals--spacings--xl)) auto;
    height: 1px;
    background-color: var(--c--contextuals--border--surface--primary);
  }

  @media (max-width: 768px) {
    .c__modal__scroller {
      height: 100vh;
      display: flex;
      flex-direction: column;

      & .c__onboarding-modal__body{
        justify-content: center;
      }
      & .c__onboarding-modal__content {
        height:auto;
      }
    }
  }
`;

export const OnboardingWelcomeModal = (props: OnboardingWelcomeModalProps) => {
  const { isOpen, onClose, ...restProps } = props;
  const { i18n, t } = useTranslation();
  const isFr = i18n.resolvedLanguage?.startsWith('fr');

  const stepImage = (src: StaticImageData) => (
    <Image
      src={src}
      alt=""
      style={{
        display: 'block',
        width: '100%',
        height: '100%',
        objectFit: 'cover',
      }}
    />
  );

  const steps: OnboardingStep[] = useMemo(
    () => [
      {
        icon: <NewChatBoldIcon />,
        title: t('Start a conversation'),
        description: t(
          'Get help with coding, writing, proofreading, and more. Just ask.',
        ),
        content: stepImage(isFr ? step1Fr : step1En),
      },
      {
        icon: <DocIcon />,
        title: t('Work from your own documents'),
        description: t(
          'Upload a file or drag and drop it into the chat. The Assistant can read, summarize, or pull specific information from your documents.',
        ),
        content: stepImage(isFr ? step2Fr : step2En),
      },
      {
        icon: <span className="material-icons">language</span>,
        title: t('Turn on internet search'),
        description: t(
          'Need external sources? Enable "Research on the web" to let the Assistant look things up online. You can also switch on Smart internet search in your settings.',
        ),
        content: stepImage(isFr ? step3Fr : step3En),
      },
      {
        icon: <FolderIcon />,
        title: t('Set up projects for recurring work'),
        description: t(
          "Stop repeating yourself. Projects let you define instructions that apply to every conversation inside them. Shared project documents are coming soon, so you'll be able to build dedicated workspaces for each of your needs.",
        ),
        content: stepImage(isFr ? step4Fr : step4En),
      },
    ],
    [isFr, t],
  );

  return (
    <>
      {isOpen ? <OnBoardingStyle /> : null}
      <OnboardingModal
        isOpen={isOpen}
        appName={t('Discover Assistant')}
        mainTitle={t('Learn the core principles')}
        steps={steps}
        onClose={onClose}
        onComplete={onClose}
        {...restProps}
      />
    </>
  );
};
