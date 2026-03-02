import { DateTime, Settings } from 'luxon';

import { getRelativeTime } from '../date';

describe('getRelativeTime', () => {
  const originalNow = Settings.now;

  beforeAll(() => {
    Settings.now = () => new Date(2026, 2, 2, 12, 0, 0).getTime();
  });

  afterAll(() => {
    Settings.now = originalNow;
  });

  it('returns null for undefined', () => {
    expect(getRelativeTime(undefined, 'en')).toBeNull();
  });

  it('returns null for null', () => {
    expect(getRelativeTime(null, 'en')).toBeNull();
  });

  it('returns null for empty string', () => {
    expect(getRelativeTime('', 'en')).toBeNull();
  });

  it('returns null for invalid ISO date', () => {
    expect(getRelativeTime('not-a-date', 'en')).toBeNull();
  });

  it('returns a relative string for a valid date', () => {
    const twoHoursAgo = DateTime.now().minus({ hours: 2 }).toISO();
    expect(getRelativeTime(twoHoursAgo, 'en')).toBe('2 hours ago');
  });

  it('respects the locale parameter', () => {
    const twoHoursAgo = DateTime.now().minus({ hours: 2 }).toISO();
    expect(getRelativeTime(twoHoursAgo, 'fr')).toBe('il y a 2 heures');
  });

  it('handles dates in the future', () => {
    const inThreeDays = DateTime.now().plus({ days: 3 }).toISO();
    expect(getRelativeTime(inThreeDays, 'en')).toBe('in 3 days');
  });
});
