const { app, BrowserWindow, ipcMain, Menu } = require('electron');
const path = require('path');
const fs = require('fs');
const http = require('http');
const { spawn } = require('child_process');

const PORT = 3922;
const SERVER_URL = `http://127.0.0.1:${PORT}`;

let serverProcess = null;
let mainWindow = null;
let settingsWindow = null;

function getConfigPath() {
  return path.join(app.getPath('userData'), 'config.json');
}

function readConfig() {
  try {
    return JSON.parse(fs.readFileSync(getConfigPath(), 'utf-8'));
  } catch {
    return {};
  }
}

function writeConfig(config) {
  const configPath = getConfigPath();
  fs.mkdirSync(path.dirname(configPath), { recursive: true });
  fs.writeFileSync(configPath, JSON.stringify(config, null, 2), 'utf-8');
}

function getStandaloneDir() {
  // Khi đã đóng gói (.exe): server đứng trong resources/standalone
  // Khi chạy dev (npm run electron:dev): server đứng trong .next/standalone
  return app.isPackaged
    ? path.join(process.resourcesPath, 'standalone')
    : path.join(__dirname, '..', '.next', 'standalone');
}

function stopServer() {
  if (serverProcess) {
    serverProcess.kill();
    serverProcess = null;
  }
}

function startServer(apiKey, workspaceId) {
  stopServer();
  const standaloneDir = getStandaloneDir();
  const serverPath = path.join(standaloneDir, 'server.js');

  serverProcess = spawn(process.execPath, [serverPath], {
    cwd: standaloneDir,
    env: {
      ...process.env,
      PORT: String(PORT),
      HOSTNAME: '127.0.0.1',
      ANTHROPIC_API_KEY: apiKey || '',
      ANTHROPIC_WORKSPACE_ID: workspaceId || '',
      ELECTRON_RUN_AS_NODE: '1', // chạy Node lõi bên trong Electron, không cần cài Node.js riêng
    },
  });

  serverProcess.stdout.on('data', (d) => console.log(`[server] ${d}`.trim()));
  serverProcess.stderr.on('data', (d) => console.error(`[server] ${d}`.trim()));
  serverProcess.on('exit', (code) => {
    if (code && code !== 0) console.error(`Server thoát với mã lỗi ${code}`);
  });
}

function waitForServer(url, timeoutMs = 20000) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const attempt = () => {
      const req = http.get(url, (res) => {
        res.destroy();
        resolve();
      });
      req.on('error', () => {
        if (Date.now() - start > timeoutMs) reject(new Error('Server không khởi động kịp.'));
        else setTimeout(attempt, 300);
      });
    };
    attempt();
  });
}

async function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1150,
    height: 820,
    minWidth: 720,
    minHeight: 560,
    backgroundColor: '#12141a',
    autoHideMenuBar: true,
    icon: path.join(__dirname, 'icon.png'),
    webPreferences: { contextIsolation: true, nodeIntegration: false },
  });

  try {
    await waitForServer(SERVER_URL);
    mainWindow.loadURL(SERVER_URL);
  } catch (err) {
    mainWindow.loadURL(
      'data:text/html,' +
        encodeURIComponent(
          `<body style="background:#12141a;color:#f87171;font-family:sans-serif;padding:24px">
            <h2>Không khởi động được server</h2><p>${err.message}</p></body>`
        )
    );
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function createSettingsWindow() {
  if (settingsWindow) {
    settingsWindow.focus();
    return;
  }
  settingsWindow = new BrowserWindow({
    width: 480,
    height: 460,
    resizable: false,
    autoHideMenuBar: true,
    backgroundColor: '#12141a',
    icon: path.join(__dirname, 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  settingsWindow.loadFile(path.join(__dirname, 'settings.html'));
  settingsWindow.on('closed', () => {
    settingsWindow = null;
  });
}

function buildMenu() {
  const template = [
    {
      label: 'Cài đặt',
      submenu: [
        {
          label: 'Đổi API key...',
          click: () => createSettingsWindow(),
        },
        { type: 'separator' },
        { role: 'quit', label: 'Thoát' },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

ipcMain.handle('save-api-key', async (_event, { apiKey, workspaceId }) => {
  writeConfig({ apiKey, workspaceId });
  startServer(apiKey, workspaceId);
  if (settingsWindow) {
    settingsWindow.close();
  }
  if (!mainWindow) {
    await createMainWindow();
  } else {
    try {
      await waitForServer(SERVER_URL);
      mainWindow.loadURL(SERVER_URL);
    } catch (err) {
      console.error(err);
    }
  }
  return true;
});

ipcMain.handle('get-config', () => readConfig());

app.whenReady().then(async () => {
  buildMenu();
  const config = readConfig();
  if (config.apiKey) {
    startServer(config.apiKey, config.workspaceId);
    await createMainWindow();
  } else {
    createSettingsWindow();
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      const cfg = readConfig();
      if (cfg.apiKey) createMainWindow();
      else createSettingsWindow();
    }
  });
});

app.on('window-all-closed', () => {
  stopServer();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  stopServer();
});
