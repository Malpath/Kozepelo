const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  openFile: () => ipcRenderer.invoke('open-file'),
  runStep: (mode, inputPath) => ipcRenderer.invoke('run-step', { mode, inputPath }),
  saveOutput: (content, suggestedName) => ipcRenderer.invoke('save-output', { content, suggestedName })
});
