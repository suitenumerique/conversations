import { Page, expect, test } from '@playwright/test';

import { overrideConfig } from './common';

/**
 * Simulates pasting files into the chat textarea.
 */
const pasteFile = async (
  page: Page,
  {
    content,
    name,
    type,
    lastModified,
  }: { content: string; name: string; type: string; lastModified?: number },
) => {
  await page.evaluate(
    ({ content, name, type, lastModified }) => {
      const textarea = document.querySelector(
        'textarea[name="inputchat-textarea"]',
      ) as HTMLTextAreaElement;
      if (!textarea) return;

      const file = new File([content], name, {
        type,
        ...(lastModified !== undefined && { lastModified }),
      });
      const dataTransfer = new DataTransfer();
      dataTransfer.items.add(file);

      const pasteEvent = new Event('paste', {
        bubbles: true,
        cancelable: true,
      }) as unknown as ClipboardEvent;

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
    { content, name, type, lastModified },
  );
};

test.describe('File paste in chat input', () => {
  test.beforeEach(async ({ page }) => {
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
  });

  test('the user can paste a document into the chat input', async ({
    page,
  }) => {
    const fileContent = 'Test document content for paste';
    const fileName = 'test-document.txt';
    const fileType = 'text/plain';

    await pasteFile(page, {
      content: fileContent,
      name: fileName,
      type: fileType,
    });

    const attachment = page.getByText(fileName, { exact: false }).first();
    await expect(attachment).toBeVisible({ timeout: 5000 });
  });

  test('pasting a PDF file adds it as an attachment', async ({ page }) => {
    await pasteFile(page, {
      content: '%PDF-1.4 fake content',
      name: 'report.pdf',
      type: 'application/pdf',
    });

    await expect(page.getByText('report.pdf')).toBeVisible({ timeout: 5000 });
  });

  test('pasting an image file adds it as an attachment', async ({ page }) => {
    await pasteFile(page, {
      content: 'fake-png-data',
      name: 'screenshot.png',
      type: 'image/png',
    });

    await expect(page.getByText('screenshot.png')).toBeVisible({
      timeout: 5000,
    });
  });

  test('pasting an unsupported file type shows an error toast', async ({
    page,
  }) => {
    await pasteFile(page, {
      content: 'binary data',
      name: 'archive.zip',
      type: 'application/zip',
    });

    await expect(page.getByText('File type not supported')).toBeVisible({
      timeout: 5000,
    });

    // The file should NOT appear as an attachment
    await expect(page.getByText('archive.zip')).toBeHidden();
  });

  test('pasting a file when upload is disabled does nothing', async ({
    page,
  }) => {
    // Re-override config with upload disabled
    await overrideConfig(page, {
      FEATURE_FLAGS: {
        'document-upload': 'disabled',
        'web-search': 'enabled',
      },
    });
    await page.goto('/');

    const chatInput = page.getByRole('textbox', {
      name: 'Enter your message or a',
    });
    await expect(chatInput).toBeVisible();
    await chatInput.click();

    await pasteFile(page, {
      content: 'Hello world',
      name: 'notes.txt',
      type: 'text/plain',
    });

    // No attachment should appear
    await expect(page.getByText('notes.txt')).toBeHidden();
    await expect(
      page.getByRole('button', { name: 'Remove attachment' }),
    ).toBeHidden();
  });

  test('pasting the same file twice does not create a duplicate', async ({
    page,
  }) => {
    const file = {
      content: 'duplicate test',
      name: 'duplicate.txt',
      type: 'text/plain',
      lastModified: 1700000000000,
    };

    await pasteFile(page, file);
    await expect(page.getByText('duplicate.txt')).toBeVisible({
      timeout: 5000,
    });

    await pasteFile(page, file);

    const removeButtons = page.getByRole('button', {
      name: 'Remove attachment',
    });
    await expect(removeButtons).toHaveCount(1);
  });

  test('pasting multiple different files shows all attachments', async ({
    page,
  }) => {
    await pasteFile(page, {
      content: 'text content',
      name: 'first.txt',
      type: 'text/plain',
    });
    await expect(page.getByText('first.txt')).toBeVisible({ timeout: 5000 });

    await pasteFile(page, {
      content: '%PDF-1.4 content',
      name: 'second.pdf',
      type: 'application/pdf',
    });
    await expect(page.getByText('second.pdf')).toBeVisible({ timeout: 5000 });

    // 2 attachments should be visible
    await expect(page.getByText('first.txt')).toBeVisible();
    const removeButtons = page.getByRole('button', {
      name: 'Remove attachment',
    });
    await expect(removeButtons).toHaveCount(2);
  });

  test('removing a pasted attachment works', async ({ page }) => {
    await pasteFile(page, {
      content: 'to be removed',
      name: 'removeme.txt',
      type: 'text/plain',
    });
    await expect(page.getByText('removeme.txt')).toBeVisible({
      timeout: 5000,
    });

    await page.getByRole('button', { name: 'Remove attachment' }).click();

    await expect(page.getByText('removeme.txt')).toBeHidden();
    await expect(
      page.getByRole('button', { name: 'Remove attachment' }),
    ).toBeHidden();
  });

  test('pasting text (not a file) should not create an attachment', async ({
    page,
  }) => {
    const chatInput = page.getByRole('textbox', {
      name: 'Enter your message or a',
    });

    await page.evaluate(() => {
      const textarea = document.querySelector(
        'textarea[name="inputchat-textarea"]',
      ) as HTMLTextAreaElement;
      if (!textarea) return;

      const pasteEvent = new Event('paste', {
        bubbles: true,
        cancelable: true,
      }) as unknown as ClipboardEvent;

      Object.defineProperty(pasteEvent, 'clipboardData', {
        value: {
          files: new DataTransfer().files,
          items: [],
          types: ['text/plain'],
          getData: () => 'just plain text',
          setData: () => {},
        },
        writable: false,
        configurable: true,
      });

      textarea.dispatchEvent(pasteEvent);
    });

    // No attachment should be visible
    await expect(
      page.getByRole('button', { name: 'Remove attachment' }),
    ).toBeHidden();

    // Textarea still there
    await expect(chatInput).toBeVisible();
  });
});
