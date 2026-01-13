import { act, renderHook } from '@testing-library/react';

import { useFileDragDrop } from '../useFileDragDrop';

const createFile = (name: string, type: string): File => {
  return new File(['content'], name, { type });
};

const createDragEvent = (
  type: string,
  files?: File[],
  relatedTarget?: EventTarget | null,
): DragEvent => {
  const event = new Event(type, { bubbles: true }) as DragEvent;

  const dataTransfer = {
    types: files ? ['Files'] : [],
    files: files
      ? {
          length: files.length,
          item: (i: number) => files[i],
          [Symbol.iterator]: function* () {
            for (const file of files) {
              yield file;
            }
          },
        }
      : { length: 0 },
  } as unknown as DataTransfer;

  Object.defineProperty(event, 'dataTransfer', { value: dataTransfer });
  Object.defineProperty(event, 'relatedTarget', { value: relatedTarget });
  Object.defineProperty(event, 'preventDefault', { value: jest.fn() });

  return event;
};

describe('useFileDragDrop', () => {
  const defaultProps = {
    enabled: true,
    isFileAccepted: jest.fn(() => true),
    onFilesAccepted: jest.fn(),
    onFilesRejected: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should initialize with isDragActive as false', () => {
    const { result } = renderHook(() => useFileDragDrop(defaultProps));

    expect(result.current.isDragActive).toBe(false);
  });

  it('should set isDragActive to true on dragenter with files', () => {
    const { result } = renderHook(() => useFileDragDrop(defaultProps));

    act(() => {
      window.dispatchEvent(
        createDragEvent('dragenter', [createFile('test.txt', 'text/plain')]),
      );
    });

    expect(result.current.isDragActive).toBe(true);
  });

  it('should not set isDragActive on dragenter without files', () => {
    const { result } = renderHook(() => useFileDragDrop(defaultProps));

    act(() => {
      window.dispatchEvent(createDragEvent('dragenter'));
    });

    expect(result.current.isDragActive).toBe(false);
  });

  it('should set isDragActive to false on dragleave when leaving window', () => {
    const { result } = renderHook(() => useFileDragDrop(defaultProps));

    act(() => {
      window.dispatchEvent(
        createDragEvent('dragenter', [createFile('test.txt', 'text/plain')]),
      );
    });
    expect(result.current.isDragActive).toBe(true);

    act(() => {
      window.dispatchEvent(createDragEvent('dragleave', [], null));
    });

    expect(result.current.isDragActive).toBe(false);
  });

  it('should not set isDragActive to false on dragleave when moving between elements', () => {
    const { result } = renderHook(() => useFileDragDrop(defaultProps));

    act(() => {
      window.dispatchEvent(
        createDragEvent('dragenter', [createFile('test.txt', 'text/plain')]),
      );
    });
    expect(result.current.isDragActive).toBe(true);

    act(() => {
      window.dispatchEvent(createDragEvent('dragleave', [], document.body));
    });

    expect(result.current.isDragActive).toBe(true);
  });

  it('should set isDragActive to false on drop', () => {
    const { result } = renderHook(() => useFileDragDrop(defaultProps));

    act(() => {
      window.dispatchEvent(
        createDragEvent('dragenter', [createFile('test.txt', 'text/plain')]),
      );
    });
    expect(result.current.isDragActive).toBe(true);

    act(() => {
      window.dispatchEvent(
        createDragEvent('drop', [createFile('test.txt', 'text/plain')]),
      );
    });

    expect(result.current.isDragActive).toBe(false);
  });

  it('should call onFilesAccepted with accepted files on drop', () => {
    const onFilesAccepted = jest.fn();
    const file = createFile('test.txt', 'text/plain');

    renderHook(() =>
      useFileDragDrop({
        ...defaultProps,
        onFilesAccepted,
      }),
    );

    act(() => {
      window.dispatchEvent(createDragEvent('drop', [file]));
    });

    expect(onFilesAccepted).toHaveBeenCalledWith([file]);
  });

  it('should call onFilesRejected with rejected file names', () => {
    const onFilesRejected = jest.fn();
    const isFileAccepted = jest.fn(() => false);

    renderHook(() =>
      useFileDragDrop({
        ...defaultProps,
        isFileAccepted,
        onFilesRejected,
      }),
    );

    act(() => {
      window.dispatchEvent(
        createDragEvent('drop', [createFile('test.exe', 'application/exe')]),
      );
    });

    expect(onFilesRejected).toHaveBeenCalledWith(['test.exe']);
  });

  it('should separate accepted and rejected files', () => {
    const onFilesAccepted = jest.fn();
    const onFilesRejected = jest.fn();
    const isFileAccepted = jest.fn((file: File) => file.type === 'text/plain');

    const acceptedFile = createFile('good.txt', 'text/plain');
    const rejectedFile = createFile('bad.exe', 'application/exe');

    renderHook(() =>
      useFileDragDrop({
        ...defaultProps,
        isFileAccepted,
        onFilesAccepted,
        onFilesRejected,
      }),
    );

    act(() => {
      window.dispatchEvent(
        createDragEvent('drop', [acceptedFile, rejectedFile]),
      );
    });

    expect(onFilesAccepted).toHaveBeenCalledWith([acceptedFile]);
    expect(onFilesRejected).toHaveBeenCalledWith(['bad.exe']);
  });

  it('should ignore drag events when disabled', () => {
    const { result } = renderHook(() =>
      useFileDragDrop({
        ...defaultProps,
        enabled: false,
      }),
    );

    act(() => {
      window.dispatchEvent(
        createDragEvent('dragenter', [createFile('test.txt', 'text/plain')]),
      );
    });

    expect(result.current.isDragActive).toBe(false);
  });

  it('should reset isDragActive when disabled changes to false', () => {
    const { result, rerender } = renderHook(
      ({ enabled }) => useFileDragDrop({ ...defaultProps, enabled }),
      { initialProps: { enabled: true } },
    );

    act(() => {
      window.dispatchEvent(
        createDragEvent('dragenter', [createFile('test.txt', 'text/plain')]),
      );
    });
    expect(result.current.isDragActive).toBe(true);

    rerender({ enabled: false });

    expect(result.current.isDragActive).toBe(false);
  });

  it('should clean up event listeners on unmount', () => {
    const removeEventListenerSpy = jest.spyOn(window, 'removeEventListener');

    const { unmount } = renderHook(() => useFileDragDrop(defaultProps));
    unmount();

    expect(removeEventListenerSpy).toHaveBeenCalledWith(
      'dragenter',
      expect.any(Function),
    );
    expect(removeEventListenerSpy).toHaveBeenCalledWith(
      'dragleave',
      expect.any(Function),
    );
    expect(removeEventListenerSpy).toHaveBeenCalledWith(
      'dragover',
      expect.any(Function),
    );
    expect(removeEventListenerSpy).toHaveBeenCalledWith(
      'drop',
      expect.any(Function),
    );

    removeEventListenerSpy.mockRestore();
  });
});
