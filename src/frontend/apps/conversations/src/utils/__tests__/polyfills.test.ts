const nativeHasOwn = Object.hasOwn;
const nativeFindLastIndex = Array.prototype.findLastIndex;

// The module installs the polyfills as a side effect: it has to be loaded after
// the native method is removed, hence the dynamic import.
const loadPolyfills = async () => {
  vi.resetModules();
  await import('../polyfills');
};

describe('polyfills', () => {
  afterEach(() => {
    // Restored as the engine defines them: plain assignment after a delete
    // would add an enumerable property, showing up in for...in loops.
    Object.defineProperty(Object, 'hasOwn', {
      value: nativeHasOwn,
      configurable: true,
      writable: true,
    });
    Object.defineProperty(Array.prototype, 'findLastIndex', {
      value: nativeFindLastIndex,
      configurable: true,
      writable: true,
    });
  });

  it('adds Object.hasOwn to browsers that lack it', async () => {
    // Simulating Chrome before 93 / Firefox before 92.
    Reflect.deleteProperty(Object, 'hasOwn');

    await loadPolyfills();

    const inherited = Object.create({ inheritedKey: 1 }) as object;
    expect(Object.hasOwn({ ownKey: 1 }, 'ownKey')).toBe(true);
    expect(Object.hasOwn(inherited, 'inheritedKey')).toBe(false);
  });

  it('adds Array.prototype.findLastIndex to browsers that lack it', async () => {
    // Simulating Chrome before 97 / Firefox before 104.
    Reflect.deleteProperty(Array.prototype, 'findLastIndex');

    await loadPolyfills();

    const roles = ['user', 'assistant', 'user', 'assistant'];
    expect(roles.findLastIndex((role) => role === 'user')).toBe(2);
    expect(roles.findLastIndex((role) => role === 'system')).toBe(-1);
    expect(
      roles.findLastIndex((_, index, array) => array.length - 1 === index),
    ).toBe(3);
  });
});
