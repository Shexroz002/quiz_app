import AnalysisPage from './pages/AnalysisPage';
import QuizPage from './pages/QuizPage';
import ReviewPage from './pages/ReviewPage';
import { getMode } from './utils/telegram';

const PAGES = { review: ReviewPage, analysis: AnalysisPage };

export default function App() {
  const Page = PAGES[getMode()] || QuizPage;
  return <Page />;
}
