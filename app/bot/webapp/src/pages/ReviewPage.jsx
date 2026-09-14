import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, Grid3X3, Moon, Search, Sun, Zap } from 'lucide-react';
import AnswerOptions from '../components/AnswerOptions';
import Question from '../components/Question';
import { authenticate, getQuizReview, setCorrectOption } from '../api/quiz';
import { closeTelegram, getQuizId, getTelegramTheme, initTelegram } from '../utils/telegram';

const correctLabelOf = (question) => (question.options || []).find((option) => option.is_correct)?.label;

export default function ReviewPage() {
  const [state, setState] = useState({ status: 'loading', error: '', quiz: null, questions: [] });
  const [current, setCurrent] = useState(0);
  const [saving, setSaving] = useState(false);
  const [showNavigator, setShowNavigator] = useState(false);
  const [theme, setTheme] = useState(getTelegramTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const loadReview = useCallback(async () => {
    setState({ status: 'loading', error: '', quiz: null, questions: [] });
    try {
      const initData = initTelegram();
      const quizId = getQuizId();
      await authenticate(initData);
      const quiz = await getQuizReview(quizId);
      setState({ status: 'ready', error: '', quiz, questions: quiz.questions || [] });
      setCurrent(0);
    } catch (error) {
      setState({
        status: 'error',
        error: error.message || 'Savollarni yuklab bo‘lmadi.',
        quiz: null,
        questions: [],
      });
    }
  }, []);

  useEffect(() => {
    loadReview();
  }, [loadReview]);

  const question = state.questions[current];
  const total = state.questions.length;
  const missing = useMemo(
    () => state.questions.reduce((indexes, item, index) => (
      correctLabelOf(item) ? indexes : [...indexes, index]
    ), []),
    [state.questions],
  );

  const goToNextProblem = () => {
    const next = missing.find((index) => index > current) ?? missing[0];
    if (next !== undefined) {
      setCurrent(next);
      setShowNavigator(false);
    }
  };

  const finishReview = () => setState((value) => ({ ...value, status: 'done' }));

  const chooseCorrect = async (label) => {
    if (!question || saving) return;
    const option = (question.options || []).find((item) => item.label === label);
    if (!option || option.is_correct) return;

    const previousQuestions = state.questions;
    setState((value) => ({
      ...value,
      error: '',
      questions: value.questions.map((item) => (item.id === question.id
        ? { ...item, options: item.options.map((entry) => ({ ...entry, is_correct: entry.id === option.id })) }
        : item)),
    }));
    setSaving(true);
    try {
      await setCorrectOption(question.id, option.id);
    } catch (error) {
      setState((value) => ({
        ...value,
        questions: previousQuestions,
        error: error.message || 'To‘g‘ri javobni saqlab bo‘lmadi.',
      }));
    } finally {
      setSaving(false);
    }
  };

  if (state.status === 'loading') {
    return <main className="app-shell"><p className="loading">Savollar yuklanmoqda...</p></main>;
  }
  if (state.status === 'error') {
    return <main className="app-shell"><section className="card error">
      <h1>Xatolik</h1>
      <p>{state.error}</p>
      <button type="button" onClick={loadReview}>Qayta urinish</button>
    </section></main>;
  }
  if (state.status === 'done') {
    return <main className="app-shell"><section className="card result">
      <CheckCircle2 className="result-icon" size={44} aria-hidden="true" />
      <h1>Savollar tekshirildi</h1>
      <p>{missing.length
        ? `O‘zgarishlar saqlandi. ${missing.length} ta savolda to‘g‘ri javob hali belgilanmagan.`
        : 'O‘zgarishlar saqlandi. Endi testni Telegramdagi tugmalar orqali boshlashingiz mumkin.'}</p>
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
      </div>
    </header>

    <main className="app-shell">
      <section className="status-panel" aria-label="Tekshiruv holati">
        <span className="status-icon" aria-hidden="true"><Search size={20} /></span>
        <div className="progress-copy">
          <div className="progress-heading">
            <strong>Savol {current + 1}/{total}</strong>
            {missing.length > 0 && <button
              className="answer-count warning"
              type="button"
              onClick={goToNextProblem}
              title="To‘g‘ri javobi belgilanmagan savolga o‘tish"
            >
              <AlertTriangle size={12} aria-hidden="true" />&nbsp;{missing.length}
            </button>}
          </div>
          <div className="progress-line">
            <progress value={current + 1} max={total || 1} aria-label="Tekshirilgan savollar" />
            <span>{total ? Math.round(((current + 1) / total) * 100) : 0}%</span>
          </div>
        </div>
        <button className="icon-button" type="button" onClick={() => setShowNavigator(value => !value)} title="Savollar ro‘yxati" aria-label="Savollar ro‘yxati">
          <Grid3X3 size={19} />
        </button>
        <button className="icon-button icon-button-primary" type="button" onClick={finishReview} title="Tekshiruvni yakunlash" aria-label="Tekshiruvni yakunlash">
          <CheckCircle2 size={18} />
        </button>
      </section>

      {showNavigator && <nav className="question-navigator" aria-label="Savolni tanlash">
        {state.questions.map((item, index) => <button
          type="button"
          key={item.id}
          className={`${index === current ? 'active' : ''} ${correctLabelOf(item) ? 'answered' : 'missing'}`}
          onClick={() => { setCurrent(index); setShowNavigator(false); }}
        >{index + 1}</button>)}
      </nav>}

      {state.error && <p className="inline-error" role="alert">{state.error}</p>}
      {question ? <article className="question-card">
        <div className="question-tags">
          <span className="tag tag-subject">{question.subject || state.quiz?.subject || 'Umumiy'}</span>
          {question.topic && <span className="tag tag-topic">{question.topic}</span>}
          {question.difficulty && <span className="tag tag-level">{question.difficulty}</span>}
        </div>
        <Question question={question} />
        <p className={`review-hint ${correctLabelOf(question) ? '' : 'warning'}`}>
          {correctLabelOf(question)
            ? 'To‘g‘ri javob noto‘g‘ri bo‘lsa, to‘g‘ri variantni belgilang.'
            : '⚠️ Bu savolda to‘g‘ri javob belgilanmagan. To‘g‘ri variantni tanlang.'}
        </p>
        <AnswerOptions
          options={question.options || []}
          selected={correctLabelOf(question)}
          onSelect={chooseCorrect}
          disabled={saving}
        />
        <nav className="navigation" aria-label="Savollar boshqaruvi">
          <button className="nav-button" type="button" onClick={() => setCurrent((value) => value - 1)} disabled={current === 0}>
            <ChevronLeft size={18} /> <span>Oldingi</span>
          </button>
          {current < total - 1
            ? <button className="nav-button primary" type="button" onClick={() => setCurrent((value) => value + 1)}><span>Keyingi</span> <ChevronRight size={18} /></button>
            : <button className="nav-button primary" type="button" onClick={finishReview}><span>Tayyor</span> <ChevronRight size={18} /></button>}
        </nav>
      </article> : <section className="question-card empty-state"><h1>Savollar topilmadi</h1></section>}
    </main>
  </div>;
}
