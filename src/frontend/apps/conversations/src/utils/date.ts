import { DateTime } from 'luxon';

export const getRelativeTime = (
  isoDate: string | undefined | null,
  locale: string,
): string | null => {
  if (!isoDate) {
    return null;
  }
  const dt = DateTime.fromISO(isoDate);
  if (!dt.isValid) {
    return null;
  }
  return dt.toRelative({ locale }) ?? null;
};
