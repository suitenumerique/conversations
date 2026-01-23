import { useCunninghamTheme } from '../useCunninghamTheme';

describe('<useCunninghamTheme />', () => {
  it('has the favicon correctly set', () => {
    expect(
      useCunninghamTheme.getState().componentTokens.favicon['png-light'],
    ).toBe('/assets/favicon-light.png');

    // Change theme
    useCunninghamTheme.getState().setTheme('dsfr');

    const { componentTokens } = useCunninghamTheme.getState();
    const favicon = componentTokens.favicon;
    expect(favicon['png-light']).toBe('/assets/favicon-light.png');
    expect(favicon['png-dark']).toBe('/assets/favicon-dark.png');
  });
});
