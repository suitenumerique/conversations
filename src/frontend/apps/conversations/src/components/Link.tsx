import { memo, useCallback, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router';
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
 * Link that avoids re-renders from the router context.
 *
 * Use instead of the router `Link` in large lists (sidebars, tables) where
 * router-triggered re-renders cause performance issues.
 *
 */
export const StyledLink = memo(function StyledLink({
  href,
  onClick,
  ...props
}: Props) {
  const navigate = useNavigate();
  const navigateRef = useRef(navigate);

  // avoid rerenders
  useEffect(() => {
    navigateRef.current = navigate;
  }, [navigate]);

  // Memoized click handler to maintain stable reference across re-renders.
  // Necessary for memo() to work correctly
  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLAnchorElement>) => {
      // Allow default browser behavior for modifier keys (new tab, etc.)
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
        return;
      }

      if (props.target === '_blank') {
        return;
      }

      e.preventDefault();
      onClick?.(e);
      void navigateRef.current(href);
    },
    [href, onClick, props.target],
  );

  return <Anchor href={href} onClick={handleClick} {...props} />;
});
