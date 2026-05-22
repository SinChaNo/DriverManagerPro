'use strict';

// ── Constants ──────────────────────────────────────────────────────────────

const RING_CIRC = 326.73; // 2 * PI * 52

// 드라이버 카테고리 정의 — Python hardware_detect._CLASS_NORMALIZE 키와 일치
const CAT = {
  Display:       { label: '그래픽 어댑터',      icon: 'monitor',                   priority: 1 },
  Net:           { label: '네트워크 어댑터',    icon: 'router',                    priority: 2 },
  Media:         { label: '오디오 컨트롤러',    icon: 'speaker',                   priority: 3 },
  AudioEndpoint: { label: '오디오 엔드포인트',  icon: 'volume_up',                 priority: 4 },
  System:        { label: '시스템 장치',         icon: 'settings_input_component',  priority: 5 },
  Bluetooth:     { label: '블루투스',            icon: 'bluetooth',                 priority: 6 },
  USB:           { label: 'USB 컨트롤러',        icon: 'usb',                       priority: 7 },
  HIDClass:      { label: 'HID 장치',            icon: 'mouse',                     priority: 8 },
  Storage:       { label: '저장 장치',           icon: 'storage',                   priority: 9 },
  Security:      { label: '보안 장치',           icon: 'security',                  priority: 10 },
  // Processor는 트리 렌더링 시 제외 — 내장 그래픽은 Display로 별도 분류됨
  Processor:     { label: '프로세서',            icon: 'developer_board',           priority: 99 },
  Other:         { label: '기타 장치',           icon: 'hardware',                  priority: 99 },
};

const PRIORITY_CLASSES = ['Display', 'Net', 'Media', 'AudioEndpoint', 'System', 'Bluetooth', 'USB', 'Storage'];

// ── State ──────────────────────────────────────────────────────────────────

const S = {
  view: 'main',             // main | download | install | complete
  mainState: 'idle',        // idle | scanning | results
  updateList: [],
  selectedIds: new Set(),
  installStartTime: 0,
  installResults: [],
  installQueue: [],
  elapsedTimer: null,
  pollInterval: null,
  dlPollInterval: null,
  logOffset: 0,
  rebootCountdownTimer: null,
  dlFileLog: [],
};

// ── Helpers ────────────────────────────────────────────────────────────────

const $ = id => document.getElementById(id);
const api = () => window.pywebview?.api ?? null;

async function call(method, ...args) {
  const a = api();
  if (!a) { console.warn('API not ready:', method); return null; }
  try { return await a[method](...args); }
  catch (e) { console.error('API error:', method, e); return null; }
}

function fmtBytes(b) {
  if (!b) return '0 B';
  const u = ['B','KB','MB','GB'], i = Math.floor(Math.log(b) / Math.log(1024));
  return (b / 1024 ** i).toFixed(1) + ' ' + u[i];
}

