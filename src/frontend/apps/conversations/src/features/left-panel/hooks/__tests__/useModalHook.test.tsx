import { act, renderHook } from '@testing-library/react';

import { useOwnModal } from '../useModalHook';

describe('useOwnModal', () => {
  it('should initialize with isOpen as false by default', () => {
    const { result } = renderHook(() => useOwnModal());

    expect(result.current.isOpen).toBe(false);
  });

  it('should initialize with isOpen as true when initialState is true', () => {
    const { result } = renderHook(() => useOwnModal(true));

    expect(result.current.isOpen).toBe(true);
  });

  it('should set isOpen to true when open is called', () => {
    const { result } = renderHook(() => useOwnModal());

    act(() => {
      result.current.open();
    });

    expect(result.current.isOpen).toBe(true);
  });

  it('should set isOpen to false when close is called', () => {
    const { result } = renderHook(() => useOwnModal(true));

    act(() => {
      result.current.close();
    });

    expect(result.current.isOpen).toBe(false);
  });

  it('should maintain stable callback references across rerenders', () => {
    const { result, rerender } = renderHook(() => useOwnModal());

    const initialOpen = result.current.open;
    const initialClose = result.current.close;

    rerender();

    expect(result.current.open).toBe(initialOpen);
    expect(result.current.close).toBe(initialClose);
  });

  it('should handle multiple open/close cycles', () => {
    const { result } = renderHook(() => useOwnModal());

    expect(result.current.isOpen).toBe(false);

    act(() => {
      result.current.open();
    });
    expect(result.current.isOpen).toBe(true);

    act(() => {
      result.current.close();
    });
    expect(result.current.isOpen).toBe(false);

    act(() => {
      result.current.open();
    });
    expect(result.current.isOpen).toBe(true);
  });
});
