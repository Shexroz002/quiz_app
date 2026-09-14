import { useCallback, useEffect, useMemo, useState } from 'react';
import { Check, CircleHelp, Clock3, Lightbulb, Moon, Search, Sun, TriangleAlert, X, Zap } from 'lucide-react';
import Question from '../components/Question';
import RichText from '../components/RichText';
import { authenticate, getAnalysis } from '../api/quiz';
import { getSessionId, getTelegramTheme, initTelegram } from '../utils/telegram';

const TABS = [
  { id: 'result', label: 'Natija' },
  { id: 'topics', label: 'Mavzular' },
  { id: 'questions', label: 'Savollar' },
];

const RING_RADIUS = 46;
const RING_LENGTH = 2 * Math.PI * RING_RADIUS;

const band = (percent) => (percent < 50 ? 'low' : percent < 80 ? 'mid' : 'high');
const clock = (seconds) => {
  const value = Math.max(0, Math.round(seconds || 0));
  return `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`;
};

function Ring({ percent, correct, total }) {
  return <div className="score-ring">
    <svg width="104" height="104" viewBox="0 0 104 104">
      <circle cx="52" cy="52" r={RING_RADIUS} fill="none" stroke="var(--surface)" strokeWidth="10" />
      <circle
        cx="52" cy="52" r={RING_RADIUS} fill="none" strokeWidth="10" strokeLinecap="round"
        className={`ring-${band(percent)}`}
        strokeDasharray={`${(RING_LENGTH * Math.min(100, Math.max(0, percent))) / 100} ${RING_LENGTH}`}
      />
    </svg>
    <div className="score-ring-value">
      <strong>{Math.round(percent)}<span>%</span></strong>
      <span>{correct}/{total}</span>
    </div>
  </div>;
}

function Bar({ label, correct, total, percent }) {
  return <div className="bar-row">
    <div className="bar-head">
      <span>{label}</span>
      <strong className={`band-${band(percent)}`}>{correct}/{total} · {percent}%</strong>
    </div>
    <div className="bar"><div className={`bar-fill band-bg-${band(percent)}`} style={{ width: `${percent}%` }} /></div>
  </div>;
}

function StatCard({ icon, tone, label, value, hint }) {
  return <div className="stat-card">
    <div className={`stat-head tone-${tone}`}>{icon}<span>{label}</span></div>
    <strong>{value}{hint && <span className="stat-hint"> {hint}</span>}</strong>
  </div>;
}

function ResultTab({ data }) {
  const insight = data.topics.find((row) => row.total >= 2 && row.percent < 100);
  return <>
    <section className="card score-card">
      <Ring percent={data.percentage} correct={data.correct_answers} total={data.total_questions} />
      <div className="score-copy">
        <h1>{data.quiz_title}</h1>
        <div className="question-tags no-border">
          <span className="tag tag-subject">{data.subject || 'Umumiy'}</span>
        </div>
        {data.room?.rank && <p className="muted-line">
          Xonada {data.room.rank}-o‘rin / {data.room.participants} ta
          {data.room.average_correct != null && ` · o‘rtacha ${data.room.average_correct}/${data.total_questions}`}
        </p>}
      </div>
    </section>

    <section className="stat-grid">
      <StatCard tone="ok" icon={<Check size={16} />} label="To‘g‘ri" value={data.correct_answers} />
      <StatCard tone="bad" icon={<X size={16} />} label="Xato" value={data.wrong_answers} />
      <StatCard tone="muted" icon={<CircleHelp size={16} />} label="Javobsiz" value={data.unanswered_questions} />
      <StatCard tone="accent" icon={<Clock3 size={16} />} label="Vaqt" value={clock(data.spend_time)} />
    </section>

    {data.difficulty.length > 0 && <section className="card">
      <h2>Qiyinlik kesimi</h2>
      {data.difficulty.map((row) => <Bar key={row.level} label={row.level} {...row} />)}
    </section>}

    {data.room?.top?.length > 0 && <section className="card">
      <h2>Xona reytingi</h2>
      <ol className="rank-list">
        {data.room.top.map((row, index) => <li key={index} className={row.is_me ? 'me' : ''}>
          <span className="rank-place">{index + 1}</span>
          <span className="rank-name">{row.is_me ? 'Siz' : row.display_name}</span>
          <strong>{row.correct_answers}/{row.total_questions}</strong>
        </li>)}
      </ol>
    </section>}

    {insight && <section className="insight">
      <Lightbulb size={20} aria-hidden="true" />
      <p>Eng ko‘p yo‘qotish — <strong>{insight.topic}</strong>: {insight.total} tadan {insight.total - insight.correct} tasi.</p>
    </section>}
  </>;
}

