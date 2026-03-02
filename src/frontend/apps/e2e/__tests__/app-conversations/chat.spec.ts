import { expect, test } from '@playwright/test';

import { overrideConfig } from './common';

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

  test('the user can paste a document into the chat input', async ({
    page,
  }) => {
    await overrideConfig(page, {
      FEATURE_FLAGS: {
        'document-upload': 'enabled',
        'web-search': 'enabled',
      },
    });

    await page.goto('/');

    const chatInput = page.getByRole('textbox', {
      name: 'Enter your message or a',
    });
    await expect(chatInput).toBeVisible();
    await chatInput.click();

    // Create a test file content
    const fileContent = 'Test document content for paste';
    const fileName = 'test-document.txt';
    const fileType = 'text/plain';

    // Simulate paste event with file
    await page.evaluate(
      ({ content, name, type }) => {
        const textarea = document.querySelector(
          'textarea[name="inputchat-textarea"]',
        ) as HTMLTextAreaElement;
        if (!textarea) return;

        // Create a File object
        const file = new File([content], name, { type });

        // Create a DataTransfer object to simulate clipboard
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);

        // Create a paste event - ClipboardEvent constructor doesn't accept clipboardData
        // so we create a regular Event and add clipboardData property
        const pasteEvent = new Event('paste', {
          bubbles: true,
          cancelable: true,
        }) as unknown as ClipboardEvent;

        // Define clipboardData property to make it accessible
        Object.defineProperty(pasteEvent, 'clipboardData', {
          value: {
            files: dataTransfer.files,
            items: dataTransfer.items,
            types: Array.from(dataTransfer.types),
            getData: () => '',
            setData: () => {},
          },
          writable: false,
          configurable: true,
        });

        textarea.dispatchEvent(pasteEvent);
      },
      { content: fileContent, name: fileName, type: fileType },
    );

    // Wait for the file to be processed and appear in the attachment list
    // The attachment should be visible with the file name
    const attachment = page.getByText(fileName, { exact: false }).first();
    await expect(attachment).toBeVisible({ timeout: 5000 });
  });
});
