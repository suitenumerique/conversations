import { renderHook } from '@testing-library/react';

import { useFileUrls } from '../useFileUrls';

const createFile = (
  name: string,
  size: number = 100,
  lastModified: number = 1234567890,
): File => {
  const file = new File(['x'.repeat(size)], name, { type: 'text/plain' });
  Object.defineProperty(file, 'size', { value: size });
  Object.defineProperty(file, 'lastModified', { value: lastModified });
  return file;
};

const createFileList = (files: File[]): FileList => {
  return {
    length: files.length,
    item: (index: number) => files[index] || null,
    [Symbol.iterator]: function* () {
      for (const file of files) {
        yield file;
      }
    },
    ...files.reduce(
      (acc, file, index) => {
        acc[index] = file;
        return acc;
      },
      {} as Record<number, File>,
    ),
  } as FileList;
};

describe('useFileUrls', () => {
  let urlCounter: number;
  const mockCreateObjectURL = jest.fn();
  const mockRevokeObjectURL = jest.fn();

  beforeEach(() => {
    urlCounter = 0;
    mockCreateObjectURL.mockImplementation(
      () => `blob:mock-url-${++urlCounter}`,
    );
    mockRevokeObjectURL.mockImplementation(() => {});

    global.URL.createObjectURL = mockCreateObjectURL;
    global.URL.revokeObjectURL = mockRevokeObjectURL;
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it('should return an empty Map when files is null', () => {
    const { result } = renderHook(() => useFileUrls(null));

    expect(result.current).toEqual(new Map());
  });

  it('should create URLs for files', () => {
    const file = createFile('test.txt');
    const fileList = createFileList([file]);

    const { result } = renderHook(() => useFileUrls(fileList));

    expect(mockCreateObjectURL).toHaveBeenCalledWith(file);
    expect(result.current.size).toBe(1);
    expect(result.current.get('test.txt-100-1234567890')).toBe(
      'blob:mock-url-1',
    );
  });

  it('should create URLs for multiple files', () => {
    const file1 = createFile('file1.txt', 100, 1000);
    const file2 = createFile('file2.txt', 200, 2000);
    const fileList = createFileList([file1, file2]);

    const { result } = renderHook(() => useFileUrls(fileList));

    expect(mockCreateObjectURL).toHaveBeenCalledTimes(2);
    expect(result.current.size).toBe(2);
    expect(result.current.get('file1.txt-100-1000')).toBe('blob:mock-url-1');
    expect(result.current.get('file2.txt-200-2000')).toBe('blob:mock-url-2');
  });

  it('should reuse URLs for unchanged files', () => {
    const file = createFile('test.txt');
    const fileList1 = createFileList([file]);
    const fileList2 = createFileList([file]);

    const { result, rerender } = renderHook(({ files }) => useFileUrls(files), {
      initialProps: { files: fileList1 },
    });

    const initialUrl = result.current.get('test.txt-100-1234567890');
    expect(mockCreateObjectURL).toHaveBeenCalledTimes(1);

    rerender({ files: fileList2 });

    expect(result.current.get('test.txt-100-1234567890')).toBe(initialUrl);
    expect(mockCreateObjectURL).toHaveBeenCalledTimes(1);
  });

  it('should revoke URLs when files are removed', () => {
    const file1 = createFile('file1.txt', 100, 1000);
    const file2 = createFile('file2.txt', 200, 2000);

    const { rerender } = renderHook(({ files }) => useFileUrls(files), {
      initialProps: { files: createFileList([file1, file2]) },
    });

    rerender({ files: createFileList([file1]) });

    expect(mockRevokeObjectURL).toHaveBeenCalledWith('blob:mock-url-2');
  });

  it('should revoke all URLs when files becomes null', () => {
    const file1 = createFile('file1.txt', 100, 1000);
    const file2 = createFile('file2.txt', 200, 2000);

    const { rerender } = renderHook<
      Map<string, string>,
      { files: FileList | null }
    >(({ files }) => useFileUrls(files), {
      initialProps: { files: createFileList([file1, file2]) },
    });

    rerender({ files: null });

    expect(mockRevokeObjectURL).toHaveBeenCalledWith('blob:mock-url-1');
    expect(mockRevokeObjectURL).toHaveBeenCalledWith('blob:mock-url-2');
  });

  it('should clean up all URLs on unmount', () => {
    const file = createFile('test.txt');
    const fileList = createFileList([file]);

    const { unmount } = renderHook(() => useFileUrls(fileList));

    unmount();

    expect(mockRevokeObjectURL).toHaveBeenCalledWith('blob:mock-url-1');
  });

  it('should create new URL when adding a file', () => {
    const file1 = createFile('file1.txt', 100, 1000);
    const file2 = createFile('file2.txt', 200, 2000);

    const { result, rerender } = renderHook(({ files }) => useFileUrls(files), {
      initialProps: { files: createFileList([file1]) },
    });

    expect(result.current.size).toBe(1);

    rerender({ files: createFileList([file1, file2]) });

    expect(result.current.size).toBe(2);
    expect(mockCreateObjectURL).toHaveBeenCalledTimes(2);
  });
});
