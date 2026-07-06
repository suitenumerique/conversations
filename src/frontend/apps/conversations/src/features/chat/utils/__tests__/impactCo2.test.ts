import {
  buildImpactCo2ComparateurUrl,
  buildImpactCo2WidgetDataSearch,
  formatImpactCo2Value,
  mountImpactCo2Widget,
} from '../impactCo2';

const TEST_CO2_IMPACT_KG = 0.00002191613089507352;

describe('impactCo2', () => {
  it('formats kg CO₂eq as a gram value for impactco2', () => {
    expect(formatImpactCo2Value(TEST_CO2_IMPACT_KG)).toBe(
      '0.021916130895073518',
    );
  });

  it('builds the comparateur URL with value and comparisons', () => {
    expect(buildImpactCo2ComparateurUrl(TEST_CO2_IMPACT_KG)).toBe(
      'https://impactco2.fr/outils/comparateur?value=0.021916130895073518&comparisons=ordinateurfixeparticulier%2Chotel%2Cdisquedur%2Cgalettefromage',
    );
  });

  it('builds widget data-search with theme and language', () => {
    expect(
      buildImpactCo2WidgetDataSearch({
        co2ImpactKg: TEST_CO2_IMPACT_KG,
        language: 'fr',
        theme: 'night',
      }),
    ).toBe(
      '?value=0.021916130895073518&comparisons=ordinateurfixeparticulier%2Chotel%2Cdisquedur%2Cgalettefromage&language=fr&theme=night',
    );
  });

  it('mounts the impactco2 script with the expected data attributes', () => {
    const container = document.createElement('div');
    const dataSearch = buildImpactCo2WidgetDataSearch({
      co2ImpactKg: TEST_CO2_IMPACT_KG,
      language: 'en',
      theme: 'default',
    });

    mountImpactCo2Widget(container, dataSearch);

    const script = container.querySelector('script[data-name="impact-co2"]');
    expect(script).not.toBeNull();
    expect(script?.getAttribute('data-type')).toBe(
      'comparateur/etiquette-animee',
    );
    expect(script?.getAttribute('data-search')).toContain('value=0.0219161');
    expect(script?.getAttribute('data-search')).toContain('language=en');
    expect(script?.getAttribute('data-search')).toContain('theme=default');
  });
});
