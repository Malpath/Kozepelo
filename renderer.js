let inputPath = null;
let lastOutput = '';
let lastMode = null;

const $ = (sel) => document.querySelector(sel);
const outputEl = $('#output');
const filePathLabel = $('#filePathLabel');
const statusEl = $('#status');
const footInfo = $('#footInfo');

function setOutput(text) {
  lastOutput = text || '';
  outputEl.classList.remove('placeholder');
  outputEl.textContent = lastOutput;
}

function setActive(mode) {
  document.querySelectorAll('.step').forEach(b => b.classList.remove('active'));
  if (mode === 'step1') $('#btnStep1')?.classList.add('active');
  if (mode === 'step2a') $('#btnStep2a')?.classList.add('active');
  if (mode === 'step2b') $('#btnStep2b')?.classList.add('active');
  lastMode = mode;
  footInfo.textContent = mode ? `Aktív lépés: ${mode}` : '—';
}

function setStatus(text, type='') {
  statusEl.textContent = text;
  statusEl.className = 'status';
  if (type) statusEl.classList.add(type);
}

function busy(on){
  document.body.classList.toggle('busy', !!on);
}

$('#btnLoad').addEventListener('click', async () => {
  try {
    const res = await window.api.openFile();
    if (res && !res.canceled) {
      inputPath = res.filePath;
      filePathLabel.textContent = inputPath;
      setOutput(res.content); // nyers tartalom
      setActive(null);
      setStatus('Fájl betöltve. Válassz lépést!', 'ok');
    }
  } catch (err) {
    setStatus(`Hiba a betöltésnél: ${err.message || err}`, 'err');
    setOutput('');
  }
});

async function run(mode) {
  if (!inputPath) {
    setStatus('Előbb tölts be egy TXT fájlt.', 'warn');
    return;
  }
  setActive(mode);
  setStatus(`Futtatás: ${mode}...`);
  setOutput(`Futtatás: ${mode}...\n`);
  busy(true);
  try {
    const res = await window.api.runStep(mode, inputPath);
    setOutput(res.content);
    setStatus('Kész.', 'ok');
  } catch (err) {
    setStatus(`Hiba futtatás közben (${mode}): ${err.message || err}`, 'err');
    setOutput((lastOutput ? lastOutput + '\n\n' : '') + `Hiba: ${err.message || err}`);
  } finally {
    busy(false);
  }
}

$('#btnStep1').addEventListener('click', () => run('step1'));
$('#btnStep2a').addEventListener('click', () => run('step2a'));
$('#btnStep2b').addEventListener('click', () => run('step2b'));

$('#btnExport').addEventListener('click', async () => {
  if (!lastOutput) {
    setStatus('Nincs mit exportálni. Futtass egy lépést előbb.', 'warn');
    return;
  }
  try {
    const base = inputPath ? inputPath.split(/[\\/]/).pop() : 'kimenet';
    const suggested = `${base}${lastMode ? '.'+lastMode : ''}.txt`;
    const res = await window.api.saveOutput(lastOutput, suggested);
    if (res && !res.canceled) setStatus(`Exportálva ide: ${res.filePath}`, 'ok');
  } catch (err) {
    setStatus(`Export hiba: ${err.message || err}`, 'err');
  }
});

// induláskor
document.title = 'Közepelő';
footInfo.textContent = '—';
