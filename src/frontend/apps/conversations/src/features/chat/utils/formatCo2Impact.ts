/**
 * Formats a CO₂ impact value (kg CO₂eq) for display in the UI.
 */
export const formatCo2Impact = (kgCo2eq: number): string => {
  if (kgCo2eq >= 1) {
    return `${kgCo2eq.toLocaleString(undefined, {
      maximumFractionDigits: 2,
    })} kg CO₂eq`;
  }

  if (kgCo2eq >= 0.001) {
    return `${(kgCo2eq * 1000).toLocaleString(undefined, {
      maximumFractionDigits: 2,
    })} g CO₂eq`;
  }

  return `${(kgCo2eq * 1_000_000).toLocaleString(undefined, {
    maximumFractionDigits: 2,
  })} mg CO₂eq`;
};
