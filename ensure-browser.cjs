/**
 * @file ensure-browser.js
 * @description Tüm işletim sistemlerinde (macOS, Linux, Windows) çalışan, akalin-browser-module
 * Playwright Chromium Headless Docker container'ını (akalin-virtual-browser) başlatan, sağlık
 * durumunu denetleyen ve ProjectNavigation ile tam entegre çalışan otomasyon scriptidir.
 */
const { spawnSync } = require('child_process');
const os = require('os');
const fs = require('fs');
const path = require('path');
const http = require('http');

const CONFIG = {
  containerName: process.env.BROWSER_CONTAINER_NAME || 'akalin-virtual-browser',
  composeFile: path.join(__dirname, 'docker-compose.yml'),
  hostPort: parseInt(process.env.BROWSER_HOST_PORT || '8002', 10),
};

const sleepSync = (ms) => {
  const shared = new SharedArrayBuffer(4);
  const view = new Int32Array(shared);
  Atomics.wait(view, 0, 0, ms);
};

const resolveDockerBinary = () => {
  const platform = os.platform();
  const candidates = platform === 'win32'
    ? [
        'docker',
        'C:\\Program Files\\Docker\\Docker\\resources\\bin\\docker.exe',
        path.join(process.env.ProgramFiles || 'C:\\Program Files', 'Docker', 'Docker', 'resources', 'bin', 'docker.exe')
      ]
    : [
        'docker',
        '/usr/local/bin/docker',
        '/opt/homebrew/bin/docker',
        '/usr/bin/docker',
        '/Applications/Docker.app/Contents/Resources/bin/docker'
      ];

  for (const bin of candidates) {
    try {
      if (bin !== 'docker' && !fs.existsSync(bin)) continue;
      const res = spawnSync(bin, ['--version'], { encoding: 'utf8', timeout: 5000 });
      if (res.status === 0) return bin;
    } catch (e) { }
  }
  return 'docker';
};

const DOCKER_BIN = resolveDockerBinary();

const runDocker = (args, { ignoreError = false, timeout = 300000, cwd = __dirname } = {}) => {
  const res = spawnSync(DOCKER_BIN, args, {
    cwd,
    encoding: 'utf8',
    timeout,
    env: {
      ...process.env,
      PATH: os.platform() === 'win32'
        ? process.env.PATH
        : `/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:${process.env.PATH || ''}`
    }
  });

  if (res.error) {
    if (ignoreError) return { ok: false, stdout: '', stderr: res.error.message };
    throw new Error(`Docker komutu çalıştırılamadı (${DOCKER_BIN} ${args.join(' ')}): ${res.error.message}`);
  }

  if (res.status !== 0 && !ignoreError) {
    const errMsg = (res.stderr || res.stdout || `Çıkış kodu: ${res.status}`).trim();
    throw new Error(`Docker hatası (${args.join(' ')}): ${errMsg}`);
  }

  return {
    ok: res.status === 0,
    stdout: (res.stdout || '').trim(),
    stderr: (res.stderr || '').trim()
  };
};

const ensureDockerDaemonRunning = () => {
  const info = runDocker(['info'], { ignoreError: true, timeout: 10000 });
  if (info.ok) return true;

  if (os.platform() === 'darwin' && fs.existsSync('/Applications/Docker.app')) {
    console.log('⏳ Docker Desktop kapalı görünüyor, otomatik başlatılıyor...');
    spawnSync('open', ['-a', 'Docker'], { encoding: 'utf8' });
    for (let i = 0; i < 45; i++) {
      sleepSync(2000);
      const retry = runDocker(['info'], { ignoreError: true, timeout: 5000 });
      if (retry.ok) {
        console.log('✅ Docker Desktop hazır.');
        return true;
      }
    }
  }

  throw new Error(
    'Docker servisine ulaşılamıyor. Lütfen Docker Desktop / Docker Engine servisinin çalıştığından emin olun.\n' +
    `Detay: ${info.stderr || 'Docker daemon yanıt vermiyor.'}`
  );
};

