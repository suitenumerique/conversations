import { useRouter } from 'next/navigation';
import { memo, useCallback, useEffect, useRef } from 'react';
import styled, { RuleSet } from 'styled-components';

interface StyledLinkProps {
  $css?: string | RuleSet<object>;
}

const Anchor = styled.a<StyledLinkProps>`
  text-decoration: none;
  color: #ffffff;
  display: flex;
  cursor: pointer;
  ${({ $css }) => $css && (typeof $css === 'string' ? `${$css}` : $css)}
`;

interface Props extends React.AnchorHTMLAttributes<HTMLAnchorElement> {
  href: string;
  $css?: string | RuleSet<object>;
}

/**
 * Link that avoids re-renders from Next.js router context.
 *
 * Use instead of Next.js `Link` in large lists (sidebars, tables) where
 * router-triggered re-renders cause performance issues.
 *
 * Warning: No automatic prefetching.
 *
 */
export const StyledLink = memo(function StyledLink({
  href,
  onClick,
  ...props
}: Props) {
  const router = useRouter();
  const routerRef = useRef(router);

  // avoid rerenders
  useEffect(() => {
    routerRef.current = router;
  }, [router]);

  // Memoized click handler to maintain stable reference across re-renders.
  // Necessary for memo() to work correctly
  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLAnchorElement>) => {
      // Allow default browser behavior for modifier keys (new tab, etc.)
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
        return;
      }

      e.preventDefault();
      onClick?.(e);
      routerRef.current.push(href);
    },
    [href, onClick],
  );

  return <Anchor href={href} onClick={handleClick} {...props} />;
});
