import { createGlobalStyle } from 'styled-components';

export const QuickSearchStyle = createGlobalStyle`
  .quick-search-container {
    position: relative;
    [cmdk-root] {
        width: 100%;
        position: relative;
        border-radius: 12px;
        overflow: hidden;
        transition: transform 100ms ease;
        outline: none;
        border: none;
  }

  [cmdk-input] {
    border: none;
    input::placeholder {
      font-size: 14px;
      color: var(--c--contextuals--content--semantic--neutral--tertiary) !important;
    }
  }

  [cmdk-item] {
    content-visibility: auto;
    cursor: pointer;  
    border-radius: var(--c--theme--spacings--xs);
    font-size: 14px;
    display: flex;
    align-items: center;
    gap: 8px;
    user-select: none;
    will-change: background, color;
    transition: all 150ms ease;
    transition-property: none;

    .show-right-on-focus {
      opacity: 0;
    }

    &:hover,
    &[data-selected='true'] {
      background: var(--c--theme--colors--gray-100);
      .show-right-on-focus {
        opacity: 1;
      }
    }

    &[data-disabled='true'] {
      color: var(--c--theme--colors--gray-500);
      cursor: not-allowed;
    }

    & + [cmdk-item] {
      margin-top: 4px;
    }
  }

  [cmdk-list] {
  
    padding: 0 var(--c--theme--spacings--base) var(--c--theme--spacings--base)
      var(--c--theme--spacings--base);
  
    flex:1;
    overflow-y: auto;
    overscroll-behavior: contain;
  }

  [cmdk-vercel-shortcuts] {
    display: flex;
    margin-left: auto;
    gap: 8px;

    kbd {
      font-size: 12px;
      min-width: 20px;
      padding: 4px;
      height: 20px;
      border-radius: 4px;
      color: white;
      background: var(--c--contextuals--content--semantic--neutral--tertiary);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      text-transform: uppercase;
    }
  }

  [cmdk-separator] {
    height: 1px;
    width: 100%;
    background: transparent;
    margin: 4px 0;
  }

  *:not([hidden]) + [cmdk-group] {
    margin-top: 8px;
  }

  [cmdk-group-heading] {
    padding: 0 var(--c--theme--spacings--xs);
    user-select: none;
    font-size: 12px;
    color: var(--c--theme--colors--gray-700);
    font-weight: 700;;
    margin-bottom: var(--c--theme--spacings--xs);
  }
}

.c__modal__scroller:has(.quick-search-container),
.c__modal__scroller:has(.noPadding) {
  padding: 0 !important;

  .c__modal__close .c__button {
    right: 5px;
    top: 5px;
    padding: 1.5rem 1rem;
  }

  .c__modal__title {
    font-size: var(--c--theme--font--sizes--xs);
    
    padding: var(--c--theme--spacings--base);
    margin-bottom: 0;
  }
}
`;
