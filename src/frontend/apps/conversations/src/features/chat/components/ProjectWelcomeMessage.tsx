import { InfiniteData, useQueryClient } from '@tanstack/react-query';
import { type ReactNode, memo, useMemo } from 'react';

import { Box, Text } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import {
  KEY_LIST_PROJECT,
  ProjectsResponse,
} from '@/features/chat/api/useProjects';
import { usePendingChatStore } from '@/features/chat/stores/usePendingChatStore';
import {
  PROJECT_COLORS,
  PROJECT_ICONS,
} from '@/features/left-panel/components/projects/project-constants';

const WELCOME_PADDING = { all: 'base', bottom: 'md' } as const;
const WELCOME_MARGIN = {
  horizontal: 'base',
  bottom: 'md',
  top: '-105px',
} as const;
const WELCOME_TEXT_MARGIN = { all: '0' } as const;

interface ProjectWelcomeMessageProps {
  fallback: ReactNode;
}

export const ProjectWelcomeMessage = memo(function ProjectWelcomeMessage({
  fallback,
}: ProjectWelcomeMessageProps) {
  const projectId = usePendingChatStore((s) => s.projectId);
  const queryClient = useQueryClient();
  const { colorsTokens } = useCunninghamTheme();

  // Look up the project from the already-fetched infinite projects cache
  const project = useMemo(() => {
    if (!projectId) return undefined;
    const projectsData = queryClient.getQueryData<
      InfiniteData<ProjectsResponse>
    >([KEY_LIST_PROJECT, { page: 1 }]);
    return projectsData?.pages
      .flatMap((page) => page.results)
      .find((p) => p.id === projectId);
  }, [projectId, queryClient]);

  if (!project) {
    return <>{fallback}</>;
  }

  const IconComp = PROJECT_ICONS[project.icon] ?? PROJECT_ICONS.folder;
  const iconColor =
    colorsTokens[PROJECT_COLORS[project.color] as keyof typeof colorsTokens] ??
    undefined;

  return (
    <Box $padding={WELCOME_PADDING} $align="center" $margin={WELCOME_MARGIN}>
      <Box $direction="row" $align="center" $gap="10px">
        <Box
          $display="flex"
          $align="center"
          $justify="center"
          $width="32px"
          $height="32px"
          style={{ color: iconColor, flexShrink: 0 }}
        >
          <IconComp
            width={32}
            height={32}
            style={{ fill: 'currentColor', display: 'block' }}
          />
        </Box>
        <Text as="h2" $size="xl" $weight="600" $margin={WELCOME_TEXT_MARGIN}>
          {project.title}
        </Text>
      </Box>
    </Box>
  );
});
