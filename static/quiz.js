// quiz.js -- BYD Tech Quiz
// Modules: I18n -> State -> API -> UI -> App

// =========================================================================
// I18n -- Translation strings
// =========================================================================
let lang = new URLSearchParams(window.location.search).get('lang') || 'en';
if (lang !== 'en' && lang !== 'es') lang = 'en';

const T = {
  en: {
    title: '⚙️ BYD Tech Quiz',
    subtitle: '5 random questions -- test your BYD technical knowledge',
    startTitle: '⚙️ BYD Tech Quiz',
    startSubtitle: 'Test your BYD technical knowledge with 5 random questions.',
    startBtn: 'Start Quiz',
    loading: 'Loading questions...',
    checkBtn: '✓ Check Answers',
    correct: '✅ Correct!',
    great: 'Excellent!',
    good: 'Good job!',
    meh: 'Keep practicing!',
    unanswered: '⚠️ Please answer all questions and try again.',
    scoreLabel: 'Score',
    answered: 'Answered',
    errorLoad: '⚠️ Failed to load questions.',
    retry: 'Retry',
    tryAgain: 'Try Again',
    catLabel: 'BYD Tech',
    multiHint: '(Select all that apply)',
    multiTag: 'MULTI',
    yourAnswer: 'Your answer',
    correctAnswer: 'Correct answer',
  },
  es: {
    title: '⚙️ Cuestionario Tecnico BYD',
    subtitle: '5 preguntas aleatorias -- pon a prueba tu conocimiento tecnico BYD',
    startTitle: '⚙️ Cuestionario Tecnico BYD',
    startSubtitle: 'Pon a prueba tu conocimiento tecnico BYD con 5 preguntas aleatorias.',
    startBtn: 'Comenzar',
    loading: 'Cargando preguntas...',
    checkBtn: '✓ Verificar Respuestas',
    correct: '✅ ¡Correcto!',
    great: '¡Excelente!',
    good: '¡Buen trabajo!',
    meh: '¡Sigue practicando!',
    unanswered: '⚠️ Por favor responde todas las preguntas e intenta de nuevo.',
    scoreLabel: 'Puntuacion',
    answered: 'Respondidas',
    errorLoad: '⚠️ Error al cargar las preguntas.',
    retry: 'Reintentar',
    tryAgain: 'Intentar de nuevo',
    catLabel: 'Tecnologia BYD',
    multiHint: '(Selecciona todas las correctas)',
    multiTag: 'MULTI',
    yourAnswer: 'Tu respuesta',
    correctAnswer: 'Respuesta correcta',
  }
};

function t(key) { return T[lang][key]; }

function applyLangUrl() {
  const url = new URL(window.location);
  url.searchParams.set('lang', lang);
  window.history.replaceState({}, '', url);
}

function switchLang() {
  lang = lang === 'en' ? 'es' : 'en';
  applyLangUrl();
  var screen = getCurrentScreen();
  if (screen === 'start') renderStartScreen();
  else if (screen === 'quiz') renderQuestions();
  else if (screen === 'result') renderResult();
}

// =========================================================================
// State
// =========================================================================
var questions = [];
var answered = false;
var sessionId = '';
var lastResult = null;

function genSessionId() {
  return 'qz_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
}

function resetState() {
  questions = [];
  answered = false;
  sessionId = genSessionId();
  lastResult = null;
}

// =========================================================================
// API
// =========================================================================
async function fetchQuestions() {
  var resp = await fetch('/api/questions');
  if (!resp.ok) throw new Error('API error');
  var data = await resp.json();
  if (data.error) throw new Error(data.error);
  return data.questions;
}

async function submitAnswers(answers) {
  try {
    await fetch('/api/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, answers: answers }),
    });
  } catch (err) {
    console.error('Submit failed:', err);
  }
}
