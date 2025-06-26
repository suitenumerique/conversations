import { execSync } from 'child_process';
import fs from 'fs';

describe('checks all the frontend translation are made', () => {
  it('checks missing translation. If this test fails, go to https://crowdin.com/', () => {
    // Extract the translations
    execSync(
      'yarn extract-translation:conversations -c ./i18next-parser.config.jest.mjs',
    );
    const outputCrowdin = './locales/conversations/translations-crowdin.json';
    const jsonCrowdin = JSON.parse(fs.readFileSync(outputCrowdin, 'utf8'));
    const listKeysCrowdin = Object.keys(jsonCrowdin).sort();

    // Check the translations in the app conversations
    const outputconversations =
      '../../apps/conversations/src/i18n/translations.json';
    const jsonconversations = JSON.parse(
      fs.readFileSync(outputconversations, 'utf8'),
    );

    // Our keys are in english, so we don't need to check the english translation
    Object.keys(jsonconversations)
      .filter((key) => key !== 'en')
      .forEach((key) => {
        const listKeysconversations = Object.keys(
          jsonconversations[key].translation,
        ).sort();
        const missingKeys = listKeysCrowdin.filter(
          (element) => !listKeysconversations.includes(element),
        );
        const additionalKeys = listKeysconversations.filter(
          (element) => !listKeysCrowdin.includes(element),
        );

        if (missingKeys.length > 0) {
          console.log(
            `Missing keys in conversations translations that should be translated in Crowdin, got to https://crowdin.com/ :`,
            missingKeys,
          );
        }

        if (additionalKeys.length > 0) {
          console.log(
            `Additional keys in conversations translations that seems not present in this branch:`,
            additionalKeys,
          );
        }

        expect(missingKeys.length).toBe(0);
      });
  });
});
