import { expect, test } from '@playwright/test';

import { createProject } from '../helpers';

import { randomName } from './common';

test.describe('Projects', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('checks the create project button is visible', async ({ page }) => {
    const createButton = page.getByRole('button', {
      name: /New project|Nouveau projet/,
    });
    await expect(createButton).toBeVisible();
  });

  test('it creates a project', async ({ page, browserName }) => {
    const [projectName] = randomName('project', browserName, 1);
    await createProject(page, projectName);

    // Project should appear in the left panel
    await expect(page.getByText(projectName)).toBeVisible();
  });

  test('it edits a project', async ({ page, browserName }) => {
    const [projectName] = randomName('project-edit', browserName, 1);
    const updatedName = `${projectName}-updated`;

    await createProject(page, projectName);

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
    await expect(page.getByText('The project has been updated.')).toBeVisible();

    // Updated name should appear
    await expect(page.getByText(updatedName)).toBeVisible();
  });

  test('it deletes a project', async ({ page, browserName }) => {
    const [projectName] = randomName('project-delete', browserName, 1);

    await createProject(page, projectName);

    // Hover and open actions
    await page.getByText(projectName).hover();
    await page.getByLabel(`Actions list for project ${projectName}`).click();

    // Click delete
    await page.getByText('Delete project').click();

    // Confirm deletion
    const deleteModal = page.getByTestId('delete-project-confirm');
    await expect(deleteModal).toBeVisible();
    await expect(
      deleteModal.getByText(
        `Are you sure you want to delete the "${projectName}" project?`,
        { exact: false },
      ),
    ).toBeVisible();

    await page.getByRole('button', { name: 'Confirm deletion' }).click();

    // Toast confirmation
    await expect(page.getByText('The project has been deleted.')).toBeVisible();

    // Project should no longer be visible
    await expect(page.getByText(projectName)).toBeHidden();
  });

  test('it expands and collapses a project', async ({ page, browserName }) => {
    const [projectName] = randomName('project-toggle', browserName, 1);
    const [prompt] = randomName('project-toggle-conv', browserName, 1);

    await createProject(page, projectName);

    // Create one conversation so the toggle button is enabled
    await page
      .getByRole('button', {
        name: `Start new conversation in ${projectName}`,
        exact: true,
      })
      .click();
    const chatInput = page.getByRole('textbox', {
      name: /Enter your message|Entrez votre message/i,
    });
    await chatInput.fill(prompt);
    await page.keyboard.press('Enter');

    // Toggle project conversations
    const projectHeader = page.getByRole('button', {
      name: `Toggle conversations for ${projectName}`,
      exact: true,
    });
    await expect(projectHeader).toBeEnabled();
    const initialExpanded = await projectHeader.getAttribute('aria-expanded');
    expect(initialExpanded).not.toBeNull();
    if (!initialExpanded) {
      throw new Error('Project toggle should expose aria-expanded.');
    }
    await projectHeader.click();

    // Should invert state after first click
    const toggledExpanded = initialExpanded === 'true' ? 'false' : 'true';
    await expect(projectHeader).toHaveAttribute(
      'aria-expanded',
      toggledExpanded,
    );

    // Click again to collapse
    await projectHeader.click();
    await expect(projectHeader).toHaveAttribute(
      'aria-expanded',
      initialExpanded,
    );
  });
});
