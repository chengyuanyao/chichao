// Local-only archive. No live reports, credentials, entity positions or replay.
export const REPORT_HISTORY_KEY = 'redtide.reportHistory.v1';
export const REPORT_HISTORY_LIMIT = 20;
const MAX_BYTES = 3 * 1024 * 1024;

export function readReportHistory(storage) {
  try {
    const rows = JSON.parse(storage.getItem(REPORT_HISTORY_KEY) || '[]');
    return Array.isArray(rows) ? rows.filter(row => row && typeof row.viewerId === 'string' &&
      row.report && typeof row.report.matchId === 'string' && Array.isArray(row.report.players) &&
      row.report.players.some(p => p.id === row.viewerId)).slice(0,REPORT_HISTORY_LIMIT) : [];
  } catch (_) { return []; }
}

export function saveReportHistory(storage, report, viewerId, savedAt=Date.now()) {
  if (!report || !report.matchId || !Array.isArray(report.players) ||
      !report.players.some(p => p.id === viewerId)) return false;
  const latest = {viewerId,savedAt,report};
  const rows = [latest,...readReportHistory(storage).filter(row => row.report.matchId !== report.matchId)]
    .slice(0,REPORT_HISTORY_LIMIT);
  while (rows.length) {
    const text = JSON.stringify(rows);
    if (text.length * 2 <= MAX_BYTES) {
      try { storage.setItem(REPORT_HISTORY_KEY,text); return true; } catch (_) { /* Quota/private mode. */ }
    }
    rows.pop();
  }
  return false; // Preserve the previous archive if even the newest report won't fit.
}
