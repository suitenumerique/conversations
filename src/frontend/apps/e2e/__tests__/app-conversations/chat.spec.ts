import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/home/');
});

test.describe('Chat page', () => {
  test('it checks the page is displayed properly', async ({ page }) => {
    await page.goto('/');

    const newChatButton = page.getByRole('button', { name: 'New chat' });
    await expect(newChatButton).toBeVisible();

    const chatInput = page.getByRole('textbox', {
      name: 'Enter your message or a',
    });
    await expect(chatInput).toBeVisible();

    const attachmentButton = page.getByRole('button', {
      name: 'Add attach file',
    });
    await expect(attachmentButton).toBeVisible();

    const websearchButton = page.getByRole('button', {
      name: 'Research on the web',
    });
    await expect(websearchButton).toBeVisible();

    const sendMessageButton = page.getByRole('button', { name: 'Send' });
    await expect(sendMessageButton).toBeVisible();
  });

  test('the user can chat with LLM (simple)', async ({ page }) => {
    await page.goto('/');

    const newChatButton = page.getByRole('button', { name: 'New chat' });
    await expect(newChatButton).toBeVisible();

    const chatInput = page.getByRole('textbox', {
      name: 'Enter your message or a',
    });
    await chatInput.click();
    await chatInput.fill('Hello, how are you?');

    const sendMessageButton = page.getByRole('button', { name: 'Send' });
    await expect(sendMessageButton).toBeEnabled();

    await page.keyboard.press('Enter');

    // Wait for the response to appear
    await page
      .getByRole('button', { name: 'See more' })
      .waitFor({ timeout: 10000 });

    const copyButton = page.getByRole('button', { name: 'Copy' });
    await expect(copyButton).toBeVisible();

    const messageContent = page.getByTestId('assistant-message-content');
    await expect(messageContent).toBeVisible();
    await expect(messageContent).not.toBeEmpty(); 

    // Check history
    const chatHistoryLink = page
      .getByRole('link', { name: 'Simple chat icon Hello, how' })
      .first();
    await expect(chatHistoryLink).toBeVisible();

    await newChatButton.click();

    await page
      .getByRole('heading', { name: 'What is on your mind?' })
      .isVisible();

    await chatHistoryLink.click();
    await expect(messageContent).toBeVisible();
  });
});
