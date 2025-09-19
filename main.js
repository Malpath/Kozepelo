// main.js — Közepelő (Electron + Python/EXE processor)
const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const os = require('os');
const fs = require('fs');
const { spawn, spawnSync } = require('child_process');

let mainWindow;

function createWindow() {
  try { app.setName('Közepelő'); } catch {}
  mainWindow = new BrowserWindow({
    title: 'Közepelő',
    width: 1220,
    height: 820,
    backgroundColor: '#0b1020',
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  mainWindow.loadFile('index.html');
}

app.whenReady().then(() => {
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

// ---------- helpers ----------
function getPythonCmd() {
  let cmd = 'python3';
  try { if (spawnSync(cmd, ['--version']).status === 0) return cmd; } catch {}
  cmd = 'python';
  try { if (spawnSync(cmd, ['--version']).status === 0) return cmd; } catch {}
  return null;
}

function loadJSONSafe(p) {
  try { return JSON.parse(fs.readFileSync(p, 'utf-8')); } catch { return {}; }
}
function saveJSONSafe(p, obj) {
  try { fs.writeFileSync(p, JSON.stringify(obj, null, 2), 'utf-8'); } catch {}
}

/**
 * Először a beágyazott binárisokat keresi:
 *   - Windows: resources/python-win/feldolgozo.exe
 *   - macOS:   resources/python-mac/feldolgozo
 * Ha nincs, nézi a projekt gyökerét, az input mappáját, és a korábban elmentett útvonalat.
 * Ha így sem találja, fájlválasztóban megkéri és eltárolja.
 */
async function resolveProcessor(inputPath) {
  const isWin = process.platform === 'win32';
  const isMac = process.platform === 'darwin';
  const candidates = [];

  // 1) csomagolt app resources
  if (process.resourcesPath) {
    if (isWin) candidates.push(path.join(process.resourcesPath, 'python-win', 'feldolgozo.exe'));
    if (isMac) candidates.push(path.join(process.resourcesPath, 'python-mac', 'feldolgozo'));
    candidates.push(path.join(process.resourcesPath, 'feldolgozo.py'));
  }

  // 2) fejlesztői környezet / projekt gyökér
  const root = __dirname;
  if (isWin) candidates.push(path.join(root, 'python-win', 'feldolgozo.exe'));
  if (isMac) candidates.push(path.join(root, 'python-mac', 'feldolgozo'));
  candidates.push(path.join(root, 'feldolgozo.py'));

  // 3) bemeneti fájl mappája
  if (inputPath) {
    const base = path.dirname(inputPath);
    if (isWin) candidates.push(path.join(base, 'feldolgozo.exe'));
    candidates.push(path.join(base, 'feldolgozo.py'));
  }

  // 4) korábban elmentett útvonal
  const cfgPath = path.join(app.getPath('userData'), 'config.json');
  const cfg = loadJSONSafe(cfgPath);
  if (cfg.processorPath) candidates.push(cfg.processorPath);

  // találat?
  for (const p of candidates) {
    if (p && fs.existsSync(p)) {
      return { path: p, type: p.endsWith('.py') ? 'py' : 'exe', cfgPath };
    }
  }

  // 5) kérjük be a felhasználótól
  const res = await dialog.showOpenDialog({
    title: 'Válaszd ki a feldolgozót (feldolgozo.exe vagy feldolgozo.py)',
    properties: ['openFile'],
    filters: [
      { name: 'Processor', extensions: ['exe', 'py'] },
      { name: 'All files', extensions: ['*'] }
    ]
  });
  if (res.canceled || !res.filePaths?.[0]) {
    throw new Error('Nem találom a feldolgozót (feldolgozo.exe / feldolgozo.py).');
  }
  const chosen = res.filePaths[0];
  cfg.processorPath = chosen;
  saveJSONSafe(cfgPath, cfg);
  return { path: chosen, type: chosen.endsWith('.py') ? 'py' : 'exe', cfgPath };
}

// ---------- IPC ----------
ipcMain.handle('open-file', async () => {
  const res = await dialog.showOpenDialog({
    title: 'Válassz TXT fájlt',
    properties: ['openFile'],
    filters: [{ name: 'Text', extensions: ['txt'] }]
  });
  if (res.canceled || !res.filePaths?.[0]) return { canceled: true };
  const filePath = res.filePaths[0];
  const content = fs.readFileSync(filePath, 'utf-8');
  return { canceled: false, filePath, content };
});

ipcMain.handle('run-step', async (_e, { mode, inputPath }) => {
  // processor (EXE előny, különben PY)
  const { path: procPath, type } = await resolveProcessor(inputPath);

  // ideiglenes kimeneti fájl
  const outPath = path.join(
    os.tmpdir(),
    `${path.basename(inputPath)}.${mode}.${Date.now()}.out.txt`
  );

  return new Promise((resolve, reject) => {
    let child, args;

    if (type === 'exe') {
      // beágyazott feldolgozó EXE közvetlenül
      args = [inputPath, outPath, '--mode', mode];
      child = spawn(procPath, args, { shell: false });
    } else {
      // Python szkript fallback
      const pyCmd = getPythonCmd();
      if (!pyCmd) return reject(new Error('Python nem található a rendszeren (python3/python).'));
      args = [procPath, inputPath, outPath, '--mode', mode];
      child = spawn(pyCmd, args, { shell: false });
    }

    let stderr = '';
    child.stderr.on('data', d => { stderr += d.toString(); });
    child.on('close', (code) => {
      if (code !== 0) return reject(new Error(`Processor hibakód: ${code}\n${stderr}`));
      try {
        const out = fs.readFileSync(outPath, 'utf-8');
        fs.unlink(outPath, () => {});
        resolve({ content: out });
      } catch (err) {
        reject(err);
      }
    });
  });
});

ipcMain.handle('save-output', async (_e, { content, suggestedName }) => {
  const res = await dialog.showSaveDialog({
    title: 'Exportálás',
    defaultPath: suggestedName || 'kimenet.txt',
    filters: [{ name: 'Text', extensions: ['txt'] }]
  });
  if (res.canceled || !res.filePath) return { canceled: true };
  fs.writeFileSync(res.filePath, content, 'utf-8');
  return { canceled: false, filePath: res.filePath };
});
