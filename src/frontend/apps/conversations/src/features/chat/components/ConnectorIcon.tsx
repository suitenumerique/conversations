import type { CSSProperties } from 'react';

import GenericConnectorIcon from '@/assets/icons/uikit-custom/puzzle-filled.svg?react';

interface ConnectorIconProps {
  /** The declared icon: an http(s) URL or a path served by the frontend. */
  icon: string | null;
  size?: number;
}

/**
 * A connector's icon, as its declaration gives it, or one generic icon.
 *
 * The declared icon is drawn as a mask filled with the text colour, like an
 * inline SVG painted with `currentColor`: it follows the theme, grey in the
 * menu and the brand colour in an active chip. Only its shape is kept, so a
 * multicoloured logo is drawn in a single colour.
 *
 * Decorative: the connector is always named next to it.
 */
export const ConnectorIcon = ({ icon, size = 16 }: ConnectorIconProps) => {
  if (!icon) {
    return (
      <GenericConnectorIcon
        width={size}
        height={size}
        aria-hidden="true"
        data-testid="connector-icon-generic"
      />
    );
  }

  const mask = `url("${icon}")`;
  const style: CSSProperties = {
    display: 'inline-block',
    flexShrink: 0,
    width: `${size}px`,
    height: `${size}px`,
    backgroundColor: 'currentColor',
    maskImage: mask,
    maskRepeat: 'no-repeat',
    maskPosition: 'center',
    maskSize: 'contain',
    WebkitMaskImage: mask,
    WebkitMaskRepeat: 'no-repeat',
    WebkitMaskPosition: 'center',
    WebkitMaskSize: 'contain',
  };

  return <span aria-hidden="true" data-testid="connector-icon" style={style} />;
};