const getContainerState = () => {
  const res = runDocker(
    ['inspect', '-f', '{{.State.Status}}', CONFIG.containerName],
    { ignoreError: true, timeout: 10000 }
  );
  if (!res.ok || !res.stdout) return 'missing';
  return res.stdout.toLowerCase().trim();
};

const waitForHttpReady = (maxWaitSeconds = 60) => {
  console.log(`⏳ Sanal Tarayıcı HTTP uç noktası (http://127.0.0.1:${CONFIG.hostPort}/docs) bekleniyor...`);
  const startTime = Date.now();
  const deadline = startTime + maxWaitSeconds * 1000;

  while (Date.now() < deadline) {
    try {
      const res = spawnSync('curl', ['-s', '-o', '/dev/null', '-w', '%{http_code}', `http://127.0.0.1:${CONFIG.hostPort}/docs`], {
        encoding: 'utf8',
        timeout: 2000
      });
      if (res.status === 0 && (res.stdout.trim() === '200' || res.stdout.trim() === '307')) {
        console.log(`✅ Sanal Tarayıcı Docker konteyneri hazır ve çalışıyor (Port: ${CONFIG.hostPort}).`);
        return true;
      }
    } catch (e) { }
    sleepSync(1000);
  }
  console.warn(`⚠️ Sanal Tarayıcı ${maxWaitSeconds}s içinde HTTP 200 vermedi, ancak container ayakta.`);
  return false;
};

const ensureBrowserContainer = () => {
  console.log('==============================================================');
  console.log(`🌐 Akalin Virtual Browser (Docker Playwright) Başlatılıyor (${os.platform()})`);
  console.log('==============================================================');

  ensureDockerDaemonRunning();

  const state = getContainerState();
  if (state === 'missing') {
    console.log(`📦 ${CONFIG.containerName} imajı derleniyor ve başlatılıyor...`);
    runDocker(['compose', '-f', CONFIG.composeFile, 'up', '-d', '--build'], { timeout: 600000 });
  } else if (state !== 'running') {
    console.log(`▶️  Mevcut ${CONFIG.containerName} container'ı başlatılıyor (önceki durum: ${state})...`);
    runDocker(['start', CONFIG.containerName]);
  } else {
    console.log(`🟢 ${CONFIG.containerName} container'ı zaten çalışıyor (Port: ${CONFIG.hostPort}).`);
  }

  waitForHttpReady(60);
};

const stopBrowserContainer = () => {
  ensureDockerDaemonRunning();
  const state = getContainerState();
  if (state === 'running') {
    console.log(`🛑 ${CONFIG.containerName} durduruluyor...`);
    runDocker(['stop', CONFIG.containerName], { ignoreError: true });
    console.log(`✅ ${CONFIG.containerName} durduruldu.`);
  } else {
    console.log(`ℹ️  ${CONFIG.containerName} zaten çalışmıyor (durum: ${state}).`);
  }
};

const showStatus = () => {
  ensureDockerDaemonRunning();
  const state = getContainerState();
  console.log(`Container: ${CONFIG.containerName} | Port: ${CONFIG.hostPort} | Durum: ${state.toUpperCase()}`);
};

const showLogs = () => {
  ensureDockerDaemonRunning();
  const res = runDocker(['logs', '--tail', '150', CONFIG.containerName], { ignoreError: true });
  console.log(res.stdout || res.stderr || 'Log bulunamadı.');
};

if (require.main === module) {
  try {
    const action = (process.argv[2] || 'start').toLowerCase();
    if (action === 'start' || action === 'ensure' || action === 'up') {
      ensureBrowserContainer();
    } else if (action === 'stop' || action === 'down') {
      stopBrowserContainer();
    } else if (action === 'restart') {
      stopBrowserContainer();
      ensureBrowserContainer();
    } else if (action === 'status') {
      showStatus();
    } else if (action === 'logs') {
      showLogs();
    } else {
      console.log('Kullanım: node ensure-browser.js [start|stop|restart|status|logs]');
      process.exit(1);
    }
  } catch (err) {
    console.error(`❌ Hata: ${err.message}`);
    process.exit(1);
  }
}

module.exports = {
  CONFIG,
  ensureBrowserContainer,
  stopBrowserContainer,
  getContainerState,
  showStatus,
  showLogs,
};
