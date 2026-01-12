import { useCunninghamTheme } from '../useCunninghamTheme';

describe('<useCunninghamTheme />', () => {
  it('has the favicon correctly set', () => {
    const favicon1 = (
      useCunninghamTheme.getState().componentTokens as Record<string, unknown>
    ).favicon as { 'png-light': string; 'png-dark': string } | undefined;
    expect(favicon1?.['png-light']).toBe('/assets/favicon-light.png');

    // Change theme
    useCunninghamTheme.getState().setTheme('dsfr');

    const { componentTokens } = useCunninghamTheme.getState();
    const favicon = (componentTokens as Record<string, unknown>).favicon as
      | { 'png-light': string; 'png-dark': string }
      | undefined;
    expect(favicon?.['png-light']).toBe('/assets/favicon-light.png');
    expect(favicon?.['png-dark']).toBe('/assets/favicon-dark.png');
  });
});
