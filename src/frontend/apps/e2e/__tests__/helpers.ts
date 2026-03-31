import { Page, expect } from '@playwright/test';

export const createProject = async (page: Page, projectName: string) => {
  await page
    .getByRole('button', { name: /New project|Nouveau projet/ })
    .click();
  const createModal = page.getByRole('dialog', {
    name: /Content modal to create a project|Création de projet/,
  });
  await createModal
    .getByRole('textbox', { name: /Project name|Nom du projet/ })
    .fill(projectName);
  await createModal
    .getByRole('button', { name: /Create project|Créer un projet/ })
    .click();
  await expect(
    page.getByText(/The project has been created\.|Le projet a été créé\./),
  ).toBeVisible();
};
