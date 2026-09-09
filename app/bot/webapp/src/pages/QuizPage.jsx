import { useCallback, useEffect, useMemo, useState } from 'react';
import { Bell, CheckCircle2, ChevronLeft, ChevronRight, Moon, Sun, Zap } from 'lucide-react';
import AnswerOptions from '../components/AnswerOptions';
import Question from '../components/Question';
import QuizProgress from '../components/QuizProgress';
import QuizTimer from '../components/QuizTimer';
import {
  authenticate,
  finishQuiz,
  finishRoomQuiz,
  getInfo,
  getQuestions,
  getRoomQuestions,
  getRoomState,
  handoffSinglePlayerResult,
  startQuiz,
  submitAnswer,
  submitRoomAnswer,
} from '../api/quiz';
import { closeTelegram, getQuizDuration, getQuizId, getRoomSession, initTelegram } from '../utils/telegram';

const sessionKey = (quizId, durationMinutes) => `telegram-quiz-session:${quizId}:${durationMinutes}`;
const roomCompletionKey = (sessionId, userId) => `telegram-room-completed:${userId}:${sessionId}`;
const isCompletedSessionError = (error) => (
  /session[_ ]already[_ ]finished|session is not running|quiz deadline has passed/i
    .test(error?.message || '')
);

const completedState = (info, isRoom = false) => ({
  status: 'finished',
  error: '',
  info: info ? { ...info, isRoom } : null,
  questions: [],
  title: 'Siz testni ishlab bo‘lgansiz',
  message: isRoom
    ? 'Javoblaringiz qabul qilingan. Natijalarni Telegramdagi xona xabarida ko‘rishingiz mumkin.'
    : 'Javoblaringiz qabul qilingan. Natijani Telegram botdagi “📊 Natijalar” bo‘limida ko‘rishingiz mumkin.',
});

