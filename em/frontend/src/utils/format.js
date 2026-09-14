/**
 * Display formatters.
 *
 * The fleet contains machines whose source records never stated an odometer
 * reading or a manufacturer. Those are rendered as explicitly unrecorded rather
 * than as a zero, which would read as a real measurement.
 */

/** Operating hours, or an explicit unknown when the source never recorded them. */
export const formatHours = (hours) => {
  const value = Number(hours);
  return Number.isFinite(value) && value > 0 ? value.toLocaleString() : 'Not recorded';
};

/** Any field that a source may legitimately not have supplied. */
export const orNotRecorded = (value) =>
  value === null || value === undefined || value === '' ? 'Not recorded' : value;
