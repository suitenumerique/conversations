import { createGlobalStyle } from 'styled-components';

export const TabsStyle = createGlobalStyle`
 .c__tabs {
  display: flex;

  .react-aria-Tabs {
    display: flex;
    width: 100%;
  }

  .react-aria-TabList {
    display: flex;
    width: 100%;
    flex-direction: column;
  }

  .react-aria-Tab {
    padding: 10px;
    cursor: pointer;
    font-weight: 400;
    font-size: var(--c--globals--font--sizes--sm);
    color: var(--c--contextuals--content--semantic--neutral--primary);
    outline: none;
    border: none;
    border-radius: 4px;
    letter-spacing: -0.01em;
    position: relative;
    transition: color 200ms;
    line-height: var(--c--globals--font--sizes--md);
    forced-color-adjust: none;
    display: flex;
    align-items: center;
    gap: var(--c--globals--spacings--sm);

    &__subtext {
      display: block;
      font-weight: 400;
      line-height: var(--c--globals--font--sizes--md);
      font-size: var(--c--globals--font--sizes--xs);
      color: var(--c--contextuals--content--semantic--neutral--secondary);
    }

    &[data-hovered] {
      background-color: var(
        --c--contextuals--background--semantic--overlay--primary
      );
    }

    &[data-selected] {
      font-weight: 700;
      padding-bottom: 10px;
      color: var(--c--contextuals--content--semantic--neutral--primary);
      background-color:
        var(--c--contextuals--background--semantic--overlay--primary);
      border: none;
    }

    &[data-disabled] {
      color: var(--text-color-disabled);
      &[data-selected] {
        --border-color: var(--text-color-disabled);
      }
    }

    &[data-focus-visible]:after {
      content: "";
      position: absolute;
      inset: 4px;
      border-radius: 4px;
      border: 2px solid var(--focus-ring-color);
    }
  }

  .react-aria-TabPanel {
    margin-top: 4px;
    padding: 10px;
    border-radius: 4px;
    outline: none;

    &[data-focus-visible] {
      outline: 2px solid var(--focus-ring-color);
    }
  }
}
`