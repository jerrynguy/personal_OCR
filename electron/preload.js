const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  saveApiKey: (apiKey, workspaceId) => ipcRenderer.invoke('save-api-key', { apiKey, workspaceId }),
  getConfig: () => ipcRenderer.invoke('get-config'),
});