export default function QuizPage() {
  const [state, setState] = useState({ status: 'loading', error: '', info: null, questions: [] });
  const [current, setCurrent] = useState(0);
  const [answers, setAnswers] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [showNavigator, setShowNavigator] = useState(false);
  const [theme, setTheme] = useState('dark');

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const loadQuiz = useCallback(async () => {
    let authenticatedUserId = null;
    try {
      const initData = initTelegram();
      const quizId = getQuizId();
      const roomSessionId = getRoomSession();
      const durationMinutes = getQuizDuration();
      authenticatedUserId = await authenticate(initData);

      if (roomSessionId) {
        if (window.localStorage.getItem(roomCompletionKey(roomSessionId, authenticatedUserId)) === '1') {
          setState(completedState({ session_id: roomSessionId, userId: authenticatedUserId }, true));
          return;
        }
        const info = await getRoomState(roomSessionId);
        const savedAnswers = info.answers || {};
        setAnswers(savedAnswers);
        if (info.status === 'finished') {
          window.localStorage.setItem(roomCompletionKey(roomSessionId, authenticatedUserId), '1');
          setState(completedState({ ...info, userId: authenticatedUserId }, true));
          return;
        }
        if (info.status !== 'running') {
          throw new Error('Xona egasi testni hali boshlamagan.');
        }
        const questionsResponse = await getRoomQuestions(roomSessionId);
        if (questionsResponse.status === 'finished') {
          const finishedInfo = await getRoomState(roomSessionId);
          window.localStorage.setItem(roomCompletionKey(roomSessionId, authenticatedUserId), '1');
          setState(completedState({ ...finishedInfo, userId: authenticatedUserId }, true));
          return;
        }
        setState({
          status: 'ready',
          error: '',
          info: { ...info, isRoom: true, userId: authenticatedUserId },
          questions: questionsResponse.questions || [],
        });
        const firstUnanswered = (questionsResponse.questions || [])
          .findIndex((question) => !savedAnswers[question.id]);
        setCurrent(firstUnanswered >= 0 ? firstUnanswered : 0);
        return;
      }

      let sessionId = Number(window.localStorage.getItem(sessionKey(quizId, durationMinutes)));
      let info;
      if (Number.isSafeInteger(sessionId) && sessionId > 0) {
        try {
          info = await getInfo(sessionId);
          if (info.status !== 'running') sessionId = 0;
        } catch {
          sessionId = 0;
        }
      }
      if (!sessionId) {
        const started = await startQuiz(quizId, durationMinutes);
        sessionId = started.session_id;
        window.localStorage.setItem(sessionKey(quizId, durationMinutes), String(sessionId));
        info = await getInfo(sessionId);
      }

      const questionsResponse = await getQuestions(sessionId);
      setState({
        status: 'ready',
        error: '',
        info: {
          ...info,
          session_id: sessionId,
          storageKey: sessionKey(quizId, durationMinutes),
        },
        questions: questionsResponse.questions || [],
      });
    } catch (error) {
      if (isCompletedSessionError(error)) {
        const completedRoomSessionId = getRoomSession();
        if (completedRoomSessionId && authenticatedUserId) {
          window.localStorage.setItem(
            roomCompletionKey(completedRoomSessionId, authenticatedUserId),
            '1',
          );
        }
        setState(completedState(
          completedRoomSessionId
            ? { session_id: completedRoomSessionId, userId: authenticatedUserId }
            : null,
          Boolean(completedRoomSessionId),
        ));
      } else {
        setState({ status: 'error', error: error.message || 'Testni yuklab bo‘lmadi.', info: null, questions: [] });
      }
    }
  }, []);

  useEffect(() => {
    loadQuiz();
  }, [loadQuiz]);

  const question = state.questions[current];
  const selected = question ? answers[question.id] : undefined;
  const answeredCount = Object.keys(answers).length;
  const deadline = useMemo(
    () => {
      if (!state.info?.finished_at) return 0;
      const endsAt = new Date(state.info.finished_at).getTime();
      if (!state.info.server_now) return endsAt;
      const serverNow = new Date(state.info.server_now).getTime();
      return Date.now() + Math.max(0, endsAt - serverNow);
    },
    [state.info?.finished_at, state.info?.server_now],
  );

  const chooseAnswer = async (label) => {
    if (!question || !state.info || submitting) return;
    setAnswers((previous) => ({ ...previous, [question.id]: label }));
    setSubmitting(true);
    try {
      const payload = { question_id: question.id, selected_option: label };
      if (state.info.isRoom) {
        await submitRoomAnswer(state.info.session_id, payload);
      } else {
        await submitAnswer(state.info.session_id, payload);
      }
    } catch (error) {
      if (isCompletedSessionError(error)) {
        if (state.info.isRoom) {
          window.localStorage.setItem(
            roomCompletionKey(state.info.session_id, state.info.userId),
            '1',
          );
        }
        setState(completedState(state.info, Boolean(state.info.isRoom)));
      } else {
        setState((previous) => ({ ...previous, error: error.message || 'Javobni saqlab bo‘lmadi.' }));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const finish = useCallback(async () => {
    if (!state.info || state.status === 'finished' || submitting) return;
    setSubmitting(true);
    try {
      if (state.info.isRoom) {
        await finishRoomQuiz(state.info.session_id);
        window.localStorage.setItem(
          roomCompletionKey(state.info.session_id, state.info.userId),
          '1',
        );
        setState(completedState(state.info, true));
      } else {
        await finishQuiz(
          state.info.session_id,
          Object.entries(answers).map(([questionId, selectedOption]) => ({
            question_id: Number(questionId),
            selected_option: selectedOption,
          })),
        );
        try {
          await handoffSinglePlayerResult(state.info.session_id);
        } catch (error) {
          setState((previous) => ({
            ...previous,
            status: 'handoff-error',
            error: error.message || 'Natijani Telegramga yuborib bo‘lmadi.',
          }));
          return;
        }
        window.localStorage.removeItem(state.info.storageKey);
        setState((previous) => ({
          ...previous,
          status: 'finished',
          message: 'Test yakunlandi. Natijani Telegram botda ko‘ring.',
          error: '',
        }));
      }
    } catch (error) {
      if (isCompletedSessionError(error)) {
        if (state.info.isRoom) {
          window.localStorage.setItem(
            roomCompletionKey(state.info.session_id, state.info.userId),
            '1',
          );
        }
        setState(completedState(state.info, Boolean(state.info.isRoom)));
      } else {
        setState((previous) => ({ ...previous, error: error.message || 'Testni yakunlab bo‘lmadi.' }));
      }
    } finally {
      setSubmitting(false);
    }
  }, [answers, state.info, state.status, submitting]);

  const retryHandoff = useCallback(async () => {
    if (!state.info || submitting) return;
    setSubmitting(true);
    try {
      await handoffSinglePlayerResult(state.info.session_id);
      window.localStorage.removeItem(state.info.storageKey);
      setState((previous) => ({
        ...previous,
        status: 'finished',
        message: 'Test yakunlandi. Natijani Telegram botda ko‘ring.',
        error: '',
      }));
    } catch (error) {
      setState((previous) => ({
        ...previous,
        error: error.message || 'Natijani Telegramga yuborib bo‘lmadi.',
      }));
    } finally {
      setSubmitting(false);
    }
  }, [state.info, submitting]);

  if (state.status === 'loading') return <main className="app-shell"><p className="loading">Test yuklanmoqda...</p></main>;
  if (state.status === 'error') {
    return <main className="app-shell"><section className="card error"><h1>Xatolik</h1><p>{state.error}</p><button onClick={loadQuiz}>Qayta urinish</button></section></main>;
  }
  if (state.status === 'handoff-error') {
    return <main className="app-shell"><section className="card error">
      <h1>Test yakunlandi</h1>
      <p>{state.error}</p>
      <button type="button" onClick={retryHandoff} disabled={submitting}>Telegramga qayta yuborish</button>
    </section></main>;
  }
  if (state.status === 'finished') {
    return <main className="app-shell"><section className="card result">
      <CheckCircle2 className="result-icon" size={44} aria-hidden="true" />
      <h1>{state.title || 'Test yakunlandi'}</h1>
      <p>{state.message}</p>
      <button type="button" onClick={closeTelegram}>Telegramga qaytish</button>
    </section></main>;
  }

  return <div className="quiz-app">
    <header className="app-header">
      <div className="brand"><span className="brand-mark"><Zap size={17} fill="currentColor" /></span><strong>EduNova</strong></div>
      <div className="header-actions">
        <button className="icon-button theme-toggle" type="button" onClick={() => setTheme(value => value === 'dark' ? 'light' : 'dark')} title="Mavzuni almashtirish" aria-label="Mavzuni almashtirish">
          {theme === 'dark' ? <Sun size={19} /> : <Moon size={19} />}
        </button>
        <span className="notification-icon" aria-hidden="true"><Bell size={18} /><i /></span>
      </div>
    </header>

    <main className="app-shell">
      <QuizProgress
        current={current + 1}
        total={state.questions.length}
        answered={answeredCount}
        timer={deadline > 0 ? <QuizTimer deadline={deadline} onExpire={finish} /> : null}
        onToggleNavigator={() => setShowNavigator(value => !value)}
        onFinish={finish}
      />

      {showNavigator && <nav className="question-navigator" aria-label="Savolni tanlash">
        {state.questions.map((item, index) => <button
          type="button"
          key={item.id}
          className={`${index === current ? 'active' : ''} ${answers[item.id] ? 'answered' : ''}`}
          onClick={() => { setCurrent(index); setShowNavigator(false); }}
        >{index + 1}</button>)}
      </nav>}

      {state.error && <p className="inline-error" role="alert">{state.error}</p>}
      {question ? <article className="question-card">
        <div className="question-tags">
          <span className="tag tag-subject">{state.info.subject_name || 'Umumiy'}</span>
          {question.topic && <span className="tag tag-topic">{question.topic}</span>}
          {question.difficulty && <span className="tag tag-level">{question.difficulty}</span>}
        </div>
        <Question question={question} />
        <AnswerOptions options={question.options || []} selected={selected} onSelect={chooseAnswer} disabled={submitting} />
        <nav className="navigation" aria-label="Savollar boshqaruvi">
          <button className="nav-button" type="button" onClick={() => setCurrent((value) => value - 1)} disabled={current === 0}>
            <ChevronLeft size={18} /> <span>Oldingi</span>
          </button>
          {current < state.questions.length - 1
            ? <button className="nav-button primary" type="button" onClick={() => setCurrent((value) => value + 1)}><span>Keyingi</span> <ChevronRight size={18} /></button>
            : <button className="nav-button primary" type="button" onClick={finish} disabled={submitting}><span>Yakunlash</span> <ChevronRight size={18} /></button>}
        </nav>
      </article> : <section className="question-card empty-state"><h1>Savollar topilmadi</h1></section>}
    </main>
  </div>;
}
