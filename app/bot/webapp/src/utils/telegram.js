export function initTelegram() {
  const app = window.Telegram?.WebApp;
  app?.ready();
  app?.expand();
  return app?.initData || '';
}

export function closeTelegram() {
  window.Telegram?.WebApp?.close?.();
}

export function getQuizId() {
  const value = new URLSearchParams(window.location.search).get('quiz_id');
  if (!value || !/^\d+$/.test(value) || !Number.isSafeInteger(Number(value)) || Number(value) < 1) {
    throw new Error('Test havolasi yaroqsiz. Botdan testni qayta oching.');
  }
  return Number(value);
}

export function getQuizDuration() {
  const value = new URLSearchParams(window.location.search).get('duration_minutes');
  if (!value) return 10;
  if (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value)) || Number(value) < 1) {
    throw new Error('Test vaqti yaroqsiz. Botdan testni qayta oching.');
  }
  return Number(value);
}

export function getRoomSession() {
  const value = new URLSearchParams(window.location.search).get('room_session');
  if (!value) return null;
  if (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value)) || Number(value) < 1) {
    throw new Error('Xona havolasi yaroqsiz. Botdan testni qayta oching.');
  }
  return Number(value);
}
