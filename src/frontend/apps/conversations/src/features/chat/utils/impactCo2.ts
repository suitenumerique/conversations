export const IMPACT_CO2_COMPARISONS =
  'ordinateurfixeparticulier,hotel,disquedur,galettefromage';

export const IMPACT_CO2_SCRIPT_URL = 'https://impactco2.fr/iframe.js';
export const IMPACT_CO2_WIDGET_TYPE = 'comparateur/etiquette-animee';

/** impactco2 widgets expect the impact as a gram value (numeric string). */
export const formatImpactCo2Value = (co2ImpactKg: number): string =>
  (co2ImpactKg * 1000).toLocaleString('en-US', {
    maximumFractionDigits: 20,
    useGrouping: false,
  });

export const buildImpactCo2ComparateurUrl = (co2ImpactKg: number): string => {
  const params = new URLSearchParams({
    value: formatImpactCo2Value(co2ImpactKg),
    comparisons: IMPACT_CO2_COMPARISONS,
  });

  return `https://impactco2.fr/outils/comparateur?${params.toString()}`;
};

export const buildImpactCo2WidgetDataSearch = ({
  co2ImpactKg,
  language,
  theme,
}: {
  co2ImpactKg: number;
  language: 'fr' | 'en';
  theme: 'default' | 'night';
}): string => {
  const params = new URLSearchParams({
    value: formatImpactCo2Value(co2ImpactKg),
    comparisons: IMPACT_CO2_COMPARISONS,
    language,
    theme,
  });

  return `?${params.toString()}`;
};

/** Mount the impactco2 iframe script into a container (see https://impactco2.fr/iframe.js). */
export const mountImpactCo2Widget = (
  container: HTMLElement,
  dataSearch: string,
): void => {
  container.replaceChildren();
  const script = document.createElement('script');
  script.src = IMPACT_CO2_SCRIPT_URL;
  script.setAttribute('data-name', 'impact-co2');
  script.setAttribute('data-type', IMPACT_CO2_WIDGET_TYPE);
  script.setAttribute('data-search', dataSearch);
  container.appendChild(script);
};
