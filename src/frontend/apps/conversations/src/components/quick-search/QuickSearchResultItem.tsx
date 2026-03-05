import { ComponentType, SVGProps, memo, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { css } from 'styled-components';

import { Box, Text } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import { ChatConversation } from '@/features/chat/types';
import { PROJECT_ICONS } from '@/features/left-panel/components/projects/project-constants';
import { getRelativeTime } from '@/utils';

import ArrowForwardIcon from './assets/arrow-forward.svg';
import BubbleIcon from './assets/bubble.svg';

const descriptionCss = css`
  font-weight: 400;
`;

type QuickSearchResultItemProps = {
  conversation: ChatConversation;
};

export const QuickSearchResultItem = memo(function QuickSearchResultItem({
  conversation,
}: QuickSearchResultItemProps) {
  const { t, i18n } = useTranslation();
  const { spacingsTokens, colorsTokens } = useCunninghamTheme();
  const title = conversation.title || t('Untitled conversation');
  const project = conversation.project;
  const projectTitle = project?.title?.trim();

  const updatedAtLabel = useMemo(
    () => getRelativeTime(conversation.updated_at, i18n.language),
    [conversation.updated_at, i18n.language],
  );

  const ProjectIcon: ComponentType<SVGProps<SVGSVGElement>> | undefined =
    project?.icon ? (PROJECT_ICONS[project.icon] ?? undefined) : undefined;

  return (
    <Box
      $direction="row"
      $align="center"
      $gap={spacingsTokens.sm}
      $width="100%"
      $padding={{ vertical: 'xxs', horizontal: 'xs' }}
    >
      <BubbleIcon aria-hidden="true" color="brand" />
      <Box $flex={1} $direction="column" $minWidth={0}>
        <Text aria-label={title} $size="sm" $shrink={1}>
          {title}
        </Text>
        <Text $css={descriptionCss} $size="xs" $shrink={0}>
          <Box
            $direction="row"
            $align="center"
            $gap="4px"
            as="span"
            $display="inline-flex"
            style={{ color: colorsTokens['gray-500'] }}
          >
            {projectTitle && (
              <>
                {ProjectIcon && (
                  <ProjectIcon width={12} height={12} aria-hidden="true" />
                )}
                <span>{projectTitle}</span>
                {updatedAtLabel && <span>&bull;</span>}
              </>
            )}
            {updatedAtLabel && <span>{updatedAtLabel}</span>}
          </Box>
        </Text>
      </Box>
      <Box
        className="show-right-on-focus"
        $shrink={0}
        $css="color: var(--c--contextuals--content--semantic--brand--primary);"
      >
        <ArrowForwardIcon aria-hidden width={18} height={12} />
      </Box>
    </Box>
  );
});
