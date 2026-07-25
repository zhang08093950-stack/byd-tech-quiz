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

// =========================================================================
// UI -- Screen management
// =========================================================================
function showScreen(name) {
  document.getElementById('startScreen').style.display = name === 'start' ? 'block' : 'none';
  document.getElementById('loading').style.display = name === 'loading' ? 'block' : 'none';
  document.getElementById('quizArea').style.display = name === 'quiz' ? 'block' : 'none';
  document.getElementById('resultScreen').style.display = name === 'result' ? 'block' : 'none';
  document.getElementById('progressWrap').style.display = (name === 'quiz' || name === 'result') ? 'block' : 'none';
  document.getElementById('scoreDisplay').style.display = name === 'result' ? 'inline-flex' : 'none';
  document.getElementById('scoreHero').classList.toggle('show', name === 'result');
}

function getCurrentScreen() {
  if (document.getElementById('startScreen').style.display === 'block') return 'start';
  if (document.getElementById('loading').style.display === 'block') return 'loading';
  if (document.getElementById('quizArea').style.display === 'block') return 'quiz';
  if (document.getElementById('resultScreen').style.display === 'block') return 'result';
  return 'start';
}

// =========================================================================
// UI -- Start Screen
// =========================================================================
function renderStartScreen() {
  document.getElementById('langBtn').textContent = lang === 'en' ? 'ES' : 'EN';
  document.title = t('title');
  document.getElementById('title').textContent = t('title');
  document.getElementById('subtitle').textContent = t('subtitle');
  showScreen('start');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// =========================================================================
// UI -- Quiz
// =========================================================================
function renderQuestions() {
  document.getElementById('langBtn').textContent = lang === 'en' ? 'ES' : 'EN';
  document.title = t('title');
  document.getElementById('title').textContent = t('title');
  document.getElementById('subtitle').textContent = t('subtitle');
  document.getElementById('submitBtn').textContent = t('checkBtn');
  document.getElementById('submitBtn').disabled = false;
  document.getElementById('progressLabel').textContent = t('answered') + ' 0/' + questions.length;
  document.getElementById('progressPct').textContent = '0%';
  document.getElementById('progressFill').style.width = '0%';
  document.getElementById('progressFill').classList.remove('complete');

  var container = document.getElementById('questionsContainer');
  container.innerHTML = '';

  questions.forEach(function(q, i) {
    var card = document.createElement('div');
    card.className = 'question-card stagger-in stagger-' + (i + 1);
    card.id = 'qcard-' + i;

    var questionText = lang === 'es' ? q.question_es : q.question_en;
    var options = lang === 'es' ? q.options_es : q.options_en;
    var isMulti = q.multi;
    var inputType = isMulti ? 'checkbox' : 'radio';
    var multiHint = isMulti ? '<span class="multi-hint">' + t('multiHint') + '</span>' : '';

    var optionsHtml = options.map(function(opt, j) {
      return '<label class="option">' +
        '<input type="' + inputType + '" name="q' + i + '" value="' + j + '">' +
        '<span class="option-letter">' + String.fromCharCode(65 + j) + '</span>' +
        '<span class="option-text">' + opt + '</span>' +
        '</label>';
    }).join('');

    card.innerHTML = '<div class="q-header">' +
      '<span class="q-num">#' + (i + 1) + '</span>' +
      '<span class="q-type-tag">' + t('catLabel') + '</span>' +
      (isMulti ? '<span class="q-type-tag multi-tag">' + t('multiTag') + '</span>' : '') +
      '</div>' +
      '<div class="q-body">' +
      '<p class="q-text">' + questionText + ' ' + multiHint + '</p>' +
      '<div class="options" id="options-' + i + '">' + optionsHtml + '</div>' +
      '<div class="explanation" id="explanation-' + i + '" style="display:none"></div>' +
      '</div>';

    container.appendChild(card);
  });

  showScreen('quiz');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// =========================================================================
// UI -- Progress (real-time)
// =========================================================================
function updateProgress() {
  var total = questions.length;
  if (total === 0) return;
  var count = 0;
  for (var i = 0; i < total; i++) {
    var isMulti = questions[i].multi;
    if (isMulti) {
      var checked = document.querySelectorAll('input[name="q' + i + '"]:checked');
      if (checked.length > 0) count++;
    } else {
      var selected = document.querySelector('input[name="q' + i + '"]:checked');
      if (selected) count++;
    }
  }
  var pct = Math.round(count / total * 100);
  document.getElementById('progressLabel').textContent = t('answered') + ' ' + count + '/' + total;
  document.getElementById('progressPct').textContent = pct + '%';
  document.getElementById('progressFill').style.width = pct + '%';
}

// =========================================================================
// UI -- Result Screen
// =========================================================================
function renderResult() {
  if (!lastResult) return;

  document.getElementById('langBtn').textContent = lang === 'en' ? 'ES' : 'EN';
  document.title = t('title');
  document.getElementById('title').textContent = t('title');
  document.getElementById('subtitle').textContent = t('subtitle');

  var correct = lastResult.correct;
  var total = lastResult.total;
  var pct = lastResult.pct;

  var heroVal = document.getElementById('scoreHeroValue');
  var heroLabel = document.getElementById('scoreHeroLabel');
  heroVal.textContent = correct + '/' + total;
  if (pct >= 80) {
    heroVal.className = 'big-score great';
    heroLabel.textContent = t('great');
  } else if (pct >= 50) {
    heroVal.className = 'big-score good';
    heroLabel.textContent = t('good');
  } else {
    heroVal.className = 'big-score meh';
    heroLabel.textContent = t('meh');
  }

  var scorePill = document.getElementById('scoreDisplay');
  scorePill.textContent = t('scoreLabel') + ': ' + correct + '/' + total;
  scorePill.classList.add('show');

  document.getElementById('progressLabel').textContent = t('answered') + ' ' + total + '/' + total;
  document.getElementById('progressPct').textContent = '100%';
  document.getElementById('progressFill').style.width = '100%';
  document.getElementById('progressFill').classList.add('complete');

  var reviewContainer = document.getElementById('resultReview');
  reviewContainer.innerHTML = '';

  questions.forEach(function(q, i) {
    var isMulti = q.multi;
    var qText = lang === 'es' ? q.question_es : q.question_en;
    var options = lang === 'es' ? q.options_es : q.options_en;
    var correctIdxArr = lastResult.correctIndexesByQ[i] || [];
    var chosenIdxArr = lastResult.chosenByQ[i] || [];
    var isCorrect = isMulti
      ? correctIdxArr.sort().join(',') === chosenIdxArr.sort().join(',')
      : chosenIdxArr[0] === correctIdxArr[0];

    var chosenTexts = chosenIdxArr.length > 0
      ? chosenIdxArr.map(function(j) { return String.fromCharCode(65 + j) + '. ' + (options[j] || '?'); }).join('; ')
      : t('unanswered');
    var correctTexts = correctIdxArr.map(function(j) { return String.fromCharCode(65 + j) + '. ' + (options[j] || '?'); }).join('; ');

    var accordion = document.createElement('div');
    accordion.className = 'result-accordion ' + (isCorrect ? 'correct' : 'incorrect') + ' stagger-in';
    accordion.style.animationDelay = (i * 0.05) + 's';
    accordion.innerHTML = '<div class="result-accordion-header" onclick="this.parentElement.classList.toggle(\'open\')">' +
      '<span class="result-accordion-icon">' + (isCorrect ? '✅' : '❌') + '</span>' +
      '<span class="result-accordion-qnum">Q' + (i + 1) + '</span>' +
      '<span class="result-accordion-summary">' + qText.replace(/<[^>]*>/g, '') + '</span>' +
      '<span class="result-accordion-chevron">▼</span>' +
      '</div>' +
      '<div class="result-accordion-body">' +
      '<p><strong>' + t('yourAnswer') + ':</strong> <span class="' + (isCorrect ? 'correct-answer' : 'your-answer') + '">' + chosenTexts + '</span></p>' +
      (!isCorrect ? '<p><strong>' + t('correctAnswer') + ':</strong> <span class="correct-answer">' + correctTexts + '</span></p>' : '') +
      '</div>';
    reviewContainer.appendChild(accordion);
  });

  showScreen('result');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
