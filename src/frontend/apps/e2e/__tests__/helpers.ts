import { Page, expect } from '@playwright/test';

export const createProject = async (page: Page, projectName: string) => {
  await page.getByRole('button', { name: 'New project' }).click();
  const createModal = page.getByRole('dialog', {
    name: 'Content modal to create a project',
  });
  await createModal
    .getByRole('textbox', { name: 'Project name' })
    .fill(projectName);
  await createModal.getByRole('button', { name: 'Create project' }).click();
  await expect(page.getByText('The project has been created.')).toBeVisible();
};
