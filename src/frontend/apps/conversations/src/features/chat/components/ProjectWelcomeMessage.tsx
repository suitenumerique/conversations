import { type ReactNode, memo, useMemo } from 'react';

import { Box } from '@/components';
import { useCunninghamTheme } from '@/cunningham';
import { useInfiniteProjects } from '@/features/chat/api/useProjects';
import { usePendingChatStore } from '@/features/chat/stores/usePendingChatStore';
import {
  PROJECT_COLORS,
  PROJECT_ICONS,
} from '@/features/left-panel/components/projects/project-constants';

import { WelcomeLayout } from './WelcomeLayout';

interface ProjectWelcomeMessageProps {
  fallback: ReactNode;
}

export const ProjectWelcomeMessage = memo(function ProjectWelcomeMessage({
  fallback,
}: ProjectWelcomeMessageProps) {
  const projectId = usePendingChatStore((s) => s.projectId);
  const { colorsTokens } = useCunninghamTheme();
  const projects = useInfiniteProjects({ page: 1 });

  const project = useMemo(() => {
    if (!projectId) return undefined;
    return projects.data?.pages
      .flatMap((page) => page.results)
      .find((p) => p.id === projectId);
  }, [projectId, projects.data]);

  if (!project) {
    return <>{fallback}</>;
  }

  const IconComp = PROJECT_ICONS[project.icon] ?? PROJECT_ICONS.folder;
  const iconColor =
    colorsTokens[PROJECT_COLORS[project.color] as keyof typeof colorsTokens] ??
    undefined;

  return (
    <WelcomeLayout
      title={project.title}
      icon={
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
      }
    />
  );
});
