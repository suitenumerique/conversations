import * as Sentry from '@sentry/nextjs';

/**
 * TEMPORARY diagnostic for the "Maximum update depth exceeded" errors seen in
 * production.
 *
 * `trackRender` is called from the always-mounted components. React aborts a
 * runaway update cycle at 50 nested updates, so a component crossing
 * WARN_THRESHOLD renders inside WINDOW_MS is already looping: we attach that to
 * the Sentry scope, so the React error that follows a few milliseconds later
 * carries the name of the component that caused it.
 *
 * The console stays silent unless `localStorage['debug-render-loop']` is set:
 * streaming legitimately re-renders ~20x/s, and the diff payload holds message
 * content, which has no business in an end user's console. Only counts and
 * changed key *names* ever reach Sentry.
 *
 *   localStorage['debug-render-loop'] = 'on'       // loop reports
 *   localStorage['debug-render-loop'] = 'verbose'  // plus every single render
 *
 * Remove this module and its call sites once the loop is fixed.
 */

const WINDOW_MS = 1000;
const WARN_THRESHOLD = 25;

// Once a component passes this many renders in the window it is misbehaving,
// so start reporting which of its values changed identity between renders.
const DIFF_THRESHOLD = 5;
const DIFF_LOGS_PER_WINDOW = 12;

interface RenderCounter {
  count: number;
  windowStart: number;
  warned: boolean;
  diffLogs: number;
  lastContext?: Record<string, unknown>;
  previousValues?: Record<string, unknown>;
  lastChangedKeys?: string[];
}

const counters = new Map<string, RenderCounter>();

/**
 * Keys whose identity differs from the previous render. An empty list means the
 * re-render came from a parent, a context, or a store - not from this
 * component's own values.
 */
const changedKeys = (
  previous: Record<string, unknown>,
  current: Record<string, unknown>,
) =>
  Object.keys(current).filter((key) => !Object.is(previous[key], current[key]));

const debugLevel = () => {
  try {
    return localStorage.getItem('debug-render-loop');
  } catch {
    // localStorage unavailable (privacy mode, sandboxed iframe) - stay quiet.
    return null;
  }
};

/** Console output is opt-in; Sentry reporting is not gated by this. */
const isConsoleEnabled = () => debugLevel() !== null;
const isVerbose = () => debugLevel() === 'verbose';

/**
 * Components still inside their current window, busiest first. Carries only
 * counts and changed key *names* - never the values, which hold message
 * content and would otherwise reach Sentry.
 */
const snapshot = () => {
  const now = Date.now();
  return Array.from(counters.entries())
    .filter(([, counter]) => now - counter.windowStart <= WINDOW_MS)
    .sort(([, a], [, b]) => b.count - a.count)
    .map(([name, counter]) => ({
      component: name,
      renders: counter.count,
      elapsedMs: now - counter.windowStart,
      changedKeys: counter.lastChangedKeys ?? [],
    }));
};

/**
 * Count one render of `name`. Pass every hook output the component depends on
 * as `context`: once the render rate goes abnormal, the keys whose identity
 * changed between renders are logged, which is what names the culprit.
 */
