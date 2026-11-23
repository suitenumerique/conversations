// Imported first in main.tsx, before any dependency runs.

// Object.hasOwn: Chrome 93, Firefox 92, Safari 15.4. Older browsers are still
// found on locked-down workstations, and react-markdown, the HTML sanitizer and
// lottie-react call it.
if (typeof Object.hasOwn !== 'function') {
  Object.defineProperty(Object, 'hasOwn', {
    value: (object: object, key: PropertyKey) =>
      Object.prototype.hasOwnProperty.call(object, key),
    configurable: true,
    writable: true,
  });
}

// Array.prototype.findLastIndex: Chrome 97, Firefox 104, Safari 15.4.
if (typeof Array.prototype.findLastIndex !== 'function') {
  Object.defineProperty(Array.prototype, 'findLastIndex', {
    value: function <T>(
      this: T[],
      predicate: (value: T, index: number, array: T[]) => unknown,
      thisArg?: unknown,
    ) {
      for (let index = this.length - 1; index >= 0; index--) {
        if (predicate.call(thisArg, this[index], index, this)) {
          return index;
        }
      }
      return -1;
    },
    configurable: true,
    writable: true,
  });
}

// A module, not a script, so that it can be imported for its side effect.
export {};