function TopicsTab({ data }) {
  const solid = data.topics.filter((row) => row.total >= 2 && row.percent === 100);
  const shaky = data.topics.filter((row) => row.total >= 2 && row.percent < 100);
  const thin = data.topics.filter((row) => row.total < 2);

  if (!data.topics.length) {
    return <section className="card empty-state"><h1>Mavzu ma’lumoti yo‘q</h1></section>;
  }

  return <>
    {shaky.length > 0 && <section className="card">
      <h2 className="tone-bad"><TriangleAlert size={16} aria-hidden="true" /> Ishlash kerak</h2>
      {shaky.map((row) => <Bar key={row.topic} label={row.topic} {...row} />)}
    </section>}

    {solid.length > 0 && <section className="card">
      <h2 className="tone-ok"><Check size={16} aria-hidden="true" /> Mustahkam</h2>
      {solid.map((row) => <Bar key={row.topic} label={row.topic} {...row} />)}
    </section>}

    {thin.length > 0 && <section className="card">
      <h2><CircleHelp size={16} aria-hidden="true" /> Bitta savolli mavzular</h2>
      <p className="muted-line">Bu mavzularda atigi 1 savol bo‘lgani uchun foiz ishonchli emas.</p>
      <div className="question-tags no-border">
        {thin.map((row) => <span key={row.topic} className={`tag ${row.correct ? 'tag-level' : 'tag-bad'}`}>
          {row.topic} {row.correct}/{row.total}
        </span>)}
      </div>
    </section>}
  </>;
}

function AnswerRow({ caption, label, text, tone }) {
  return <div className="answer-review">
    <span className="answer-caption">{caption}</span>
    <div className={`answer ${tone}`}>
      <span className="option-label">{label}</span>
      <RichText text={text} />
    </div>
  </div>;
}

function QuestionsTab({ data }) {
  const [filter, setFilter] = useState('wrong');
  const filters = [
    { id: 'wrong', label: `Xato ${data.wrong_answers}` },
    { id: 'skipped', label: `Javobsiz ${data.unanswered_questions}` },
    { id: 'all', label: `Hammasi ${data.total_questions}` },
  ];
  const shown = data.questions.filter((question) => (
    filter === 'all'
      || (filter === 'wrong' && question.answered && !question.is_correct)
      || (filter === 'skipped' && !question.answered)
  ));

  return <>
    <div className="question-tags no-border">
      {filters.map((item) => <button
        key={item.id}
        type="button"
        className={`tag tag-button ${filter === item.id ? 'active' : ''}`}
        onClick={() => setFilter(item.id)}
      >{item.label}</button>)}
    </div>

    {shown.length === 0
      ? <section className="card empty-state"><h1>Bu bo‘limda savol yo‘q</h1></section>
      : shown.map((question, index) => {
        const correct = (question.options || []).find((option) => option.is_correct);
        const chosen = (question.options || []).find((option) => option.label === question.selected_option);
        const status = !question.answered ? 'skipped' : question.is_correct ? 'ok' : 'bad';
        return <article className="question-card" key={question.id}>
          <div className="question-tags">
            <span className={`index-badge badge-${status}`}>{data.questions.indexOf(question) + 1}</span>
            {question.topic && <span className="tag tag-subject">{question.topic}</span>}
            {question.difficulty && <span className="tag">{question.difficulty}</span>}
          </div>
          <Question question={question} />
          {chosen && !question.is_correct && <AnswerRow caption="Sizning javobingiz" label={chosen.label} text={chosen.text} tone="wrong" />}
          {correct && <AnswerRow caption={question.is_correct ? 'Sizning javobingiz' : 'To‘g‘ri javob'} label={correct.label} text={correct.text} tone="right" />}
        </article>;
      })}
  </>;
}

export default function AnalysisPage() {
  const [state, setState] = useState({ status: 'loading', error: '', data: null });
  const [tab, setTab] = useState('result');
  const [theme, setTheme] = useState(getTelegramTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const load = useCallback(async () => {
    setState({ status: 'loading', error: '', data: null });
    try {
      const initData = initTelegram();
      const sessionId = getSessionId();
      await authenticate(initData);
      setState({ status: 'ready', error: '', data: await getAnalysis(sessionId) });
    } catch (error) {
      setState({ status: 'error', error: error.message || 'Tahlilni yuklab bo‘lmadi.', data: null });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const body = useMemo(() => {
    if (!state.data) return null;
    if (tab === 'topics') return <TopicsTab data={state.data} />;
    if (tab === 'questions') return <QuestionsTab data={state.data} />;
    return <ResultTab data={state.data} />;
  }, [state.data, tab]);

  if (state.status === 'loading') return <main className="app-shell"><p className="loading">Tahlil yuklanmoqda...</p></main>;
  if (state.status === 'error') {
    return <main className="app-shell"><section className="card error">
      <h1>Xatolik</h1>
      <p>{state.error}</p>
      <button type="button" onClick={load}>Qayta urinish</button>
    </section></main>;
  }

  return <div className="quiz-app">
    <header className="app-header">
      <div className="brand"><span className="brand-mark"><Zap size={17} fill="currentColor" /></span><strong>EduNova</strong></div>
      <button className="icon-button theme-toggle" type="button" onClick={() => setTheme(value => value === 'dark' ? 'light' : 'dark')} title="Mavzuni almashtirish" aria-label="Mavzuni almashtirish">
        {theme === 'dark' ? <Sun size={19} /> : <Moon size={19} />}
      </button>
    </header>

    <main className="app-shell analysis">
      <nav className="tab-bar" aria-label="Tahlil bo‘limlari">
        {TABS.map((item) => <button
          key={item.id}
          type="button"
          className={tab === item.id ? 'active' : ''}
          onClick={() => setTab(item.id)}
        >{item.label}</button>)}
      </nav>
      {body}
    </main>
  </div>;
}