export const trackRender = (
  name: string,
  context?: Record<string, unknown>,
) => {
  const now = Date.now();
  let counter = counters.get(name);

  if (!counter || now - counter.windowStart > WINDOW_MS) {
    counter = { count: 0, windowStart: now, warned: false, diffLogs: 0 };
    counters.set(name, counter);
  }

  counter.count += 1;
  const previousValues = counter.previousValues;
  counter.previousValues = context;
  counter.lastContext = context;

  if (isVerbose()) {
    console.log(`[render-loop] ${name} #${counter.count}`, context ?? '');
  }

  // Computed even when the console is silent: the key names ride along to
  // Sentry, and they are what identifies the culprit there.
  if (context && previousValues && counter.count >= DIFF_THRESHOLD) {
    const changed = changedKeys(previousValues, context);
    counter.lastChangedKeys = changed;

    if (isConsoleEnabled() && counter.diffLogs < DIFF_LOGS_PER_WINDOW) {
      counter.diffLogs += 1;
      console.log(
        `[render-loop] ${name} #${counter.count} changed: ${changed.join(', ') || '(nothing of its own)'}`,
        changed.reduce<Record<string, unknown>>((acc, key) => {
          acc[key] = { from: previousValues[key], to: context[key] };
          return acc;
        }, {}),
      );
    }
  }

  if (counter.count < WARN_THRESHOLD || counter.warned) {
    return;
  }
  counter.warned = true;

  const renders = counter.count;
  const elapsedMs = now - counter.windowStart;

  // Values stay in the developer's own console; only names travel to Sentry.
  if (isConsoleEnabled()) {
    console.warn(
      `[render-loop] ${name} rendered ${renders} times in ${elapsedMs}ms`,
      { component: name, renders, elapsedMs, context, busiest: snapshot() },
    );
  }

  // Attached to the scope rather than captured as its own event: the React
  // error arrives moments later and we want it to carry this payload.
  const report = { component: name, renders, elapsedMs, busiest: snapshot() };
  Sentry.setContext('render_loop', report);
  Sentry.addBreadcrumb({
    category: 'render-loop',
    level: 'warning',
    message: `${name} rendered ${renders}x in ${elapsedMs}ms`,
    data: report,
  });
};

const SAMPLES_PER_WINDOW = 8;
const sampleBudgets = new Map<string, { windowStart: number; logs: number }>();

/** Rate-limited, opt-in log for call sites that fire on every render. */
export const debugSample = (
  label: string,
  payload: Record<string, unknown>,
) => {
  if (!isConsoleEnabled()) {
    return;
  }

  const now = Date.now();
  let budget = sampleBudgets.get(label);

  if (!budget || now - budget.windowStart > WINDOW_MS) {
    budget = { windowStart: now, logs: 0 };
    sampleBudgets.set(label, budget);
  }

  if (budget.logs >= SAMPLES_PER_WINDOW) {
    return;
  }
  budget.logs += 1;
  console.log(`[render-loop] ${label}`, payload);
};

const REACT_LOOP_MESSAGES = [
  'Maximum update depth exceeded',
  'while rendering a different component',
  // Production React reports errors by code: #185 is the update-depth limit.
  'Minified React error #185',
];

const isReactLoopMessage = (message: string) =>
  REACT_LOOP_MESSAGES.some((needle) => message.includes(needle));

let installed = false;

/**
 * Record the render tally whenever React reports a runaway update, so the
 * Sentry event names the component that was spinning even though the throw
 * itself comes from inside react-dom and never mentions it.
 */
export const installRenderLoopCapture = () => {
  if (installed || typeof window === 'undefined') {
    return;
  }
  installed = true;

  const report = (source: string, message: string) => {
    const busiest = snapshot();
    Sentry.setContext('render_loop_error', { source, message, busiest });
    if (isConsoleEnabled()) {
      console.warn(
        `[render-loop] React reported "${message}" via ${source}. Busiest components:`,
        busiest,
      );
    }
  };

  // React throws the update-depth error rather than logging it, so this is the
  // hook that fires in a production build.
  window.addEventListener('error', (event) => {
    const message =
      event.message ||
      (event.error instanceof Error ? event.error.message : '');
    if (isReactLoopMessage(message)) {
      report('window.onerror', message);
    }
  });

  // Development builds log the companion warnings instead of throwing. Patching
  // console.error is intrusive, so only do it when debugging is switched on.
  if (!isConsoleEnabled()) {
    return;
  }

  const originalError = console.error;
  console.error = (...args: unknown[]) => {
    const message = args.filter((arg) => typeof arg === 'string').join(' ');
    if (isReactLoopMessage(message)) {
      report('console.error', message);
    }
    originalError(...args);
  };
};
