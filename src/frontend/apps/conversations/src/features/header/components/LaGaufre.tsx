import { LaGaufreV2 } from '@gouvfr-lasuite/ui-kit';

/**
 * App switcher ("la gaufre") bound to the LaSuite services catalog.
 *
 * Thin wrapper around the design system's LaGaufreV2: the popup anchors
 * itself to the trigger button (above the sidebar footer, below the home
 * header) and adapts to mobile, so no manual placement is needed.
 */
export const LaGaufre = () => {
  return (
    <LaGaufreV2
      apiUrl="https://lasuite.numerique.gouv.fr/api/services"
      label="Services de la Suite numérique"
      closeLabel="Fermer le menu"
      headerLabel="À propos"
      background="linear-gradient(#f1f2fd, rgba(255, 255, 255, 1) 20.54%, #FFF 0%"
      loadingText="Chargement…"
      newWindowLabelSuffix=" (nouvelle fenêtre)"
      viewMoreLabel="Voir plus"
      viewLessLabel="Voir moins"
      fontFamily="Marianne"
    />
  );
};
