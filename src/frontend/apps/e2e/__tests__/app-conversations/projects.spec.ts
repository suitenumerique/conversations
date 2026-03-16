import { expect, test } from '@playwright/test';

import { randomName } from './common';

test.describe('Projects', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('checks the create project button is visible', async ({ page }) => {
    const createButton = page.getByRole('button', { name: 'Create project' });
    await expect(createButton).toBeVisible();
  });

  test('it creates a project', async ({ page, browserName }) => {
    const [projectName] = randomName('project', browserName, 1);

    const createButton = page.getByRole('button', { name: 'Create project' });
    await createButton.click();

    // Modal should open
    const modal = page.getByRole('dialog', {
      name: 'Content modal to create a project',
    });
    await expect(modal).toBeVisible();

    // Fill the project name
    const nameInput = modal.getByRole('textbox', { name: 'Project name' });
    await nameInput.fill(projectName);

    // Submit
    const submitButton = modal.getByRole('button', { name: 'Create project' });
    await expect(submitButton).toBeEnabled();
    await submitButton.click();

    // Toast confirmation
    await expect(
      page.getByText('The project has been created.'),
    ).toBeVisible();

    // Project should appear in the left panel
    await expect(page.getByText(projectName)).toBeVisible();
  });

  test('it edits a project', async ({ page, browserName }) => {
    const [projectName] = randomName('project-edit', browserName, 1);
    const updatedName = `${projectName}-updated`;

    // Create a project first
    await page.getByRole('button', { name: 'Create project' }).click();
    const createModal = page.getByRole('dialog', {
      name: 'Content modal to create a project',
    });
    await createModal.getByRole('textbox', { name: 'Project name' }).fill(projectName);
    await createModal.getByRole('button', { name: 'Create project' }).click();
    await expect(page.getByText('The project has been created.')).toBeVisible();

    // Hover the project item to reveal actions
    const projectItem = page.getByText(projectName);
    await projectItem.hover();

    // Open the actions menu
    const actionsButton = page.getByLabel(
      `Actions list for project ${projectName}`,
    );
    await actionsButton.click();

    // Click settings
    await page.getByText('Project settings').click();

    // Edit the name
    const settingsModal = page.getByRole('dialog', {
      name: 'Project settings',
    });
    await expect(settingsModal).toBeVisible();

    const nameInput = settingsModal.getByRole('textbox', {
      name: 'Project name',
    });
    await nameInput.clear();
    await nameInput.fill(updatedName);

    await settingsModal.getByRole('button', { name: 'Save' }).click();

    // Toast confirmation
    await expect(
      page.getByText('The project has been updated.'),
    ).toBeVisible();

    // Updated name should appear
    await expect(page.getByText(updatedName)).toBeVisible();
  });

  test('it deletes a project', async ({ page, browserName }) => {
    const [projectName] = randomName('project-delete', browserName, 1);

    // Create a project first
    await page.getByRole('button', { name: 'Create project' }).click();
    const createModal = page.getByRole('dialog', {
      name: 'Content modal to create a project',
    });
    await createModal.getByRole('textbox', { name: 'Project name' }).fill(projectName);
    await createModal.getByRole('button', { name: 'Create project' }).click();
    await expect(page.getByText('The project has been created.')).toBeVisible();

    // Hover and open actions
    await page.getByText(projectName).hover();
    await page
      .getByLabel(`Actions list for project ${projectName}`)
      .click();

    // Click delete
    await page.getByText('Delete project').click();

    // Confirm deletion
    const deleteModal = page.getByTestId('delete-project-confirm');
    await expect(deleteModal).toBeVisible();
    await expect(
      deleteModal.getByText(`Are you sure you want to delete the "${projectName}" project?`, { exact: false }),
    ).toBeVisible();

    await page.getByRole('button', { name: 'Confirm deletion' }).click();

    // Toast confirmation
    await expect(
      page.getByText('The project has been deleted.'),
    ).toBeVisible();

    // Project should no longer be visible
    await expect(page.getByText(projectName)).toBeHidden();
  });

  test('it expands and collapses a project', async ({ page, browserName }) => {
    const [projectName] = randomName('project-toggle', browserName, 1);

    // Create a project first
    await page.getByRole('button', { name: 'Create project' }).click();
    const createModal = page.getByRole('dialog', {
      name: 'Content modal to create a project',
    });
    await createModal.getByRole('textbox', { name: 'Project name' }).fill(projectName);
    await createModal.getByRole('button', { name: 'Create project' }).click();
    await expect(page.getByText('The project has been created.')).toBeVisible();

    // Click the project to expand it
    const projectHeader = page.getByRole('button', { name: projectName, exact: true });
    await projectHeader.click();

    // Should show "No conversations" when expanded
    await expect(page.getByText('No conversations')).toBeVisible();

    // Click again to collapse
    await projectHeader.click();
    await expect(page.getByText('No conversations')).toBeHidden();
  });
});
