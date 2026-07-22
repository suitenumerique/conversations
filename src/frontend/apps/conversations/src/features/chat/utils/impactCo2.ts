export const IMPACT_CO2_COMPARISONS = 'rechercheweb,email,cafe,visioconference';

export const IMPACT_CO2_SCRIPT_URL = 'https://impactco2.fr/iframe.js';
export const IMPACT_CO2_WIDGET_TYPE = 'comparateur/etiquette-animee';

const formatNumericValue = (value: number): string =>
  value.toLocaleString('en-US', {
    maximumFractionDigits: 20,
    useGrouping: false,
  });

/** The impactco2 comparateur page expects the impact as a gram value (numeric string). */
export const formatImpactCo2Value = (co2ImpactKg: number): string =>
  formatNumericValue(co2ImpactKg * 1000);

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
    // Unlike the comparateur page, the iframe widget expects the value in kg
    value: formatNumericValue(co2ImpactKg),
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
