import QuizPage from './pages/QuizPage';
import ReviewPage from './pages/ReviewPage';
import { getMode } from './utils/telegram';

export default function App() {
  return getMode() === 'review' ? <ReviewPage /> : <QuizPage />;
}
