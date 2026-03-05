import { Page, expect, test } from '@playwright/test';

import { randomName } from './common';

const createProject = async (page: Page, projectName: string) => {
  await page.getByRole('button', { name: 'New project' }).click();
  const createModal = page.getByRole('dialog', {
    name: 'Content modal to create a project',
  });
  await createModal
    .getByRole('textbox', { name: 'Project name' })
    .fill(projectName);
  await createModal.getByRole('button', { name: 'New project' }).click();
  await expect(page.getByText('The project has been created.')).toBeVisible();
};

test.describe('Left panel desktop', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('checks all the elements are visible', async ({ page }) => {
    await expect(page.getByTestId('left-panel-desktop')).toBeVisible();
    await expect(page.getByTestId('left-panel-mobile')).toBeHidden();
    await expect(page.getByRole('button', { name: 'New chat' })).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Search for a chat' }),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'New project' }),
    ).toBeVisible();
  });

  test('it displays the projects section', async ({ page, browserName }) => {
    const [projectName] = randomName('left-panel-project', browserName, 1);
    await createProject(page, projectName);

    const projectsSection = page.getByTestId('left-panel-projects');
    await expect(projectsSection).toBeVisible();
    await expect(projectsSection.getByText('Projects')).toBeVisible();

    // The created project item should be listed
    await expect(
      projectsSection.getByRole('button', { name: projectName, exact: true }),
    ).toBeVisible();
  });

  test('a standalone conversation appears in chats section only', async ({
    page,
    browserName,
  }) => {
    const [prompt] = randomName('standalone-conv', browserName, 1);

    // Send a message to create a standalone conversation
    const chatInput = page.getByRole('textbox', {
      name: 'Enter your message or a',
    });
    await chatInput.fill(prompt);
    await page.keyboard.press('Enter');

    // Wait for the conversation to appear in the left panel
    const chatsSection = page.getByTestId('left-panel-favorites');
    await expect(chatsSection).toBeVisible();
    const conversationLink = chatsSection
      .getByRole('link', { name: new RegExp(prompt) })
      .first();
    await expect(conversationLink).toBeVisible();

    // It should NOT appear in the projects section
    await expect(
      page.getByTestId('left-panel-projects').getByText(prompt),
    ).toHaveCount(0);
  });

  test('a project conversation appears in the project it belongs to, not in chat section', async ({
    page,
    browserName,
  }) => {
    const [projectName] = randomName('left-panel-conv', browserName, 1);
    await createProject(page, projectName);

    const projectsSection = page.getByTestId('left-panel-projects');
    const projectButton = projectsSection.getByRole('button', {
      name: projectName,
      exact: true,
    });
    await expect(projectButton).toBeVisible();

    // Start a new conversation in the project
    await projectButton.hover();
    const projectRow = projectButton.locator('..');
    await projectRow
      .getByRole('button', { name: 'New conversation in project' })
      .click();

    // Send a message to materialize the conversation
    const [prompt] = randomName('project-conv', browserName, 1);
    const chatInput = page.getByRole('textbox', {
      name: 'Enter your message or a',
    });
    await chatInput.fill(prompt);
    await page.keyboard.press('Enter');

    // Wait for assistant response
    await expect(page.getByTestId('assistant-message-content')).toBeVisible();

    // The project should auto-expand and show the conversation
    await expect(
      projectsSection.getByRole('link', { name: new RegExp(prompt) }).first(),
    ).toBeVisible();

    // It should NOT appear in the standalone "Your chats" section
    await expect(
      page.getByTestId('left-panel-favorites').getByText(prompt),
    ).toHaveCount(0);
  });

  test('it shows project actions on hover', async ({ page, browserName }) => {
    const [projectName] = randomName('left-panel-actions', browserName, 1);
    await createProject(page, projectName);

    const projectsSection = page.getByTestId('left-panel-projects');
    const projectButton = projectsSection.getByRole('button', {
      name: projectName,
      exact: true,
    });
    await expect(projectButton).toBeVisible();

    // Hover to reveal action buttons
    await projectButton.hover();
    const projectRow = projectButton.locator('..');

    await expect(
      projectRow.getByRole('button', { name: /Actions list for project/ }),
    ).toBeVisible();
    await expect(
      projectRow.getByRole('button', {
        name: 'New conversation in project',
      }),
    ).toBeVisible();
  });
});

test.describe('Left panel mobile', () => {
  test.use({ viewport: { width: 500, height: 1200 } });

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });
});
