import { errorCauses, getCSRFToken } from '@/api';

describe('utils', () => {
  describe('errorCauses', () => {
    const createMockResponse = (
      jsonData: any,
      status = 400,
      headers: Record<string, string> = {},
    ): Response => {
      return {
        status,
        headers: new Headers(headers),
        json: () => jsonData,
      } as unknown as Response;
    };

    it('parses multiple string causes from error body', async () => {
      const mockResponse = createMockResponse(
        {
          field: ['error message 1', 'error message 2'],
        },
        400,
      );

      const result = await errorCauses(mockResponse, { context: 'login' });

      expect(result.status).toBe(400);
      expect(result.cause).toEqual(['error message 1', 'error message 2']);
      expect(result.data).toEqual({ context: 'login' });
    });

    it('returns undefined causes if no JSON body', async () => {
      const mockResponse = createMockResponse(null, 500);

      const result = await errorCauses(mockResponse);

      expect(result.status).toBe(500);
      expect(result.cause).toBeUndefined();
      expect(result.data).toBeUndefined();
    });

    it('reads the retry delay from the Retry-After header', async () => {
      const mockResponse = createMockResponse({ detail: 'throttled' }, 429, {
        'Retry-After': '3218',
      });

      const result = await errorCauses(mockResponse);

      expect(result.status).toBe(429);
      expect(result.retryAfter).toBe(3218);
    });

    it('leaves the retry delay undefined without a usable header', async () => {
      const withoutHeader = await errorCauses(createMockResponse({}, 400));
      const withGarbage = await errorCauses(
        createMockResponse({}, 400, { 'Retry-After': 'soon' }),
      );

      expect(withoutHeader.retryAfter).toBeUndefined();
      expect(withGarbage.retryAfter).toBeUndefined();
    });
  });

  describe('getCSRFToken', () => {
    it('extracts csrftoken from document.cookie', () => {
      Object.defineProperty(document, 'cookie', {
        writable: true,
        value: 'sessionid=xyz; csrftoken=abc123; theme=dark',
      });

      expect(getCSRFToken()).toBe('abc123');
    });

    it('returns undefined if csrftoken is not present', () => {
      Object.defineProperty(document, 'cookie', {
        writable: true,
        value: 'sessionid=xyz; theme=dark',
      });

      expect(getCSRFToken()).toBeUndefined();
    });
  });
});
