const base = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
let token;

async function request(path, { method = 'GET', body } = {}) {
  const response = await fetch(`${base}/api/v1${path}`, {
    method,
    headers: {
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof data?.detail === 'string' ? data.detail : `So'rov bajarilmadi (${response.status}).`);
  }
  return data;
}

export async function authenticate(initData) {
  if (!initData) throw new Error('Testni Telegram botidagi tugma orqali oching.');
  const data = await request('/bot/auth/', { method: 'POST', body: { init_data: initData } });
  token = data.access_token;
  return data.user_id;
}

export const startQuiz = (quizId, durationMinutes) =>
  request(`/student/sessions/${quizId}/start-single-player/?duration_minute=${durationMinutes}`, { method: 'POST' });
export const getInfo = (id) => request(`/student/sessions/multiplayer/${id}/info/`);
export const getQuestions = (id) => request(`/student/sessions/multiplayer/${id}/questions/`);
export const submitAnswer = (id, answer) =>
  request(`/student/sessions/multiplayer/${id}/answer`, { method: 'POST', body: answer });
export const finishQuiz = (id, answers) =>
  request(`/student/sessions/${id}/finish-single-player/`, { method: 'POST', body: answers });
export const handoffSinglePlayerResult = (id) =>
  request(`/bot/single-player/${id}/result/`, { method: 'POST' });
export const getRoomState = (id) => request(`/bot/rooms/${id}/state/`);
export const getRoomQuestions = (id) => request(`/bot/rooms/${id}/questions/`);
export const submitRoomAnswer = (id, answer) =>
  request(`/bot/rooms/${id}/answer/`, { method: 'POST', body: answer });
export const finishRoomQuiz = (id) =>
  request(`/bot/rooms/${id}/finish/`, { method: 'POST' });

export function mediaUrl(value) {
  try {
    const url = new URL(value, base || window.location.origin);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
  } catch {
    return '';
  }
}
