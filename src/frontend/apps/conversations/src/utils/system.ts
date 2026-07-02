export const sleep = (ms: number) =>
  new Promise((resolve) => setTimeout(resolve, ms));

// Navigates the current context to the given URL. Wrapped so it can be mocked
// in tests: jsdom seals window.location and no longer lets it be reassigned.
export const navigate = (url: string) => {
  window.location.href = url;
};