function fmtElapsed(ms) {
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}초`;
  return `${Math.floor(s / 60)}분 ${s % 60}초`;
}

function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── View switching ─────────────────────────────────────────────────────────

const VIEWS = ['v-main', 'v-download', 'v-install', 'v-complete'];

function showView(id) {
  VIEWS.forEach(v => $(v).classList.add('is-hidden'));
  $(id).classList.remove('is-hidden');
  S.view = id.replace('v-', '');
}

function setMainState(state) {
  ['stateIdle','stateScanning','stateResults'].forEach(s => $(s).classList.add('is-hidden'));
  $(`state${state.charAt(0).toUpperCase() + state.slice(1)}`).classList.remove('is-hidden');
  S.mainState = state;
}

// ── Online indicator ────────────────────────────────────────────────────────

async function updateOnline() {
  const online = await call('is_online');
  const dot = $('hdrOnlineDot'), lbl = $('hdrOnlineLabel');
  if (online === null) return;
  dot.className = `w-1.5 h-1.5 rounded-full ${online ? 'dot-online' : 'dot-offline'}`;
  lbl.textContent = online ? '온라인' : '오프라인';
}

// ── System stat cards ───────────────────────────────────────────────────────

async function renderSysCards() {
  const summary = await call('get_system_summary');
  if (!summary) return;
  const container = $('sysCards');
  // BIOS 정보 포함 4개 카드 — index.html sysCards는 lg:grid-cols-4 그리드
  const cards = [
    { icon: 'developer_board',   label: 'CPU',  value: summary.cpu  || '정보 없음', tag: null },
    { icon: 'memory',            label: 'RAM',  value: summary.ram  || '정보 없음', tag: null },
    { icon: 'monitor',           label: 'GPU',  value: summary.gpu  || '정보 없음', tag: null },
    // BIOS 카드 — tag에 날짜 표시
    { icon: 'settings_firmware', label: 'BIOS', value: summary.bios_version || '정보 없음', tag: summary.bios_date || null },
  ];
  container.innerHTML = cards.map(c => `
    <div class="sys-card group hover:border-primary/40">
      <div class="flex justify-between items-start mb-2">
        <span class="material-symbols-outlined text-primary">${c.icon}</span>
        ${c.tag ? `<span class="text-xs text-muted bg-white/5 px-2 py-0.5 rounded">${c.tag}</span>` : ''}
      </div>
      <p class="text-muted text-xs font-medium">${c.label}</p>
      <p class="text-sm font-bold text-white truncate">${esc(c.value)}</p>
    </div>`).join('');
}

// ── Tree view rendering ─────────────────────────────────────────────────────

function deviceIcon(cls) {
  const c = (cls || '').toLowerCase();
  if (c.includes('display') || c.includes('video')) return 'monitor';
  if (c.includes('net') || c.includes('wifi') || c.includes('wireless')) return 'router';
  if (c.includes('audio') || c.includes('media') || c.includes('sound')) return 'speaker';
  if (c.includes('bluetooth')) return 'bluetooth';
  if (c.includes('usb')) return 'usb';
  if (c.includes('system')) return 'settings_input_component';
  if (c.includes('hid') || c.includes('mouse')) return 'mouse';
  return 'hardware';
}

function renderTree(updateList) {
  S.updateList = updateList;
  S.selectedIds.clear();

  const tree = $('deviceTree');
  const empty = $('emptyTree');

  if (!updateList.length) {
    tree.innerHTML = '';
    empty.classList.remove('is-hidden');
    $('btnUpdateSelected').disabled = true;
    $('updateBadge').classList.add('is-hidden');
    return;
  }
  empty.classList.add('is-hidden');

  // device_class별 그룹핑 — Processor는 UI에서 제외 (내장 그래픽은 Display로 별도 표시)
  const groups = {};
  updateList.forEach(d => {
    const cls = d.device_class || 'Other';
    if (cls === 'Processor') return;
    if (!groups[cls]) groups[cls] = [];
    groups[cls].push(d);
  });

  // Sort groups by priority
  const sortedClasses = Object.keys(groups).sort((a, b) => {
    const pa = (CAT[a] || CAT.Other).priority;
    const pb = (CAT[b] || CAT.Other).priority;
    return pa - pb;
  });

  // Count total updates
  const totalUpdates = updateList.filter(d => d.update_available).length;

  if (totalUpdates > 0) {
    $('updateBadge').textContent = `${totalUpdates}개 업데이트 필요`;
    $('updateBadge').classList.remove('is-hidden');
  } else {
    $('updateBadge').classList.add('is-hidden');
  }

  tree.innerHTML = sortedClasses.map(cls => {
    const devices = groups[cls];
    const catInfo = CAT[cls] || CAT.Other;
    const clsUpdates = devices.filter(d => d.update_available).length;
    const isOpen = clsUpdates > 0;

    const rows = devices.map(d => {
      const hasUpdate = d.update_available;
      const canSelect = hasUpdate;
      const ver = d.installed_version || '알 수 없음';
      const newVer = d.latest_bundled || '--';
      const icon = deviceIcon(cls);

      const badgeHtml = hasUpdate
        ? `<span class="badge badge-update"><span class="material-symbols-outlined text-[11px]">warning</span>업데이트 필요</span>`
        : `<span class="badge badge-ok"><span class="material-symbols-outlined text-[11px]">check_circle</span>최신</span>`;

      const actionHtml = hasUpdate
        ? `<button class="text-primary hover:text-white text-xs font-bold underline underline-offset-4 transition-colors install-one" data-id="${esc(d.driver_id)}">설치</button>`
        : `<button class="text-muted text-xs underline underline-offset-4 cursor-default">상세</button>`;

      return `
        <div class="device-row flex items-center px-4 py-2.5 border-t border-bdr/40">
          <div class="w-12 flex justify-center">
            <input type="checkbox" class="dev-cb w-4 h-4 rounded accent-primary cursor-pointer"
              data-id="${esc(d.driver_id)}" ${canSelect ? '' : 'disabled'}
              onclick="event.stopPropagation()"/>
          </div>
          <div class="flex-1 flex items-center gap-3 pl-7 min-w-0">
            <div class="w-8 h-8 rounded bg-primary/10 flex items-center justify-center text-primary shrink-0 ${hasUpdate ? '' : 'opacity-40'}">
              <span class="material-symbols-outlined text-[16px]">${icon}</span>
            </div>
            <div class="min-w-0">
              <p class="text-sm font-medium text-white truncate">${esc(d.device_name || d.driver_name || '알 수 없는 장치')}</p>
              <p class="text-xs text-muted truncate">${esc(d.vendor || cls)}</p>
            </div>
          </div>
          <div class="w-44 hidden lg:block text-sm text-muted shrink-0">
            ${esc(ver)} ${hasUpdate ? `<span class="text-primary text-xs">→ ${esc(newVer)}</span>` : ''}
          </div>
          <div class="w-40 shrink-0">${badgeHtml}</div>
          <div class="w-28 text-right pr-4 shrink-0">${actionHtml}</div>
        </div>`;
    }).join('');

    const catBadge = clsUpdates > 0
      ? `<span class="text-[10px] bg-red-500/20 text-red-400 border border-red-500/20 px-2 py-0.5 rounded-full font-bold ml-2">${clsUpdates} 업데이트</span>`
      : `<span class="text-[10px] bg-green-500/20 text-green-400 border border-green-500/20 px-2 py-0.5 rounded-full font-bold ml-2">최신</span>`;

    return `
      <details class="tree-category group border-b border-bdr/50 last:border-0" ${isOpen ? 'open' : ''}>
        <summary class="flex items-center px-4 py-3 bg-surface hover:bg-white/[0.03] cursor-pointer transition-colors select-none">
          <div class="w-12 flex justify-center" onclick="event.stopPropagation()">
            <input type="checkbox" class="cat-cb w-4 h-4 rounded accent-primary cursor-pointer" data-cls="${esc(cls)}"/>
          </div>
          <div class="flex-1 flex items-center gap-3">
            <span class="material-symbols-outlined text-muted chevron text-[18px]">chevron_right</span>
            <span class="material-symbols-outlined text-primary text-[18px]">${catInfo.icon}</span>
            <span class="text-sm font-semibold">${catInfo.label}</span>
            ${catBadge}
          </div>
        </summary>
        <div class="bg-bg/40">${rows}</div>
      </details>`;
  }).join('');

  // Checkbox events
  tree.querySelectorAll('.dev-cb').forEach(cb => {
    cb.addEventListener('change', () => {
      const id = cb.dataset.id;
      if (cb.checked) S.selectedIds.add(id);
      else S.selectedIds.delete(id);
      updateSelectionUI();
    });
  });

  tree.querySelectorAll('.cat-cb').forEach(cb => {
    cb.addEventListener('change', () => {
      const cls = cb.dataset.cls;
      tree.querySelectorAll(`.dev-cb[data-id]`).forEach(dcb => {
        const d = updateList.find(u => u.driver_id === dcb.dataset.id);
        if (d && d.device_class === cls && !dcb.disabled) {
          dcb.checked = cb.checked;
          if (cb.checked) S.selectedIds.add(dcb.dataset.id);
          else S.selectedIds.delete(dcb.dataset.id);
        }
      });
      updateSelectionUI();
    });
  });

  tree.querySelectorAll('.install-one').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      startInstall([btn.dataset.id]);
    });
  });

  // DB info
  const lastUpdated = (async () => {
    const settings = await call('get_settings');
    $('infoScanTime').textContent = `마지막 스캔: ${new Date().toLocaleTimeString('ko-KR')}`;
  })();
}

function updateSelectionUI() {
  const count = S.selectedIds.size;
  const btn = $('btnUpdateSelected');
  btn.disabled = count === 0;
  $('updateBtnLabel').textContent = count > 0 ? `선택 설치 (${count})` : '업데이트 선택';
}

// ── Scan flow ────────────────────────────────────────────────────────────────

async function runScan() {
  setMainState('scanning');
  $('btnMainScan').disabled = true;
  consoleLog('[INFO] 하드웨어 스캔 시작...', 'info');

  await renderSysCards();
  const updateList = await call('get_update_list');
  if (updateList === null) {
    setMainState('idle');
    $('btnMainScan').disabled = false;
    return;
  }

  consoleLog(`[INFO] 스캔 완료: ${updateList.length}개 일치, ${updateList.filter(d=>d.update_available).length}개 업데이트 가능`, 'info');
  setMainState('results');
  renderTree(updateList);
  $('btnMainScan').disabled = false;
  $('btnUpdateSelected').disabled = S.selectedIds.size === 0;
}

$('btnMainScan').addEventListener('click', runScan);

$('btnUpdateSelected').addEventListener('click', () => {
  const ids = [...S.selectedIds];
  if (ids.length) startInstall(ids);
});

// ── DB Download flow ─────────────────────────────────────────────────────────

$('btnMainDownloadDB').addEventListener('click', () => startDownload());

async function startDownload() {
  showView('v-download');
  S.dlFileLog = [];
  $('dlFileList').innerHTML = '';
  $('dlCurrentFile').textContent = '연결 중...';
  $('dlBar').style.width = '0%';
  $('dlPercent').textContent = '0%';
  $('dlBytes').textContent = '0 MB / 0 MB';
  $('dlFileCount').textContent = '0 / 0 파일';
  $('dlStatusMsg').textContent = '';

  consoleLog('[INFO] 드라이버 DB 다운로드 시작...', 'info');
  await call('download_driver_db');
  startDlPoll();
}

function startDlPoll() {
  if (S.dlPollInterval) clearInterval(S.dlPollInterval);
  S.dlPollInterval = setInterval(async () => {
    const ds = await call('get_download_state');
    if (!ds) return;

    const pct = ds.total_files > 0 ? Math.round((ds.downloaded_files / ds.total_files) * 100) : 0;
    $('dlBar').style.width = pct + '%';
    $('dlPercent').textContent = pct + '%';
    $('dlFileCount').textContent = `${ds.downloaded_files} / ${ds.total_files} 파일`;

    const curFile = ds.current_file || '';
    if (curFile) $('dlCurrentFile').textContent = curFile;

    const curMB = ((ds.current_bytes || 0) / 1048576).toFixed(1);
    const totMB = ((ds.current_total || 0) / 1048576).toFixed(1);
    $('dlBytes').textContent = `${curMB} MB / ${totMB} MB`;

    // File log entry
    if (curFile && !S.dlFileLog.includes(curFile)) {
      S.dlFileLog.push(curFile);
      const el = document.createElement('div');
      el.className = 'dl-file-entry is-active';
      el.id = `dlf-${S.dlFileLog.length}`;
      el.innerHTML = `<span class="material-symbols-outlined text-primary text-sm">download</span><span class="truncate flex-1">${esc(curFile)}</span>`;
      $('dlFileList').appendChild(el);
      $('dlFileList').scrollTop = $('dlFileList').scrollHeight;
    }

    if (ds.done) {
      clearInterval(S.dlPollInterval);
      // Mark last file as done
      const last = $('dlFileList').lastElementChild;
      if (last) { last.classList.remove('is-active'); last.classList.add('is-done'); }

      if (ds.error) {
        $('dlStatusMsg').innerHTML = `<span class="text-red-400">오류: ${esc(ds.error)}</span>`;
        consoleLog(`[ERROR] DB 다운로드 실패: ${ds.error}`, 'error');
        setTimeout(() => showView('v-main'), 3000);
      } else {
        $('dlStatusMsg').innerHTML = `<span class="text-green-400">다운로드 완료! 스캔을 시작합니다...</span>`;
        consoleLog('[INFO] DB 다운로드 완료', 'ok');
        setTimeout(async () => {
          showView('v-main');
          await runScan();
        }, 1500);
      }
    }
  }, 500);
}

$('btnCancelDownload').addEventListener('click', () => {
  clearInterval(S.dlPollInterval);
  showView('v-main');
});

// ── Install flow ──────────────────────────────────────────────────────────────

async function startInstall(driverIds) {
  S.installQueue = driverIds.map(id => {
    const d = S.updateList.find(u => u.driver_id === id);
    return { driver_id: id, driver_name: d?.driver_name || d?.device_name || id, status: 'pending', device_class: d?.device_class || '' };
  });

  // Switch to install view
  showView('v-install');
  renderInstallQueue();
  $('instPct').textContent = '0%';
  $('instRingFill').style.strokeDashoffset = RING_CIRC;
  $('instCount').textContent = `0 / ${driverIds.length}`;
  $('opName').textContent = '준비 중...';
  $('opMeta').textContent = '--';
  $('opBar').style.width = '0%';
  $('consoleOutput').innerHTML = '';
  S.logOffset = 0;
  S.installResults = [];
  S.installStartTime = Date.now();

  // Start elapsed timer
  if (S.elapsedTimer) clearInterval(S.elapsedTimer);
  S.elapsedTimer = setInterval(() => {
    $('instElapsed').textContent = fmtElapsed(Date.now() - S.installStartTime);
  }, 1000);

  consoleLog('[INFO] 드라이버 설치 큐 시작...', 'info');
  await call('start_install', driverIds);
  startInstallPoll();
}

function renderInstallQueue() {
  $('installQueue').innerHTML = S.installQueue.map((q, i) => {
    const icon = q.status === 'done' ? 'check' : q.status === 'fail' ? 'error' : q.status === 'installing' ? 'sync' : 'hourglass_empty';
    const iconColor = q.status === 'done' ? 'text-green-500' : q.status === 'fail' ? 'text-red-400' : q.status === 'installing' ? 'text-primary animate-spin' : 'text-muted';
    const bgColor   = q.status === 'done' ? 'bg-green-500/10 border-green-500/20' : q.status === 'installing' ? 'bg-primary/10 border-primary/20' : 'bg-bdr/30 border-transparent';
    const isDone    = q.status === 'done' || q.status === 'fail';

    return `
      <div id="qi-${i}" class="queue-item ${q.status === 'installing' ? 'is-active' : ''} ${isDone ? 'is-done' : ''}">
        <div class="w-10 h-10 rounded-full ${bgColor} border flex items-center justify-center shrink-0">
          <span class="material-symbols-outlined text-[18px] ${iconColor}">${icon}</span>
        </div>
        <div class="flex-1 min-w-0">
          <p class="text-sm font-bold text-white truncate">${esc(q.driver_name)}</p>
          <p class="text-xs text-muted">${q.status === 'done' ? '설치 완료' : q.status === 'fail' ? '설치 실패' : q.status === 'installing' ? '설치 중...' : '대기 중...'}</p>
        </div>
        ${q.status === 'done' ? '<div class="badge badge-done shrink-0">DONE</div>' : ''}
        ${q.status === 'fail' ? '<div class="badge badge-fail shrink-0">FAIL</div>' : ''}
      </div>`;
  }).join('');
}

function startInstallPoll() {
  if (S.pollInterval) clearInterval(S.pollInterval);
  S.pollInterval = setInterval(async () => {
    const progress = await call('get_progress');
    if (!progress) return;

    await pollLogs();

    // Ring + percent
    const pct = progress.percent || 0;
    $('instPct').textContent = pct + '%';
    $('instRingFill').style.strokeDashoffset = RING_CIRC * (1 - pct / 100);
    $('instCount').textContent = `${progress.installed} / ${progress.total}`;

    // Current op — stage별 표시 분기 (downloading | installing)
    if (progress.current_driver) {
      $('opName').textContent = progress.current_driver;

      if (progress.stage === 'downloading') {
        const dlPct = progress.download_pct || 0;
        $('opMeta').textContent = `다운로드 중... ${dlPct}%`;
        $('opBar').style.width = dlPct + '%';
        $('opStageLabel').textContent = '다운로드';
        $('opStageLabel').className = 'text-xs text-blue-400 font-medium';
      } else {
        $('opMeta').textContent = `설치 진행 중... (${progress.installed + 1}/${progress.total})`;
        $('opBar').style.width = Math.min(pct + 10, 95) + '%';
        $('opStageLabel').textContent = '설치 중';
        $('opStageLabel').className = 'text-xs text-primary font-medium';
      }

      // 큐 아이템 상태 업데이트
      S.installQueue.forEach((q, i) => {
        if (q.driver_name === progress.current_driver || q.driver_id === progress.current_driver) {
          if (q.status !== 'done' && q.status !== 'fail') {
            q.status = 'installing';
            renderInstallQueue();
          }
        } else if (q.status === 'installing' && i < progress.installed) {
          q.status = 'done';
        }
      });
    }

    if (progress.status === 'done' || progress.status === 'aborted') {
      clearInterval(S.pollInterval);
      clearInterval(S.elapsedTimer);

      // Mark all remaining queue items
      S.installQueue.forEach(q => {
        if (q.status === 'installing') q.status = 'done';
      });
      renderInstallQueue();

      const elapsed = Date.now() - S.installStartTime;
      const results = await call('get_install_results');
      S.installResults = results || [];

      consoleLog(`[INFO] 설치 ${progress.status === 'done' ? '완료' : '중단'}. 소요 시간: ${fmtElapsed(elapsed)}`, progress.status === 'done' ? 'ok' : 'warn');

      if (progress.status === 'done') {
        setTimeout(() => showComplete(elapsed, progress.reboot_required), 800);
      } else {
        setTimeout(() => showView('v-main'), 1500);
      }
    }
  }, 500);
}

$('btnAbortInstall').addEventListener('click', async () => {
  await call('abort_install');
  consoleLog('[WARNING] 설치 중단 요청됨', 'warn');
});

// ── Completion screen ──────────────────────────────────────────────────────────

function showComplete(elapsedMs, rebootRequired) {
  showView('v-complete');

  const results = S.installResults;
  const success = results.filter(r => r.success).length;
  const fail    = results.filter(r => !r.success).length;
  const allFail = fail > 0 && success === 0;
  const someFail = fail > 0 && success > 0;

  // ── 테마 동적 적용 ──
  const modal    = $('completeModal');
  const glow1    = $('completeGlow1');
  const glow2    = $('completeGlow2');
  const iconBox  = $('completeIcon');
  const iconSpan = $('completeIconSpan');

  if (allFail) {
    // 전체 실패 → 빨간 테마
    $('v-complete').style.background = '#170d0d';
    modal.style.background   = 'rgba(32,15,15,0.92)';
    modal.style.borderColor  = 'rgba(239,68,68,0.35)';
    modal.style.boxShadow    = '0 0 60px -15px rgba(239,68,68,0.3)';
    glow1.style.background   = 'rgba(239,68,68,0.15)';
    glow2.style.background   = 'rgba(239,68,68,0.10)';
    iconBox.style.background  = 'rgba(239,68,68,0.10)';
    iconBox.style.borderColor = 'rgba(239,68,68,0.35)';
    iconBox.style.boxShadow   = '0 0 20px rgba(239,68,68,0.3)';
    iconSpan.className = 'material-symbols-outlined text-red-400 text-3xl';
    iconSpan.textContent = 'cancel';
  } else if (someFail) {
    // 일부 실패 → 노란 경고 테마
    $('v-complete').style.background = '#17130a';
    modal.style.background   = 'rgba(28,22,10,0.92)';
    modal.style.borderColor  = 'rgba(234,179,8,0.35)';
    modal.style.boxShadow    = '0 0 60px -15px rgba(234,179,8,0.25)';
    glow1.style.background   = 'rgba(234,179,8,0.15)';
    glow2.style.background   = 'rgba(234,179,8,0.10)';
    iconBox.style.background  = 'rgba(234,179,8,0.10)';
    iconBox.style.borderColor = 'rgba(234,179,8,0.35)';
    iconBox.style.boxShadow   = '0 0 20px rgba(234,179,8,0.3)';
    iconSpan.className = 'material-symbols-outlined text-yellow-400 text-3xl';
    iconSpan.textContent = 'warning';
  } else {
    // 전체 성공 → 초록 테마 (기본값 복원)
    $('v-complete').style.background = '#0d170d';
    modal.style.background   = 'rgba(21,32,21,0.90)';
    modal.style.borderColor  = 'rgba(34,197,94,0.30)';
    modal.style.boxShadow    = '0 0 60px -15px rgba(19,236,19,0.25)';
    glow1.style.background   = 'rgba(34,197,94,0.15)';
    glow2.style.background   = 'rgba(34,197,94,0.10)';
    iconBox.style.background  = 'rgba(34,197,94,0.10)';
    iconBox.style.borderColor = 'rgba(34,197,94,0.30)';
    iconBox.style.boxShadow   = '0 0 20px rgba(34,197,94,0.3)';
    iconSpan.className = 'material-symbols-outlined text-green-400 text-3xl';
    iconSpan.textContent = 'check_circle';
  }

  // ── 통계 텍스트 ──
  $('completeSuccessCount').textContent = success;
  $('completeFailCount').textContent    = fail;
  $('completeElapsed').textContent      = fmtElapsed(elapsedMs);
  $('completeTitle').textContent = allFail ? '설치 실패' : someFail ? '일부 설치 완료' : '설치 완료';
  $('completeSubtitle').textContent = allFail
    ? `${fail}개의 드라이버 설치에 실패했습니다.`
    : someFail
    ? `${success}개 성공, ${fail}개 실패.`
    : `${success}개의 드라이버가 성공적으로 설치되었습니다.`;

  // ── 결과 목록 — 실패 항목은 오류 로그 토글 버튼 포함 ──
  $('completeResultList').innerHTML = results.map((r, i) => `
    <div class="flex flex-col px-3 py-2 rounded-lg ${r.success ? 'bg-white/5' : 'bg-red-500/5 border border-red-500/15'}">
      <div class="flex items-center gap-3">
        <span class="material-symbols-outlined text-sm ${r.success ? 'text-green-400' : 'text-red-400'}">${r.success ? 'check_circle' : 'error'}</span>
        <div class="flex-1 min-w-0">
          <p class="text-xs font-medium text-white truncate">${esc(r.driver_name)}</p>
          ${r.latest_bundled ? `<p class="text-[10px] text-muted">v${esc(r.latest_bundled)}</p>` : ''}
        </div>
        <span class="badge ${r.success ? 'badge-done' : 'badge-fail'} shrink-0">${r.success ? '완료' : '실패'}</span>
        ${!r.success
          ? `<button onclick="toggleErrLog(${i})" class="ml-1 text-muted hover:text-red-300 transition-colors" title="오류 상세 보기">
               <span class="material-symbols-outlined text-sm">expand_more</span>
             </button>`
          : ''}
      </div>
      ${!r.success
        ? `<div id="errlog-${i}" class="is-hidden mt-2 p-2 bg-black/40 rounded text-[10px] font-mono text-red-300 break-all leading-relaxed">${esc(r.message || '상세 오류 없음')}</div>`
        : ''}
    </div>`).join('');

  // ── 배경 흐림 테이블 ──
  $('completeBgTable').innerHTML = results.map(r => `
    <tr>
      <td class="px-4 py-3 text-white text-sm">${esc(r.driver_name)}</td>
      <td class="px-4 py-3 text-green-400 font-mono text-xs">v${esc(r.latest_bundled || '--')}</td>
      <td class="px-4 py-3 text-muted text-xs">${new Date().toLocaleDateString('ko-KR')}</td>
      <td class="px-4 py-3 text-right">
        <span class="badge ${r.success ? 'badge-done' : 'badge-fail'}">${r.success ? '완료' : '실패'}</span>
      </td>
    </tr>`).join('');

  // ── 재부팅 섹션 ──
  if (rebootRequired) {
    $('rebootSection').classList.remove('is-hidden');
    $('completeBtnsReboot').classList.remove('is-hidden');
    $('completeBtnsDone').classList.add('is-hidden');
    startRebootCountdown();
  } else {
    $('rebootSection').classList.add('is-hidden');
    $('completeBtnsReboot').classList.add('is-hidden');
    $('completeBtnsDone').classList.remove('is-hidden');
  }
}

// 실패 항목 오류 로그 토글
window.toggleErrLog = (i) => {
  const el = $(`errlog-${i}`);
  if (el) {
    el.classList.toggle('is-hidden');
    // 화살표 방향 전환
    const btn = el.previousElementSibling?.querySelector('.material-symbols-outlined');
    if (btn) btn.textContent = el.classList.contains('is-hidden') ? 'expand_more' : 'expand_less';
  }
};

function startRebootCountdown() {
  let secs = 60;
  $('rebootCountdown').textContent = secs;
  if (S.rebootCountdownTimer) clearInterval(S.rebootCountdownTimer);
  S.rebootCountdownTimer = setInterval(() => {
    secs--;
    $('rebootCountdown').textContent = secs;
    if (secs <= 0) {
      clearInterval(S.rebootCountdownTimer);
      call('reboot_system');
    }
  }, 1000);
}

$('btnRestartNow').addEventListener('click', () => {
  clearInterval(S.rebootCountdownTimer);
  call('reboot_system');
});

$('btnRestartLater').addEventListener('click', () => {
  clearInterval(S.rebootCountdownTimer);
  // 기존 결과가 있으면 results 상태로 복귀 후 자동 재스캔
  showView('v-main');
  setMainState(S.updateList.length > 0 ? 'results' : 'idle');
  setTimeout(runScan, 400);
});

$('btnCompleteDone').addEventListener('click', () => {
  // 설치 완료 후 results 상태로 복귀 + 자동 재스캔으로 최신 상태 반영
  showView('v-main');
  setMainState(S.updateList.length > 0 ? 'results' : 'idle');
  setTimeout(runScan, 400);
});

// ── Console log ────────────────────────────────────────────────────────────────

function consoleLog(text, level = 'default') {
  const out = $('consoleOutput');
  if (!out) return;
  const span = document.createElement('span');
  const cls = /\[error\]/i.test(text) ? 'cl-error'
    : /\[warning\]/i.test(text) ? 'cl-warn'
    : /\[info\]/i.test(text)    ? 'cl-info'
    : level === 'ok'            ? 'cl-ok'
    : level === 'warn'          ? 'cl-warn'
    : level === 'error'         ? 'cl-error'
    : level === 'info'          ? 'cl-info'
    : 'cl-default';
  span.className = `console-line ${cls}`;
  const now = new Date().toLocaleTimeString('ko-KR', { hour12: false });
  span.textContent = `[${now}] ${text}`;
  out.appendChild(span);
  while (out.children.length > 400) out.removeChild(out.firstChild);
  out.scrollTop = out.scrollHeight;
}

async function pollLogs() {
  const lines = await call('get_log_lines');
  if (!lines) return;
  lines.slice(S.logOffset).forEach(l => consoleLog(l));
  S.logOffset = lines.length;
}

$('btnClearConsole').addEventListener('click', () => {
  $('consoleOutput').innerHTML = '';
  S.logOffset = 0;
});

// ── Settings drawer ────────────────────────────────────────────────────────────

async function openSettings() {
  const s = await call('get_settings');
  if (s) {
    $('sRemoteUrl').value   = s.remote_manifest_url || '';
    $('sCdnUrl').value      = s.cdn_base_url        || '';
    $('sKeepVer').value     = s.keep_versions       ?? 3;
    $('sLogLevel').value    = s.log_level            || 'INFO';
    $('sAutoUpdate').checked = s.auto_update_check  ?? false;
    $('sReboot').checked     = s.reboot_prompt       ?? true;
  }
  $('settingsDrawer').classList.remove('translate-x-full');
  $('drawerOverlay').classList.remove('is-hidden');
}

function closeSettings() {
  $('settingsDrawer').classList.add('translate-x-full');
  $('drawerOverlay').classList.add('is-hidden');
}

$('btnMainSettings').addEventListener('click', openSettings);
$('btnSaveSettings').addEventListener('click', async () => {
  await call('save_settings', {
    remote_manifest_url: $('sRemoteUrl').value,
    cdn_base_url:        $('sCdnUrl').value,
    keep_versions:       parseInt($('sKeepVer').value) || 3,
    log_level:           $('sLogLevel').value,
    auto_update_check:   $('sAutoUpdate').checked,
    reboot_prompt:       $('sReboot').checked,
  });
  consoleLog('[INFO] 설정 저장 완료', 'info');
  closeSettings();
});

// Expose for inline onclick
window.closeSettings = closeSettings;

// ── Resize handler ─────────────────────────────────────────────────────────────
// 그래픽 드라이버 설치 후 해상도 변경 시 WebView2가 레이아웃을 갱신하지 않는 문제 대응.
// display none/block 토글로 강제 리플로우를 유발한다.
(function () {
  let resizeTimer = null;
  window.addEventListener('resize', () => {
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      const b = document.body;
      b.style.display = 'none';
      // offsetHeight 접근으로 레이아웃 플러시 강제 실행
      // eslint-disable-next-line no-unused-expressions
      b.offsetHeight;
      b.style.display = '';
    }, 150);
  });
})();

// ── Init ────────────────────────────────────────────────────────────────────────

async function init() {
  if (!window.pywebview) {
    document.addEventListener('pywebviewready', init);
    return;
  }

  updateOnline();
  setInterval(updateOnline, 30000);

  const hasDB = await call('has_driver_db');
  if (hasDB) {
    setMainState('idle');
    consoleLog('[INFO] 드라이버 DB 감지됨. 스캔 준비 완료.', 'info');
  } else {
    setMainState('idle');
    consoleLog('[WARNING] 드라이버 DB가 비어 있습니다. "DB 업데이트" 버튼으로 다운로드하세요.', 'warn');
  }

  await renderSysCards();
}

window.addEventListener('pywebviewready', init);

// Browser dev-mode fallback
if (!window.pywebview) {
  setTimeout(() => {
    if (!window.pywebview) {
      console.info('Dev mode: pywebview not found');
      setMainState('idle');
      renderSysCards();
    }
  }, 600);
}
