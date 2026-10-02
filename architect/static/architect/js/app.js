/**
 * AIBPMN Architect — Interactive IDE & Controller
 */

document.addEventListener('DOMContentLoaded', () => {
  // ── State ─────────────────────────────────────────────────────────────
  let currentProjectId = window.INITIAL_DATA ? window.INITIAL_DATA.projectId : null;
  let currentDiagramId = window.INITIAL_DATA ? window.INITIAL_DATA.diagramId : null;
  let isGenerating = false;
  let abortController = null;
  let isImporting = false;
  let codeFromVisual = false;
  let lastVisualDsl = null;
  let compileTimer = null;
  let visualSyncTimer = null;
  let lastSourceOfChange = 'init'; // 'code' | 'visual' | 'ai' | 'loaded'
  let activeTraceElementId = null;
  let currentTraceability = [];
  let lastUserPromptText = '';

  // ── Prism BPMN-as-Code Syntax Grammar ─────────────────────────────────
  if (window.Prism) {
    Prism.languages.bac = {
      'comment': {
        pattern: /(^|[^\\])#.*/,
        lookbehind: true,
        greedy: true
      },
      'string': {
        pattern: /"(?:\\.|[^"\\])*"|\[(?:\\.|[^\]\\])*\]/,
        greedy: true
      },
      'keyword': /\b(process|pool|lane|task|service|user|script|manual|businessrule|send|receive|call|subprocess|gateway|exclusive|parallel|inclusive|eventbased|complex|start|end|intermediate|catch|throw|timer|message|signal|error|terminate|escalation|compensate|conditional|link|event|dataobject|datastore|textannotation|by|note|on)\b/i,
      'operator': /--\[.*?\]-->|==>|->|-->|--/,
      'property': /\b(id|name|type|assignee|condition|documentation)\b/i,
      'punctuation': /[{}[\]:;,]/,
      'variable': /\b[a-zA-Z_][a-zA-Z0-9_-]*\b/
    };
  }

  // ── Helper: Safe Lucide Refresh ────────────────────────────────────────
  function refreshIcons() {
    if (window.lucide && typeof window.lucide.createIcons === 'function') {
      try {
        window.lucide.createIcons();
      } catch (e) {
        console.warn('Lucide createIcons warning:', e);
      }
    }
  }

  // Initial Icon Render
  refreshIcons();

  // ── Helper: Escape HTML ───────────────────────────────────────────────
  function escapeHtml(text) {
    if (!text) return '';
    return text.toString().replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ── Custom In-App Modal & Toast System (Zero native dialogs) ───────────
  const appDialog = document.getElementById('app-dialog');
  const appDialogBackdrop = document.getElementById('app-dialog-backdrop');
  const appDialogTitle = document.getElementById('app-dialog-title');
  const appDialogBody = document.getElementById('app-dialog-body');
  const appDialogInputContainer = document.getElementById('app-dialog-input-container');
  const appDialogInput = document.getElementById('app-dialog-input');
  const appDialogOk = document.getElementById('app-dialog-ok');
  const appDialogCancel = document.getElementById('app-dialog-cancel');
  const appDialogClose = document.getElementById('app-dialog-close');
  const toastContainer = document.getElementById('toast-container');

  function showToast(message, type = 'info', duration = 3500) {
    if (!toastContainer) return;
    const toast = document.createElement('div');
    toast.className = `toast toast-item toast-${type} ${type}`;
    let iconName = 'info';
    if (type === 'success') iconName = 'check-circle';
    else if (type === 'error') iconName = 'alert-circle';
    else if (type === 'warn') iconName = 'alert-triangle';

    toast.innerHTML = `
      <i data-lucide="${iconName}" class="toast-icon"></i>
      <span class="toast-text">${escapeHtml(message)}</span>
    `;
    toastContainer.appendChild(toast);
    refreshIcons();

    setTimeout(() => {
      toast.classList.add('toast-fade-out');
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  function showDialog({
    title = 'Уведомление',
    message = '',
    isPrompt = false,
    defaultValue = '',
    okText = 'OK',
    cancelText = 'Отмена',
    showCancel = true
  }) {
    return new Promise((resolve) => {
      if (!appDialog) {
        resolve(isPrompt ? defaultValue : true);
        return;
      }

      if (appDialogTitle) appDialogTitle.textContent = title;
      if (appDialogBody) appDialogBody.textContent = message;
      if (appDialogOk) appDialogOk.textContent = okText;
      if (appDialogCancel) {
        appDialogCancel.textContent = cancelText;
        appDialogCancel.style.display = showCancel ? 'inline-flex' : 'none';
      }

      if (isPrompt) {
        if (appDialogInputContainer) appDialogInputContainer.style.display = 'block';
        if (appDialogInput) {
          appDialogInput.value = defaultValue;
          setTimeout(() => {
            appDialogInput.focus();
            appDialogInput.select();
          }, 60);
        }
      } else {
        if (appDialogInputContainer) appDialogInputContainer.style.display = 'none';
        if (appDialogOk) {
          setTimeout(() => appDialogOk.focus(), 60);
        }
      }

      if (appDialogBackdrop) {
        appDialogBackdrop.classList.add('open');
        appDialogBackdrop.style.display = 'block';
      }
      appDialog.classList.add('open');
      appDialog.style.display = 'flex';

      function cleanup() {
        if (appDialogBackdrop) {
          appDialogBackdrop.classList.remove('open');
          appDialogBackdrop.style.display = 'none';
        }
        appDialog.classList.remove('open');
        appDialog.style.display = 'none';
        appDialogOk.removeEventListener('click', onOk);
        if (appDialogCancel) appDialogCancel.removeEventListener('click', onCancel);
        if (appDialogClose) appDialogClose.removeEventListener('click', onCancel);
        if (appDialogBackdrop) appDialogBackdrop.removeEventListener('click', onCancel);
        if (appDialogInput) appDialogInput.removeEventListener('keydown', onKey);
        document.removeEventListener('keydown', onGlobalKey);
      }

      function onOk() {
        const val = appDialogInput ? appDialogInput.value.trim() : '';
        cleanup();
        resolve(isPrompt ? val : true);
      }

      function onCancel() {
        cleanup();
        resolve(isPrompt ? null : false);
      }

      function onKey(e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          onOk();
        } else if (e.key === 'Escape') {
          e.preventDefault();
          onCancel();
        }
      }

      function onGlobalKey(e) {
        if (e.key === 'Escape') {
          e.preventDefault();
          onCancel();
        }
      }

      appDialogOk.addEventListener('click', onOk);
      if (appDialogCancel) appDialogCancel.addEventListener('click', onCancel);
      if (appDialogClose) appDialogClose.addEventListener('click', onCancel);
      if (appDialogBackdrop) appDialogBackdrop.addEventListener('click', onCancel);
      if (appDialogInput && isPrompt) appDialogInput.addEventListener('keydown', onKey);
      document.addEventListener('keydown', onGlobalKey);
    });
  }

  function showCustomAlert(message, title = 'Информация', okText = 'Понятно') {
    return showDialog({ title, message, showCancel: false, okText });
  }

  function showCustomConfirm(message, title = 'Подтверждение', okText = 'Подтвердить', cancelText = 'Отмена') {
    return showDialog({ title, message, showCancel: true, okText, cancelText });
  }

  function showCustomPrompt(message, defaultValue = '', title = 'Ввод данных', okText = 'Сохранить', cancelText = 'Отмена') {
    return showDialog({ title, message, isPrompt: true, defaultValue, showCancel: true, okText, cancelText });
  }

  // ── Elements ──────────────────────────────────────────────────────────
  const sidebarToggleBtn = document.getElementById('sidebar-toggle-btn');
  const sidebarDrawer = document.getElementById('sidebar-drawer');
  const sidebarBackdrop = document.getElementById('sidebar-backdrop');
  const sidebarCloseBtn = document.getElementById('sidebar-close-btn');
  const sidebarProjectsList = document.getElementById('sidebar-projects-list');
  const sidebarNewProjectBtn = document.getElementById('sidebar-new-project-btn');

  const themeToggleBtn = document.getElementById('theme-toggle-btn');
  const diagramTitleInput = document.getElementById('diagram-title-input');
  const newChatBtn = document.getElementById('new-chat-btn');
  const deleteChatBtn = document.getElementById('delete-chat-btn');
  const saveBtn = document.getElementById('save-btn');
  const kbModalBtn = document.getElementById('kb-modal-btn');
  const exportBtn = document.getElementById('export-btn');
  const exportMenu = document.getElementById('export-menu');

  const chatContainer = document.getElementById('chat-messages-container');
  const promptInput = document.getElementById('chat-prompt');
  const generateBtn = document.getElementById('generate-btn');
  const stopBtn = document.getElementById('stop-btn');
  const clearChatBtn = document.getElementById('clear-chat-btn');
  const bulkDeleteBar = document.getElementById('bulk-delete-bar');
  const bulkDeleteCount = document.getElementById('bulk-delete-count');
  const bulkDeleteBtn = document.getElementById('bulk-delete-btn');
  const bulkCancelBtn = document.getElementById('bulk-cancel-btn');
  const attachMdBtn = document.getElementById('attach-md-btn');
  const attachMdInput = document.getElementById('attach-md-input');
  const attachedMdPreview = document.getElementById('attached-md-preview');
  const attachedMdName = document.getElementById('attached-md-name');
  const attachedMdSize = document.getElementById('attached-md-size');
  const removeAttachedMdBtn = document.getElementById('remove-attached-md-btn');
  let attachedMdFile = null;

  const codeEditor = document.getElementById('code-editor');
  const lineNumbers = document.getElementById('code-line-numbers');
  const codeHighlightPre = document.getElementById('code-highlight-pre');
  const codeHighlightCode = document.getElementById('code-highlight-code');
  const codeActiveLineBar = document.getElementById('code-active-line-bar');
  let activeHighlightedLine = 0;

  const importDslBtn = document.getElementById('import-dsl-btn');
  const importDslInput = document.getElementById('import-dsl-input');

  const isAuth = Boolean(window.INITIAL_DATA && window.INITIAL_DATA.isAuthenticated);
  const openAuthBtn = document.getElementById('open-auth-btn');
  const mobileAuthBtn = document.getElementById('mobile-auth-btn');
  const logoutBtn = document.getElementById('logout-btn');
  const mobileLogoutBtn = document.getElementById('mobile-logout-btn');
  const authModal = document.getElementById('auth-modal');
  const authModalClose = document.getElementById('auth-modal-close');

  const errorBar = document.getElementById('code-error-bar');
  const syncPill = document.getElementById('sync-pill');
  const statusBadge = document.getElementById('status-badge');
  const statusBadgeText = document.getElementById('status-badge-text');

  // Modals
  const projectModal = document.getElementById('project-modal');
  const projectForm = document.getElementById('project-form');
  const modalCancelProject = document.getElementById('modal-cancel-project');
  const kbModal = document.getElementById('kb-modal');
  const kbModalClose = document.getElementById('kb-modal-close');
  const kbFilesList = document.getElementById('kb-files-list');
  const kbFileEditor = document.getElementById('kb-file-editor');
  const kbCurrentFileName = document.getElementById('kb-current-file-name');
  const kbSaveFileBtn = document.getElementById('kb-save-file-btn');
  const kbNewFileBtn = document.getElementById('kb-new-file-btn');
  const kbUploadInput = document.getElementById('kb-upload-input');
  const kbUploadZone = document.getElementById('kb-upload-zone');

  // Unified Panel & Resizer
  const resizer = document.getElementById('resizer-main');
  const panelUnified = document.getElementById('panel-unified');

  // Mobile Switcher & Actions
  const mobileBtnPanel = document.querySelector('.mobile-toggle-btn[data-view="panel"]') || document.getElementById('mobile-btn-panel');
  const mobileBtnCanvas = document.querySelector('.mobile-toggle-btn[data-view="canvas"]') || document.getElementById('mobile-btn-canvas');
  const mobileMoreBtn = document.getElementById('mobile-more-btn');
  const mobileMoreMenu = document.getElementById('mobile-more-menu');
  const mobileKbBtn = document.getElementById('mobile-kb-btn');
  const mobileThemeBtn = document.getElementById('mobile-theme-btn');
  const mobileDeleteChatBtn = document.getElementById('mobile-delete-chat-btn');

  // ── Modeler Setup ─────────────────────────────────────────────────────
  let modeler = null;
  if (typeof BpmnJS !== 'undefined') {
    modeler = new BpmnJS({
      container: '#bpmn-canvas',
      keyboard: { bindTo: document }
    });
    initBpmnCanvasTouchHandler(modeler);
    initCanvasSelectionTracking(modeler);
  } else {
    console.error('BpmnJS library is not loaded');
  }

  function initCanvasSelectionTracking(modelerInstance) {
    if (!modelerInstance) return;
    modelerInstance.on('selection.changed', (e) => {
      if (e.newSelection && e.newSelection.length > 0) {
        const sel = e.newSelection[0];
        if (sel.id && sel.type !== 'bpmn:Process' && sel.type !== 'bpmn:Collaboration') {
          onCanvasElementSelected(sel.id);
        }
      } else {
        highlightTraceInChat(null);
      }
    });

    modelerInstance.on('element.click', (e) => {
      if (e.element && e.element.id && e.element.type !== 'bpmn:Process' && e.element.type !== 'bpmn:Collaboration') {
        onCanvasElementSelected(e.element.id);
      }
    });
  }

  // ── Touch & Gesture Handler for BPMN Canvas (Mobile & Tablets) ─────────
  function initBpmnCanvasTouchHandler(modelerInstance) {
    const canvasEl = document.getElementById('bpmn-canvas');
    if (!canvasEl || !modelerInstance) return;

    let isTouching = false;
    let touchStartPoint = null;
    let lastTouchPoint = null;
    let initialPinchDist = null;
    let initialZoom = 1;
    let activeElementGfx = null;
    let hasMoved = false;

    canvasEl.addEventListener('touchstart', (e) => {
      // Allow native taps on UI controls, palette, context-pad, and floating zoom buttons
      if (e.target.closest('.djs-palette, .djs-context-pad, .canvas-floating-controls, .djs-popup')) {
        return;
      }

      if (e.touches.length === 2) {
        // 2 fingers: pinch to zoom
        isTouching = true;
        hasMoved = true;
        activeElementGfx = null;
        const t1 = e.touches[0];
        const t2 = e.touches[1];
        initialPinchDist = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);
        try {
          initialZoom = modelerInstance.get('canvas').zoom();
        } catch (err) {
          initialZoom = 1;
        }
        e.preventDefault();
        return;
      }

      if (e.touches.length === 1) {
        const touch = e.touches[0];
        touchStartPoint = { x: touch.clientX, y: touch.clientY };
        lastTouchPoint = { x: touch.clientX, y: touch.clientY };
        isTouching = true;
        hasMoved = false;

        // Check if touch started on a movable diagram shape/element
        const hitTarget = document.elementFromPoint(touch.clientX, touch.clientY);
        const shapeElement = hitTarget ? hitTarget.closest('.djs-element:not(.djs-shape[data-element-id^="Process_"]):not([data-element-id^="Collaboration_"])') : null;

        if (shapeElement && !hitTarget.closest('.djs-palette, .djs-context-pad')) {
          activeElementGfx = shapeElement;
          const mouseEv = new MouseEvent('mousedown', {
            bubbles: true,
            cancelable: true,
            view: window,
            clientX: touch.clientX,
            clientY: touch.clientY,
            screenX: touch.screenX,
            screenY: touch.screenY,
            button: 0,
            buttons: 1
          });
          (hitTarget || shapeElement).dispatchEvent(mouseEv);
        } else {
          activeElementGfx = null;
        }

        e.preventDefault();
      }
    }, { passive: false });

    document.addEventListener('touchmove', (e) => {
      if (!isTouching) return;

      if (e.touches.length === 2 && initialPinchDist) {
        const t1 = e.touches[0];
        const t2 = e.touches[1];
        const currentDist = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);
        if (initialPinchDist > 0 && currentDist > 0) {
          const factor = currentDist / initialPinchDist;
          const midX = (t1.clientX + t2.clientX) / 2;
          const midY = (t1.clientY + t2.clientY) / 2;
          const rect = canvasEl.getBoundingClientRect();
          try {
            modelerInstance.get('canvas').zoom(initialZoom * factor, {
              x: midX - rect.left,
              y: midY - rect.top
            });
          } catch (err) { }
        }
        e.preventDefault();
        return;
      }

      if (e.touches.length === 1) {
        const touch = e.touches[0];
        const dx = touch.clientX - lastTouchPoint.x;
        const dy = touch.clientY - lastTouchPoint.y;
        lastTouchPoint = { x: touch.clientX, y: touch.clientY };

        const distFromStart = Math.hypot(touch.clientX - touchStartPoint.x, touch.clientY - touchStartPoint.y);
        if (distFromStart > 5) {
          hasMoved = true;
        }

        if (activeElementGfx) {
          // Dragging shape via bpmn-js mouse event forwarding
          const mouseEv = new MouseEvent('mousemove', {
            bubbles: true,
            cancelable: true,
            view: window,
            clientX: touch.clientX,
            clientY: touch.clientY,
            screenX: touch.screenX,
            screenY: touch.screenY,
            button: 0,
            buttons: 1
          });
          document.dispatchEvent(mouseEv);
        } else {
          // Direct smooth panning of canvas
          try {
            modelerInstance.get('canvas').scroll({ dx, dy });
          } catch (err) { }
        }

        e.preventDefault();
      }
    }, { passive: false });

    function handleTouchEnd(e) {
      if (!isTouching) return;

      if (e.touches.length === 0) {
        isTouching = false;
        initialPinchDist = null;

        if (activeElementGfx) {
          const changedTouch = e.changedTouches && e.changedTouches[0];
          const mouseEv = new MouseEvent('mouseup', {
            bubbles: true,
            cancelable: true,
            view: window,
            clientX: changedTouch ? changedTouch.clientX : (lastTouchPoint ? lastTouchPoint.x : 0),
            clientY: changedTouch ? changedTouch.clientY : (lastTouchPoint ? lastTouchPoint.y : 0),
            button: 0,
            buttons: 0
          });
          document.dispatchEvent(mouseEv);
          activeElementGfx = null;
        }

        // Tap selection if finger didn't move
        if (!hasMoved && touchStartPoint) {
          const hitTarget = document.elementFromPoint(touchStartPoint.x, touchStartPoint.y);
          if (hitTarget && !hitTarget.closest('.djs-palette, .djs-context-pad, .canvas-floating-controls')) {
            const clickEv = new MouseEvent('click', {
              bubbles: true,
              cancelable: true,
              view: window,
              clientX: touchStartPoint.x,
              clientY: touchStartPoint.y
            });
            hitTarget.dispatchEvent(clickEv);
          }
        }

        touchStartPoint = null;
        lastTouchPoint = null;
      } else if (e.touches.length === 1) {
        const touch = e.touches[0];
        lastTouchPoint = { x: touch.clientX, y: touch.clientY };
        initialPinchDist = null;
      }
    }

    document.addEventListener('touchend', handleTouchEnd, { passive: false });
    document.addEventListener('touchcancel', handleTouchEnd, { passive: false });
  }

  // ── Syntax Highlighting Synchronizers ──────────────────────────────────
  function updateDslHighlight() {
    if (!codeEditor || !codeHighlightCode || !window.Prism) return;
    const text = codeEditor.value;
    codeHighlightCode.textContent = text + (text.endsWith('\n') ? ' ' : '');
    Prism.highlightElement(codeHighlightCode);
  }

  function updateXmlViewer(xml) {
    // BPMN XML tab removed from UI; no-op
  }

  function safeFitViewport() {
    if (!modeler) return;
    try {
      const container = document.getElementById('bpmn-canvas');
      if (container && container.offsetWidth > 20 && container.offsetHeight > 20) {
        const canvas = modeler.get('canvas');
        canvas.resized();
        canvas.zoom('fit-viewport');
      }
    } catch (e) {
      console.warn('zoom fit-viewport skipped:', e);
    }
  }

  async function loadIntoModeler(xml) {
    if (!modeler || !xml || !xml.trim()) return;
    isImporting = true;
    try {
      await modeler.importXML(xml);
      safeFitViewport();
      updateXmlViewer(xml);
      hideError();
      updateStatusBadge('ok', 'Диаграмма готова');
    } catch (err) {
      console.error('BPMN-js import error:', err);
      showError('Ошибка отображения BPMN 2.0 XML: ' + (err.message || err));
      updateStatusBadge('err', 'Ошибка рендеринга');
    } finally {
      isImporting = false;
    }
  }

  // ── XML -> DSL Decompiler (Visual to Code) ─────────────────────────────
  const TASK_TAGS = new Set([
    'task', 'userTask', 'serviceTask', 'manualTask',
    'scriptTask', 'businessRuleTask', 'sendTask', 'receiveTask'
  ]);
  const TASK_TYPE_MAP = {
    userTask: 'user', serviceTask: 'service', scriptTask: 'script',
    sendTask: 'send', receiveTask: 'receive', manualTask: 'manual',
    businessRuleTask: 'businessrule'
  };

  function detectEventType(el) {
    const defs = {
      messageEventDefinition: 'message', timerEventDefinition: 'timer',
      signalEventDefinition: 'signal', errorEventDefinition: 'error',
      terminateEventDefinition: 'terminate', escalationEventDefinition: 'escalation',
      compensateEventDefinition: 'compensate', conditionalEventDefinition: 'conditional',
      linkEventDefinition: 'link'
    };
    for (const [tag, kw] of Object.entries(defs)) {
      if (el.getElementsByTagNameNS('*', tag).length > 0 ||
        Array.from(el.children).some(c => (c.localName || c.tagName).includes(tag))) {
        return ' ' + kw;
      }
    }
    return '';
  }

  function detectLoopType(el) {
    if (el.getElementsByTagNameNS('*', 'standardLoopCharacteristics').length > 0 ||
      Array.from(el.children).some(c => (c.localName || c.tagName).includes('standardLoopCharacteristics'))) {
      return ' loop';
    }
    const multi = el.getElementsByTagNameNS('*', 'multiInstanceLoopCharacteristics')[0] ||
      Array.from(el.children).find(c => (c.localName || c.tagName).includes('multiInstanceLoopCharacteristics'));
    if (multi) {
      const isSeq = multi.getAttribute('isSequential') === 'true';
      return isSeq ? ' loop sequential' : ' loop parallel';
    }
    return '';
  }

  function decompileXml(xml) {
    try {
      const doc = new DOMParser().parseFromString(xml, 'application/xml');
      const proc = doc.getElementsByTagNameNS('*', 'process')[0] ||
        doc.querySelector('process') ||
        doc.querySelector('bpmn\\:process') ||
        doc.querySelector('bpmn2\\:process');
      if (!proc) return '# Не удалось распарсить BPMN процесс\n';

      const processName = proc.getAttribute('name') || 'Бизнес-процесс';
      const procId = proc.getAttribute('id') || 'Process_1';

      // 1. Collaboration, Pools & Message Flows
      const poolLines = [];
      const messageFlowLines = [];
      let mainPoolId = '';
      const collabs = doc.getElementsByTagNameNS('*', 'collaboration');
      for (let c = 0; c < collabs.length; c++) {
        const collab = collabs[c];
        const participants = collab.getElementsByTagNameNS('*', 'participant');
        for (let i = 0; i < participants.length; i++) {
          const p = participants[i];
          const pid = p.getAttribute('id');
          if (!pid) continue;
          const pname = (p.getAttribute('name') || pid).replace(/[\n\r]+/g, ' ').trim();
          const pRef = p.getAttribute('processRef');
          if (pRef === procId || (!mainPoolId && pRef)) mainPoolId = pid;
          poolLines.push(`pool: ${pid} "${pname}"`);
        }

        const msgFlows = collab.getElementsByTagNameNS('*', 'messageFlow');
        for (let i = 0; i < msgFlows.length; i++) {
          const mf = msgFlows[i];
          const mSource = mf.getAttribute('sourceRef');
          const mTarget = mf.getAttribute('targetRef');
          const mName = (mf.getAttribute('name') || '').replace(/[\n\r]+/g, ' ').trim();
          if (mSource && mTarget) {
            if (mName) {
              messageFlowLines.push(`${mSource} ~> ${mTarget} "${mName}"`);
            } else {
              messageFlowLines.push(`${mSource} ~> ${mTarget}`);
            }
          }
        }
      }

      // 2. LaneSets & Lanes
      const laneLines = [];
      const nodeToLane = new Map();
      const laneSets = proc.getElementsByTagNameNS('*', 'laneSet');
      for (let s = 0; s < laneSets.length; s++) {
        const lanes = laneSets[s].getElementsByTagNameNS('*', 'lane');
        for (let i = 0; i < lanes.length; i++) {
          const l = lanes[i];
          const lid = l.getAttribute('id');
          if (!lid) continue;
          const lname = (l.getAttribute('name') || lid).replace(/[\n\r]+/g, ' ').trim();
          const poolRef = mainPoolId ? ` in ${mainPoolId}` : '';
          laneLines.push(`lane: ${lid} "${lname}"${poolRef}`);

          const refs = l.getElementsByTagNameNS('*', 'flowNodeRef');
          for (let r = 0; r < refs.length; r++) {
            const refId = (refs[r].textContent || '').trim();
            if (refId) nodeToLane.set(refId, lid);
          }
        }
      }

      // 3. Process elements & default flow mapping
      const defaultFlowIds = new Set();
      for (const el of proc.children) {
        const def = el.getAttribute('default');
        if (def) defaultFlowIds.add(def);
      }

      const buckets = {
        start: [], end: [], catch_throw: [], boundary: [],
        task: [], gateway: [], subprocess: [], call: []
      };
      const flowLines = [];
      const knownIds = new Set();

      for (const el of proc.children) {
        const tag = el.localName || el.tagName.split(':').pop();
        const id = el.getAttribute('id');
        if (!id) continue;
        const name = (el.getAttribute('name') || id).replace(/[\n\r]+/g, ' ').trim();
        const laneMod = nodeToLane.has(id) ? ` in ${nodeToLane.get(id)}` : '';
        const loopMod = detectLoopType(el);

        if (tag === 'startEvent') {
          buckets.start.push(`start: ${id} "${name}"${detectEventType(el)}${laneMod}`);
          knownIds.add(id);
        } else if (tag === 'endEvent') {
          buckets.end.push(`end: ${id} "${name}"${detectEventType(el)}${laneMod}`);
          knownIds.add(id);
        } else if (tag === 'intermediateCatchEvent') {
          buckets.catch_throw.push(`catch: ${id} "${name}"${detectEventType(el)}${laneMod}`);
          knownIds.add(id);
        } else if (tag === 'intermediateThrowEvent') {
          buckets.catch_throw.push(`throw: ${id} "${name}"${detectEventType(el)}${laneMod}`);
          knownIds.add(id);
        } else if (tag === 'boundaryEvent') {
          const attachedTo = el.getAttribute('attachedToRef') || '';
          const nonInt = el.getAttribute('cancelActivity') === 'false' ? ' non-interrupting' : '';
          buckets.boundary.push(`boundary: ${id} on ${attachedTo} "${name}"${detectEventType(el)}${nonInt}`);
          knownIds.add(id);
        } else if (TASK_TAGS.has(tag)) {
          const taskType = TASK_TYPE_MAP[tag] ? ` ${TASK_TYPE_MAP[tag]}` : '';
          const docEls = el.getElementsByTagNameNS('*', 'documentation');
          const perf = docEls.length > 0 ? (docEls[0].textContent || '').trim() : '';
          const byMod = (perf && !nodeToLane.has(id)) ? ` by "${perf}"` : '';
          buckets.task.push(`task: ${id} "${name}"${taskType}${loopMod}${byMod}${laneMod}`);
          knownIds.add(id);
        } else if (tag === 'exclusiveGateway') {
          buckets.gateway.push(`gateway: ${id} "${name}" exclusive${laneMod}`);
          knownIds.add(id);
        } else if (tag === 'parallelGateway') {
          buckets.gateway.push(`gateway: ${id} "${name}" parallel${laneMod}`);
          knownIds.add(id);
        } else if (tag === 'inclusiveGateway') {
          buckets.gateway.push(`gateway: ${id} "${name}" inclusive${laneMod}`);
          knownIds.add(id);
        } else if (tag === 'eventBasedGateway') {
          buckets.gateway.push(`gateway: ${id} "${name}" event-based${laneMod}`);
          knownIds.add(id);
        } else if (tag === 'subProcess') {
          buckets.subprocess.push(`subprocess: ${id} "${name}"${loopMod}${laneMod}`);
          knownIds.add(id);
        } else if (tag === 'callActivity') {
          buckets.call.push(`call: ${id} "${name}"${laneMod}`);
          knownIds.add(id);
        } else if (tag === 'sequenceFlow') {
          const source = el.getAttribute('sourceRef');
          const target = el.getAttribute('targetRef');
          const flowId = el.getAttribute('id');
          const isDefault = flowId && defaultFlowIds.has(flowId);

          let flowName = el.getAttribute('name');
          if (!flowName) {
            const condEls = el.getElementsByTagNameNS('*', 'conditionExpression');
            if (condEls.length > 0 && condEls[0].textContent) {
              flowName = condEls[0].textContent.trim();
            }
          }
          if (source && target) {
            if (isDefault) {
              flowLines.push(`${source} ==> ${target}`);
            } else if (flowName && flowName.trim()) {
              flowLines.push(`${source} --[${flowName.trim()}]--> ${target}`);
            } else {
              flowLines.push(`${source} -> ${target}`);
            }
          }
        }
      }

      let dsl = `process "${processName}"\n\n`;
      const addSection = (title, items) => {
        if (items.length > 0) {
          dsl += `# ${title}\n` + items.join('\n') + '\n\n';
        }
      };

      if (poolLines.length > 0 || laneLines.length > 0) {
        addSection('Пулы и дорожки', [...poolLines, ...laneLines]);
      }
      addSection('События', [...buckets.start, ...buckets.catch_throw, ...buckets.boundary, ...buckets.end]);
      addSection('Задачи', buckets.task);
      addSection('Шлюзы', buckets.gateway);
      addSection('Подпроцессы', [...buckets.subprocess, ...buckets.call]);
      addSection('Потоки управления', flowLines);
      if (messageFlowLines.length > 0) {
        addSection('Потоки сообщений', messageFlowLines);
      }

      return dsl.trim() + '\n';
    } catch (e) {
      console.error('Decompile error:', e);
      return null;
    }
  }

  // ── Modeler Change Listener (Visual -> DSL Sync) ──────────────────────
  if (modeler) {
    const onCanvasChange = () => {
      if (isImporting) return;
      lastSourceOfChange = 'visual';
      clearTimeout(visualSyncTimer);
      visualSyncTimer = setTimeout(async () => {
        try {
          const { xml } = await modeler.saveXML({ format: true });
          updateXmlViewer(xml);

          const newDsl = decompileXml(xml);
          if (newDsl && newDsl !== lastVisualDsl && (!codeEditor || newDsl !== codeEditor.value)) {
            codeFromVisual = true;
            lastVisualDsl = newDsl;
            if (codeEditor) {
              codeEditor.value = newDsl;
              updateLineNumbers();
              updateDslHighlight();
            }
            updateTraceability();
            showSyncPill();
            setTimeout(() => { codeFromVisual = false; }, 300);
          }
        } catch (e) {
          console.warn('Visual sync error:', e);
        }
      }, 350);
    };

    modeler.on('commandStack.changed', onCanvasChange);
    modeler.on('elements.changed', onCanvasChange);
  }

  function showSyncPill() {
    if (!syncPill) return;
    syncPill.style.display = 'inline-flex';
    clearTimeout(syncPill._timer);
    syncPill._timer = setTimeout(() => {
      syncPill.style.display = 'none';
    }, 2200);
  }

  // ── DSL Compiler (Code -> Visual Sync) ─────────────────────────────────
  function compileCode() {
    const code = codeEditor ? codeEditor.value : '';
    if (!code.trim()) {
      hideError();
      return { valid: true };
    }

    try {
      if (typeof BpmnAsCode === 'undefined' || !BpmnAsCode.compile) {
        throw new Error('Модуль компилятора BpmnAsCode не загружен');
      }

      const result = BpmnAsCode.compile(code);
      if (result && (result.valid || (result.xml && !result.error))) {
        hideError();
        loadIntoModeler(result.xml);
        updateTraceability();
        return { valid: true, xml: result.xml };
      } else {
        const lineStr = (result && result.line) ? `[Строка ${result.line}] ` : '';
        const msg = lineStr + (result && result.error ? result.error : 'Синтаксическая ошибка в DSL');
        showError(msg);
        updateStatusBadge('err', 'Ошибка синтаксиса DSL');
        return { valid: false, error: msg, line: result?.line };
      }
    } catch (err) {
      showError(err.message || 'Ошибка компиляции');
      updateStatusBadge('err', 'Ошибка компиляции');
      return { valid: false, error: err.message };
    }
  }

  function showError(msg) {
    if (!errorBar) return;
    errorBar.textContent = msg;
    errorBar.style.display = 'block';
  }

  function hideError() {
    if (!errorBar) return;
    errorBar.textContent = '';
    errorBar.style.display = 'none';
  }

  function updateStatusBadge(type, text) {
    if (!statusBadge || !statusBadgeText) return;
    statusBadge.className = `status-badge ${type}`;
    statusBadgeText.textContent = text;
  }

  // ── Code Editor Line Numbers, Syntax & Events ──────────────────────────
  function updateLineNumbers() {
    if (!codeEditor || !lineNumbers) return;
    const lines = codeEditor.value.split('\n').length;
    lineNumbers.innerHTML = Array.from({ length: lines }, (_, i) => {
      const lineNum = i + 1;
      const isActive = lineNum === activeHighlightedLine ? ' active' : '';
      return `<span class="line-num${isActive}" data-line="${lineNum}">${lineNum}</span>`;
    }).join('');
    const linesBadge = document.getElementById('dsl-lines-count');
    if (linesBadge) linesBadge.textContent = `${lines} стр.`;
  }

  const codeFullscreenBtn = document.getElementById('code-fullscreen-btn');
  const codeFullscreenExitBtn = document.getElementById('code-fullscreen-exit-btn');
  const codeFullscreenLabel = document.getElementById('code-fullscreen-label');
  const tabDsl = document.getElementById('tab-dsl');

  function setDslFullscreen(enable) {
    if (!tabDsl) return;
    const isFull = (typeof enable === 'boolean') ? enable : !tabDsl.classList.contains('fullscreen');
    tabDsl.classList.toggle('fullscreen', isFull);
    document.body.classList.toggle('code-fullscreen-active', isFull);

    if (codeFullscreenBtn) {
      codeFullscreenBtn.innerHTML = isFull
        ? '<i data-lucide="minimize-2" class="icon-sm"></i><span id="code-fullscreen-label">Свернуть</span>'
        : '<i data-lucide="maximize-2" class="icon-sm"></i><span id="code-fullscreen-label">Во весь экран</span>';
      codeFullscreenBtn.title = isFull ? 'Свернуть обратно в панель' : 'Развернуть на весь экран';
      codeFullscreenBtn.classList.toggle('active', isFull);
    }

    refreshIcons();
    setTimeout(() => {
      updateLineNumbers();
      updateDslHighlight();
      if (codeEditor) codeEditor.focus();
    }, 50);
  }

  if (codeFullscreenBtn) {
    codeFullscreenBtn.addEventListener('click', () => setDslFullscreen());
  }
  if (codeFullscreenExitBtn) {
    codeFullscreenExitBtn.addEventListener('click', () => setDslFullscreen(false));
  }
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && tabDsl && tabDsl.classList.contains('fullscreen')) {
      setDslFullscreen(false);
    }
  });

  if (codeEditor) {
    codeEditor.addEventListener('input', () => {
      updateLineNumbers();
      updateDslHighlight();
      if (codeFromVisual) return;
      lastSourceOfChange = 'code';
      clearTimeout(compileTimer);
      compileTimer = setTimeout(compileCode, 400);
    });

    codeEditor.addEventListener('scroll', () => {
      if (lineNumbers) lineNumbers.scrollTop = codeEditor.scrollTop;
      if (codeHighlightPre) {
        codeHighlightPre.scrollTop = codeEditor.scrollTop;
        codeHighlightPre.scrollLeft = codeEditor.scrollLeft;
      }
      updateActiveLineBarPosition();
    });

    codeEditor.addEventListener('keydown', (e) => {
      if (e.key === 'Tab') {
        e.preventDefault();
        const start = codeEditor.selectionStart;
        const end = codeEditor.selectionEnd;
        codeEditor.value = codeEditor.value.slice(0, start) + '  ' + codeEditor.value.slice(end);
        codeEditor.selectionStart = codeEditor.selectionEnd = start + 2;
        updateLineNumbers();
        updateDslHighlight();
        codeEditor.dispatchEvent(new Event('input'));
      }
    });

    codeEditor.addEventListener('click', onEditorCursorChange);
    codeEditor.addEventListener('keyup', (e) => {
      if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'PageUp', 'PageDown'].includes(e.key)) {
        onEditorCursorChange();
      }
    });
  }

  // ── Unified Tabs Navigation (Chat / DSL / XML) ────────────────────────
  function switchUnifiedTab(tabId) {
    document.querySelectorAll('.unified-tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.unified-tab-content').forEach(p => p.classList.remove('active'));

    const btn = document.querySelector(`.unified-tab-btn[data-tab="${tabId}"]`);
    const content = document.getElementById(tabId);
    if (btn) btn.classList.add('active');
    if (content) content.classList.add('active');

    if (tabId === 'tab-dsl') {
      if (lastSourceOfChange === 'visual' && modeler && !isImporting) {
        clearTimeout(visualSyncTimer);
        modeler.saveXML({ format: true }).then(({ xml }) => {
          updateXmlViewer(xml);
          const newDsl = decompileXml(xml);
          if (newDsl && newDsl !== lastVisualDsl && (!codeEditor || newDsl !== codeEditor.value)) {
            codeFromVisual = true;
            lastVisualDsl = newDsl;
            if (codeEditor) {
              codeEditor.value = newDsl;
              updateLineNumbers();
              updateDslHighlight();
            }
            updateTraceability();
            showSyncPill();
            setTimeout(() => { codeFromVisual = false; }, 300);
          }
        }).catch(err => console.warn('Tab switch visual sync error:', err));
      }
      updateLineNumbers();
      updateDslHighlight();
      if (activeTraceElementId) {
        highlightTraceInEditor(activeTraceElementId);
      }
    } else if (tabId === 'tab-chat') {
      if (activeTraceElementId) {
        highlightTraceInChat(activeTraceElementId);
      }
    }
  }

  document.querySelectorAll('.unified-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      switchUnifiedTab(btn.dataset.tab);
    });
  });

  // ── Zoom Controls ──────────────────────────────────────────────────────
  const zoomFitBtn = document.getElementById('zoom-fit');
  const zoomInBtn = document.getElementById('zoom-in');
  const zoomOutBtn = document.getElementById('zoom-out');

  if (zoomFitBtn) {
    zoomFitBtn.addEventListener('click', () => {
      safeFitViewport();
    });
  }
  if (zoomInBtn) {
    zoomInBtn.addEventListener('click', () => {
      if (modeler) {
        const c = modeler.get('canvas');
        c.zoom(c.zoom() * 1.25);
      }
    });
  }
  if (zoomOutBtn) {
    zoomOutBtn.addEventListener('click', () => {
      if (modeler) {
        const c = modeler.get('canvas');
        c.zoom(c.zoom() / 1.25);
      }
    });
  }

  // ── Resizer ────────────────────────────────────────────────────────────
  if (resizer && panelUnified) {
    let isResizing = false;
    let startX, startW;

    resizer.addEventListener('mousedown', (e) => {
      isResizing = true;
      startX = e.clientX;
      startW = panelUnified.offsetWidth;
      resizer.classList.add('resizing');
      document.body.style.userSelect = 'none';
      document.body.style.cursor = 'col-resize';
    });

    document.addEventListener('mousemove', (e) => {
      if (!isResizing) return;
      const dx = e.clientX - startX;
      panelUnified.style.width = Math.max(340, Math.min(startW + dx, window.innerWidth - 350)) + 'px';
    });

    document.addEventListener('mouseup', () => {
      if (!isResizing) return;
      isResizing = false;
      resizer.classList.remove('resizing');
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
      if (modeler) {
        setTimeout(() => {
          try {
            modeler.get('canvas').resized();
          } catch (e) { }
        }, 80);
      }
    });
  }

  window.addEventListener('resize', () => {
    if (modeler) {
      try {
        modeler.get('canvas').resized();
      } catch (e) { }
    }
  });

  // ── Template Chips ─────────────────────────────────────────────────────
  document.querySelectorAll('.template-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      if (promptInput) {
        promptInput.value = chip.dataset.prompt;
        promptInput.focus();
      }
    });
  });

  // ── Generation & Abort ─────────────────────────────────────────────────
  function setGeneratingState(generating) {
    isGenerating = generating;
    if (generateBtn) generateBtn.style.display = generating ? 'none' : 'inline-flex';
    if (stopBtn) stopBtn.style.display = generating ? 'inline-flex' : 'none';
    if (promptInput) promptInput.disabled = generating;

    if (generating) {
      showGeneratingIndicator();
    } else {
      hideGeneratingIndicator();
    }
  }

  // ── Markdown File Attachment Handlers ────────────────────────────────
  function formatFileSize(bytes) {
    if (!bytes || bytes === 0) return '0 Б';
    if (bytes < 1024) return bytes + ' Б';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' КБ';
    return (bytes / (1024 * 1024)).toFixed(1) + ' МБ';
  }

  function setAttachedMdFile(file) {
    if (!file) {
      attachedMdFile = null;
      if (attachedMdPreview) attachedMdPreview.style.display = 'none';
      if (attachMdBtn) {
        attachMdBtn.classList.remove('has-file');
        const lbl = attachMdBtn.querySelector('.attach-btn-label');
        if (lbl) lbl.textContent = 'Прикрепить файл';
      }
      if (attachMdInput) attachMdInput.value = '';
      return;
    }

    const name = file.name || '';
    const ext = name.toLowerCase().split('.').pop();
    const allowedExts = ['md', 'markdown', 'txt', 'docx', 'pdf'];
    if (!allowedExts.includes(ext)) {
      showToast('Разрешены форматы: .md, .txt, .docx, .pdf', 'warn');
      if (attachMdInput) attachMdInput.value = '';
      return;
    }

    const MAX_SIZE = 10 * 1024 * 1024;
    if (file.size > MAX_SIZE) {
      showToast('Размер файла превышает 10 МБ', 'warn');
      if (attachMdInput) attachMdInput.value = '';
      return;
    }

    attachedMdFile = file;
    if (attachedMdName) attachedMdName.textContent = name;
    if (attachedMdSize) attachedMdSize.textContent = formatFileSize(file.size);
    if (attachedMdPreview) attachedMdPreview.style.display = 'flex';
    if (attachMdBtn) {
      attachMdBtn.classList.add('has-file');
      const lbl = attachMdBtn.querySelector('.attach-btn-label');
      if (lbl) lbl.textContent = 'Заменить файл';
    }
    refreshIcons();
  }

  if (attachMdBtn && attachMdInput) {
    attachMdBtn.addEventListener('click', () => {
      attachMdInput.click();
    });

    attachMdInput.addEventListener('change', () => {
      if (attachMdInput.files && attachMdInput.files.length > 0) {
        setAttachedMdFile(attachMdInput.files[0]);
      }
    });
  }

  if (removeAttachedMdBtn) {
    removeAttachedMdBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      setAttachedMdFile(null);
    });
  }

  if (generateBtn) {
    generateBtn.addEventListener('click', async () => {
      const prompt = promptInput ? promptInput.value.trim() : '';
      if (!prompt && !attachedMdFile) {
        showToast('Введите описание процесса или прикрепите .md файл', 'warn');
        return;
      }

      // 1. Immediately flush pending changes according to last source of edit
      let currentDsl = codeEditor ? codeEditor.value.trim() : '';
      if (lastSourceOfChange === 'visual' && modeler) {
        clearTimeout(visualSyncTimer);
        try {
          const { xml } = await modeler.saveXML({ format: true });
          updateXmlViewer(xml);
          const decompiled = decompileXml(xml);
          if (decompiled && decompiled.trim()) {
            currentDsl = decompiled.trim();
            if (codeEditor) {
              codeEditor.value = decompiled;
              updateLineNumbers();
              updateDslHighlight();
            }
          }
        } catch (err) {
          console.warn('Pre-generate visual sync warning:', err);
        }
      } else if (lastSourceOfChange === 'code') {
        clearTimeout(compileTimer);
        compileCode();
        currentDsl = codeEditor ? codeEditor.value.trim() : '';
      }

      // 2. Switch to Chat tab
      switchUnifiedTab('tab-chat');

      // 3. User message representation for chat bubble
      const currentAttachedFile = attachedMdFile;
      let bubbleText = prompt;
      if (currentAttachedFile) {
        const fileChipMd = `\n\n📎 *Прикреплен файл:* \`${escapeHtml(currentAttachedFile.name)}\` (${formatFileSize(currentAttachedFile.size)})`;
        bubbleText = (prompt ? prompt : 'Построй процесс на основе прикрепленного документа') + fileChipMd;
      }
      lastUserPromptText = prompt || bubbleText;

      const userBubble = appendChatMessage({
        role: 'user',
        content: bubbleText,
        created_at: new Date().toLocaleTimeString()
      });
      if (userBubble) {
        userBubble.dataset.rawContent = bubbleText;
      }
      if (promptInput) promptInput.value = '';

      // Reset attached file state
      setAttachedMdFile(null);

      // 4. Set generating state (bubble appears strictly below user message)
      setGeneratingState(true);
      abortController = new AbortController();

      const isRefinement = !!currentDsl;
      const endpoint = isRefinement ? '/api/refine/' : '/api/generate/';

      try {
        let resp;
        if (currentAttachedFile) {
          const formData = new FormData();
          formData.append('attached_file', currentAttachedFile);
          if (isRefinement) {
            formData.append('diagram_id', String(currentDiagramId));
            formData.append('instruction', prompt);
            formData.append('current_dsl', currentDsl);
          } else {
            formData.append('project_id', String(currentProjectId));
            formData.append('diagram_id', String(currentDiagramId));
            formData.append('prompt', prompt);
            formData.append('current_dsl', currentDsl);
          }
          resp = await fetch(endpoint, {
            method: 'POST',
            body: formData,
            signal: abortController.signal
          });
        } else {
          const payload = isRefinement
            ? { diagram_id: currentDiagramId, instruction: prompt, current_dsl: currentDsl }
            : { project_id: currentProjectId, diagram_id: currentDiagramId, prompt: prompt, current_dsl: currentDsl };
          resp = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            signal: abortController.signal
          });
        }

        const res = await resp.json();
        if (res.user_message && userBubble) {
          updateBubbleId(userBubble, res.user_message.id);
        }

        if (!res.success) {
          const assistantMsg = res.assistant_message || {
            role: 'assistant',
            content: 'Ошибка: ' + (res.error || 'Неизвестная ошибка'),
            is_error: true,
            created_at: new Date().toLocaleTimeString()
          };
          appendChatMessage(assistantMsg);
          showError(res.error || 'Ошибка генерации');
          updateStatusBadge('err', 'Сбой анализа');
        } else {
          appendChatMessage(res.assistant_message);
          if (res.traceability) {
            updateTraceability(res.traceability);
          } else {
            updateTraceability();
          }
          if (res.has_dsl && res.dsl_code && codeEditor) {
            codeEditor.value = res.dsl_code;
            updateLineNumbers();
            updateDslHighlight();
            lastSourceOfChange = 'ai';
            const compileRes = compileCode();
            if (compileRes && !compileRes.valid) {
              await requestCorrection(compileRes.error, res.dsl_code, 1);
            }
          }
        }
      } catch (err) {
        if (err.name === 'AbortError') {
          appendChatMessage({
            role: 'assistant',
            content: 'Генерация была остановлена пользователем.',
            created_at: new Date().toLocaleTimeString()
          });
        } else {
          appendChatMessage({
            role: 'assistant',
            content: 'Сбой соединения при генерации: ' + err.message,
            is_error: true,
            created_at: new Date().toLocaleTimeString()
          });
        }
      } finally {
        setGeneratingState(false);
      }
    });
  }

  if (stopBtn) {
    stopBtn.addEventListener('click', () => {
      if (abortController) abortController.abort();
      setGeneratingState(false);
      showToast('Генерация прервана', 'info');
    });
  }

  if (promptInput) {
    promptInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (generateBtn) generateBtn.click();
      }
    });
  }

  // ── Validation Report & Proactive Questions Cards ──────────────────────
  function formatValidationReportCard(reportText) {
    const lines = reportText.split('\n').map(l => l.trim()).filter(l => l.startsWith('-') || l.startsWith('*'));
    const listItems = lines.map(l => {
      const clean = l.replace(/^[-*]\s*/, '');
      return `<li>${escapeHtml(clean).replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')}</li>`;
    }).join('');
    return `
      <div class="validation-report-card">
        <div class="report-title">
          <i data-lucide="shield-check" class="icon"></i>
          <span>Отчет валидации процесса</span>
        </div>
        <ul>${listItems}</ul>
      </div>
    `;
  }

  function formatProactiveQuestionsCard(questionsText) {
    const lines = questionsText.split('\n').map(l => l.trim()).filter(l => l.startsWith('-') || l.startsWith('*') || /^\d+\./.test(l));
    const listItems = lines.map(l => {
      const clean = l.replace(/^[-*\d\.]\s*/, '');
      return `<li>${escapeHtml(clean).replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')}</li>`;
    }).join('');

    const chips = [];
    const lower = questionsText.toLowerCase();
    if (lower.includes('отрицательн') || lower.includes('отказ') || lower.includes('решени') || lower.includes('шлюз')) {
      chips.push('<button type="button" class="proactive-chip" data-answer="При отказе заявка завершается со статусом Отклонено">Отказ и завершение</button>');
      chips.push('<button type="button" class="proactive-chip" data-answer="При замечаниях заявка возвращается инициатору на доработку">Возврат на доработку</button>');
    }
    if (lower.includes('роль') || lower.includes('подразделен') || lower.includes('отвечает') || lower.includes('кто')) {
      chips.push('<button type="button" class="proactive-chip" data-answer="Задачу выполняет Руководитель отдела">Руководитель отдела</button>');
      chips.push('<button type="button" class="proactive-chip" data-answer="Задачу выполняет Бухгалтерия">Бухгалтерия</button>');
    }
    if (lower.includes('разрыв') || lower.includes('связывает') || lower.includes('переход') || lower.includes('предшествующ') || lower.includes('инициирует')) {
      chips.push('<button type="button" class="proactive-chip" data-answer="После завершения первого этапа сразу запускается следующий этап">Прямой переход</button>');
      chips.push('<button type="button" class="proactive-chip" data-answer="Переход выполняется только после проверки руководителем">Переход после проверки</button>');
    }
    chips.push('<button type="button" class="proactive-chip" data-answer="Доработай схему с учетом стандартного регламента">Стандартный регламент</button>');

    return `
      <div class="proactive-questions-card">
        <div class="questions-title">
          <i data-lucide="help-circle" class="icon"></i>
          <span>Уточняющие вопросы по регламенту</span>
        </div>
        <ul>${listItems}</ul>
        <div class="chips-container">${chips.join('')}</div>
      </div>
    `;
  }

  // ── Markdown Formatter ────────────────────────────────────────────────
  function renderMarkdown(mdText) {
    if (!mdText) return '';

    let text = mdText;
    let reportCardHtml = '';
    let questionsCardHtml = '';

    // Extract validation report block
    const reportMatch = text.match(/📊\s*\*\*Отчет валидации процесса:\*\*([\s\S]*?)(?=(?:❓\s*\*\*|```|$))/i);
    if (reportMatch) {
      reportCardHtml = formatValidationReportCard(reportMatch[1]);
      text = text.replace(reportMatch[0], '{{VALIDATION_REPORT_PLACEHOLDER}}');
    }

    // Extract proactive questions block
    const questionsMatch = text.match(/❓\s*\*\*Уточняющие вопросы по регламенту:\*\*([\s\S]*?)(?=(?:📊\s*\*\*|```|$))/i);
    if (questionsMatch) {
      questionsCardHtml = formatProactiveQuestionsCard(questionsMatch[1]);
      text = text.replace(questionsMatch[0], '{{PROACTIVE_QUESTIONS_PLACEHOLDER}}');
    }

    let parsedHtml = '';
    if (window.marked && typeof window.marked.parse === 'function') {
      try {
        parsedHtml = window.marked.parse(text, { breaks: true, gfm: true });
      } catch (e) {
        console.warn('Marked parse error:', e);
      }
    }
    if (!parsedHtml) {
      let html = escapeHtml(text);
      html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
      html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
      html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');
      html = html.replace(/\*\*([^\*]+)\*\*/g, '<strong>$1</strong>');
      html = html.replace(/\*([^\*]+)\*/g, '<em>$1</em>');
      html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
      parsedHtml = html.split('\n\n').map(p => `<p>${p.replace(/\n/g, '<br/>')}</p>`).join('');
    }

    if (reportCardHtml) {
      parsedHtml = parsedHtml.replace('<p>{{VALIDATION_REPORT_PLACEHOLDER}}</p>', reportCardHtml).replace('{{VALIDATION_REPORT_PLACEHOLDER}}', reportCardHtml);
    }
    if (questionsCardHtml) {
      parsedHtml = parsedHtml.replace('<p>{{PROACTIVE_QUESTIONS_PLACEHOLDER}}</p>', questionsCardHtml).replace('{{PROACTIVE_QUESTIONS_PLACEHOLDER}}', questionsCardHtml);
    }

    return parsedHtml;
  }

  // ── Traceability & Cross-Synchronization (Diagram <-> Code <-> Chat) ──
  function extractLocalTraceability(dslText, promptText) {
    if (!dslText) return [];
    const lines = dslText.split('\n');
    const nodes = [];

    const nodeRegex = /^(start|end|catch|throw|boundary|task|gateway|gate|subprocess|call):\s*([a-zA-Z0-9_]+)\s*(?:"([^"]*)")?(.*)$/;

    for (let i = 0; i < lines.length; i++) {
      const clean = lines[i].split('#')[0].trim();
      const m = clean.match(nodeRegex);
      if (m) {
        const ntype = m[1] === 'gate' ? 'gateway' : m[1];
        const nid = m[2];
        const nlabel = m[3] || nid;
        const rest = m[4] || '';
        const laneM = rest.match(/\bin\s+([a-zA-Z0-9_]+)/);
        nodes.push({
          id: nid,
          type: ntype,
          label: nlabel,
          lane: laneM ? laneM[1] : '',
          line: i + 1,
          quote: ''
        });
      }
    }

    const sentences = (promptText || lastUserPromptText || '')
      .split(/[\r\n]+|[.!?]+/)
      .map(s => s.trim())
      .filter(s => s.length > 3);

    nodes.forEach(node => {
      if (sentences.length > 0) {
        const words = (node.label.match(/[a-zA-Zа-яА-ЯёЁ0-9]{3,}/g) || []).map(w => w.toLowerCase());
        let bestScore = 0;
        let bestSentence = '';
        sentences.forEach(sent => {
          const sentLower = sent.toLowerCase();
          const score = words.filter(w => sentLower.includes(w)).length;
          if (score > bestScore) {
            bestScore = score;
            bestSentence = sent;
          }
        });
        node.quote = (bestScore > 0 && bestSentence) ? bestSentence : node.label;
      } else {
        node.quote = node.label;
      }
    });

    return nodes;
  }

  function updateTraceability(newTrace) {
    if (Array.isArray(newTrace) && newTrace.length > 0) {
      currentTraceability = newTrace;
    } else {
      const code = codeEditor ? codeEditor.value : '';
      currentTraceability = extractLocalTraceability(code, lastUserPromptText);
    }
    refreshChatTraceQuotes();
  }

  function highlightQuotesInUserText(text, traceability) {
    if (!text) return '';
    let html = renderMarkdown(text);
    if (!traceability || traceability.length === 0) return html;

    const quotes = traceability
      .filter(t => t.quote && t.quote.trim().length >= 4)
      .sort((a, b) => b.quote.length - a.quote.length);

    quotes.forEach(t => {
      const q = t.quote.trim();
      const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const regex = new RegExp(`(?<!<[^>]*)(${escaped})(?![^<]*>)`, 'gi');
      html = html.replace(regex, `<mark class="trace-quote" data-element-id="${t.id}" title="Кликните для подсветки на схеме: ${escapeHtml(t.label || t.id)}">$1</mark>`);
    });

    return html;
  }

  function refreshChatTraceQuotes() {
    if (!chatContainer || !currentTraceability || currentTraceability.length === 0) return;
    const userBubbles = chatContainer.querySelectorAll('.chat-bubble.user');
    userBubbles.forEach(b => {
      const raw = b.dataset.rawContent;
      if (raw) {
        const body = b.querySelector('.chat-bubble-body');
        if (body) {
          body.innerHTML = highlightQuotesInUserText(raw, currentTraceability);
        }
      }
    });
  }

  function selectElementOnCanvas(elementId, center = true) {
    if (!modeler || !elementId) return;
    try {
      const elementRegistry = modeler.get('elementRegistry');
      const selection = modeler.get('selection');
      const canvas = modeler.get('canvas');
      const el = elementRegistry.get(elementId);
      if (el) {
        selection.set([el]);
        if (center && typeof canvas.scrollToElement === 'function') {
          canvas.scrollToElement(el);
        }
      }
    } catch (err) {
      console.warn('Canvas select element error:', err);
    }
  }

  function updateActiveLineBarPosition() {
    if (!codeActiveLineBar) return;
    if (activeHighlightedLine < 1) {
      codeActiveLineBar.style.display = 'none';
      return;
    }
    const lineHeight = 22;
    const paddingTop = 12;
    const scroll = codeEditor ? codeEditor.scrollTop : 0;
    const top = paddingTop + (activeHighlightedLine - 1) * lineHeight - scroll;
    codeActiveLineBar.style.transform = `translateY(${top}px)`;
    codeActiveLineBar.style.display = 'block';
  }

  function findDslLineForElement(elementId) {
    if (!elementId) return -1;
    if (Array.isArray(currentTraceability) && currentTraceability.length > 0) {
      const match = currentTraceability.find(t => t.id === elementId);
      if (match && match.line > 0) {
        return match.line;
      }
    }
    if (!codeEditor || !codeEditor.value) return -1;
    const lines = codeEditor.value.split('\n');
    const targetPattern = new RegExp(`^(?:start|end|catch|throw|boundary|task|gateway|gate|subprocess|call|pool|lane|event):\\s*${elementId}\\b`);
    for (let i = 0; i < lines.length; i++) {
      const clean = lines[i].split('#')[0].trim();
      if (targetPattern.test(clean)) {
        return i + 1;
      }
    }
    for (let i = 0; i < lines.length; i++) {
      const clean = lines[i].split('#')[0].trim();
      if (clean.includes(elementId)) {
        return i + 1;
      }
    }
    return -1;
  }

  function highlightLineInEditor(lineNumber) {
    if (!codeEditor || lineNumber < 1) {
      activeHighlightedLine = 0;
      updateActiveLineBarPosition();
      if (lineNumbers) {
        lineNumbers.querySelectorAll('.line-num.active').forEach(el => el.classList.remove('active'));
      }
      return;
    }
    const lines = codeEditor.value.split('\n');
    if (lineNumber > lines.length) return;

    activeHighlightedLine = lineNumber;

    let charStart = 0;
    for (let i = 0; i < lineNumber - 1; i++) {
      charStart += lines[i].length + 1;
    }
    const charEnd = charStart + lines[lineNumber - 1].length;

    const lineHeight = 22;
    const targetScrollTop = (lineNumber - 1) * lineHeight - codeEditor.clientHeight / 2 + lineHeight;
    codeEditor.scrollTop = Math.max(0, targetScrollTop);

    codeEditor.setSelectionRange(charStart, charEnd);

    // Update active line bar position
    updateActiveLineBarPosition();

    // Update line numbers gutter highlight
    if (lineNumbers) {
      lineNumbers.querySelectorAll('.line-num.active').forEach(el => el.classList.remove('active'));
      const numEl = lineNumbers.querySelector(`.line-num[data-line="${lineNumber}"]`);
      if (numEl) {
        numEl.classList.add('active');
      }
    }
  }

  function highlightTraceInChat(elementId) {
    if (!chatContainer) return;
    chatContainer.querySelectorAll('.trace-quote.active').forEach(el => el.classList.remove('active'));
    if (!elementId) return;

    const targetQuotes = chatContainer.querySelectorAll(`.trace-quote[data-element-id="${elementId}"]`);
    if (targetQuotes.length > 0) {
      const lastQuote = targetQuotes[targetQuotes.length - 1];
      lastQuote.classList.add('active');
      lastQuote.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  function highlightTraceInEditor(elementId) {
    if (!codeEditor || !elementId) return;
    const lineNum = findDslLineForElement(elementId);
    if (lineNum > 0) {
      highlightLineInEditor(lineNum);
    }
  }

  function onCanvasElementSelected(elementId) {
    activeTraceElementId = elementId;
    highlightTraceInChat(elementId);
    highlightTraceInEditor(elementId);
  }

  function onEditorCursorChange() {
    if (!codeEditor || codeFromVisual) return;
    const pos = codeEditor.selectionStart;
    const textBefore = codeEditor.value.slice(0, pos);
    const lineIdx = textBefore.split('\n').length - 1;
    const lineText = (codeEditor.value.split('\n')[lineIdx] || '').split('#')[0].trim();
    const m = lineText.match(/^(?:start|end|catch|throw|boundary|task|gateway|gate|subprocess|call):\s*([a-zA-Z0-9_]+)/);
    if (m) {
      const elId = m[1];
      activeTraceElementId = elId;
      selectElementOnCanvas(elId, false);
      highlightTraceInChat(elId);
    }
  }

  // ── Generation Indicator ───────────────────────────────────────────────
  let generatingBubble = null;

  function showGeneratingIndicator() {
    if (generatingBubble || !chatContainer) return;
    generatingBubble = document.createElement('div');
    generatingBubble.id = 'generating-bubble';
    generatingBubble.className = 'chat-bubble assistant generating';
    generatingBubble.innerHTML = `
      <div class="chat-bubble-header">
        <span class="chat-role">AI Архитектор</span>
      </div>
      <div class="chat-bubble-body">
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:0.84rem; color:var(--text-secondary);">GigaChat Ultra анализирует BPMN-схему</span>
          <div class="typing-indicator">
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
          </div>
        </div>
      </div>
    `;
    chatContainer.appendChild(generatingBubble);
    chatContainer.scrollTop = chatContainer.scrollHeight;
  }

  function hideGeneratingIndicator() {
    if (generatingBubble) {
      generatingBubble.remove();
      generatingBubble = null;
    }
  }

  // ── Automatic Correction of DSL Errors (Up to 5 attempts) ─────────────
  async function requestCorrection(errorMsg, brokenDsl, retryCount = 1) {
    if (retryCount > 5 || !abortController || abortController.signal.aborted) {
      setGeneratingState(false);
      return;
    }

    setGeneratingState(true);

    const correctionPrompt = `При компиляции сгенерированного BPMN-as-Code возникла ошибка (попытка ${retryCount} из 5):\n${errorMsg}\n\nПожалуйста, исправь синтаксис диаграммы и верни строго валидный BPMN-as-Code. Убедись, что все элементы сначала объявлены с типом и идентификатором (например: "task: t1 \\"Описание\\""), и лишь затем соединены через -> или --[условие]-->. Не используй несуществующие идентификаторы и не создавай дубликатов.`;

    try {
      const resp = await fetch('/api/refine/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          diagram_id: currentDiagramId,
          instruction: correctionPrompt,
          current_dsl: brokenDsl
        }),
        signal: abortController.signal
      });

      const res = await resp.json();
      hideGeneratingIndicator();

      if (!res.success) {
        if (retryCount < 5 && !abortController.signal.aborted) {
          await requestCorrection(`API error: ${res.error || 'Сбой запроса'}`, brokenDsl, retryCount + 1);
          return;
        }
        appendChatMessage({
          role: 'assistant',
          content: `Не удалось автоматически исправить синтаксис после ${retryCount} попыток: ` + (res.error || 'Ошибка'),
          is_error: true,
          created_at: new Date().toLocaleTimeString()
        });
      } else {
        appendChatMessage(res.assistant_message);
        if (res.traceability) {
          updateTraceability(res.traceability);
        } else {
          updateTraceability();
        }
        if (res.has_dsl && res.dsl_code && codeEditor) {
          codeEditor.value = res.dsl_code;
          updateLineNumbers();
          updateDslHighlight();
          lastSourceOfChange = 'ai';
          const retryRes = compileCode();
          if (retryRes && !retryRes.valid && retryCount < 5 && !abortController.signal.aborted) {
            await requestCorrection(retryRes.error, res.dsl_code, retryCount + 1);
            return;
          }
        }
      }
    } catch (err) {
      hideGeneratingIndicator();
      if (err.name !== 'AbortError') {
        console.warn('Auto-correction request error:', err);
      }
    } finally {
      setGeneratingState(false);
    }
  }

  // ── Chat Messages Rendering & Bulk Selection ──────────────────────────
  const selectedMessageIds = new Set();

  function updateBulkDeleteBar() {
    if (!bulkDeleteBar) return;
    const count = selectedMessageIds.size;
    if (count > 0) {
      bulkDeleteBar.style.display = 'flex';
      if (bulkDeleteCount) bulkDeleteCount.textContent = `Выбрано: ${count}`;
    } else {
      bulkDeleteBar.style.display = 'none';
    }
  }

  function updateBubbleId(bubble, newId) {
    if (!bubble || !newId) return;
    const oldId = bubble.dataset.id;
    bubble.dataset.id = newId;
    const chk = bubble.querySelector('.chat-select-chk');
    if (chk) {
      chk.dataset.id = newId;
      if (oldId && selectedMessageIds.has(oldId)) {
        selectedMessageIds.delete(oldId);
        selectedMessageIds.add(newId);
      }
    }
    const delBtn = bubble.querySelector('.delete-msg-btn');
    if (delBtn) delBtn.dataset.id = newId;
  }

  function appendChatMessage(msg) {
    if (!chatContainer) return null;
    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${msg.role} ${msg.is_error ? 'error' : ''}`;
    const msgId = msg.id != null ? String(msg.id) : ('temp-' + Date.now() + '-' + Math.random().toString(36).substr(2, 5));
    bubble.dataset.id = msgId;

    const roleName = msg.role === 'user' ? 'Вы' : 'AI Архитектор';

    const actionsHtml = `
      <div class="chat-bubble-actions">
        <input type="checkbox" class="chat-select-chk" data-id="${msgId}" title="Выбрать для удаления"/>
        <button class="chat-action-btn delete-msg-btn" data-id="${msgId}" title="Удалить сообщение">
          <i data-lucide="trash-2" class="icon-sm"></i>
        </button>
      </div>
    `;

    let explanationHtml = '';
    if (msg.explanation && msg.explanation.trim() !== (msg.content || '').trim()) {
      explanationHtml = `<div class="chat-bubble-explanation">${renderMarkdown(msg.explanation)}</div>`;
    }

    if (msg.role === 'user') {
      bubble.dataset.rawContent = msg.content || '';
      if (msg.content) lastUserPromptText = msg.content;
    }

    const formattedContent = (!msg.is_error)
      ? (msg.role === 'user' ? highlightQuotesInUserText(msg.content, currentTraceability) : renderMarkdown(msg.content))
      : `<p>${escapeHtml(msg.content).replace(/\n/g, '<br/>')}</p>`;

    bubble.innerHTML = `
      <div class="chat-bubble-header">
        <span class="chat-role">${roleName}</span>
        <div style="display:flex; align-items:center; gap:8px;">
          <span class="chat-time">${msg.created_at || ''}</span>
          ${actionsHtml}
        </div>
      </div>
      <div class="chat-bubble-body">${formattedContent}</div>
      ${explanationHtml}
    `;

    // Events inside bubble
    const chk = bubble.querySelector('.chat-select-chk');
    if (chk) {
      chk.addEventListener('change', () => {
        const id = chk.dataset.id;
        chk.checked ? selectedMessageIds.add(id) : selectedMessageIds.delete(id);
        updateBulkDeleteBar();
      });
    }

    const delBtn = bubble.querySelector('.delete-msg-btn');
    if (delBtn) {
      delBtn.addEventListener('click', async () => {
        const id = delBtn.dataset.id;
        const confirmed = await showCustomConfirm('Удалить это сообщение?', 'Удаление сообщения', 'Удалить', 'Отмена');
        if (confirmed) {
          await deleteMessages([id]);
          bubble.remove();
          selectedMessageIds.delete(id);
          selectedMessageIds.delete(parseInt(id));
          updateBulkDeleteBar();
          showToast('Сообщение удалено', 'info');
        }
      });
    }

    const copyBtn = bubble.querySelector('.copy-dsl-btn');
    if (copyBtn) {
      copyBtn.addEventListener('click', () => {
        navigator.clipboard.writeText(msg.dsl_code);
        showToast('Код DSL скопирован в буфер обмена', 'success');
      });
    }

    chatContainer.appendChild(bubble);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    refreshIcons();
    return bubble;
  }

  if (chatContainer) {
    chatContainer.addEventListener('click', (e) => {
      // 1. Click on trace quote in user chat message
      const quote = e.target.closest('.trace-quote');
      if (quote) {
        const elId = quote.dataset.elementId;
        if (elId) {
          activeTraceElementId = elId;
          selectElementOnCanvas(elId, true);
          highlightTraceInEditor(elId);
          highlightTraceInChat(elId);
        }
        return;
      }

      // 2. Click on proactive question quick-reply chip
      const chip = e.target.closest('.proactive-chip');
      if (chip) {
        const answer = chip.dataset.answer || chip.textContent.trim();
        if (promptInput) {
          promptInput.value = answer;
          promptInput.focus();
          if (generateBtn && !generateBtn.disabled && !isGenerating) {
            generateBtn.click();
          }
        }
        return;
      }
    });
  }

  async function deleteMessages(ids, clearAll = false) {
    if (!currentDiagramId) return;
    try {
      if (clearAll) {
        await fetch(`/api/diagrams/${currentDiagramId}/messages/`, {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ clear_all: true })
        });
      } else {
        const realIds = ids
          .filter(id => id != null && !String(id).startsWith('temp-') && !isNaN(parseInt(id)))
          .map(id => parseInt(id));
        if (realIds.length > 0) {
          const payload = realIds.length === 1 ? { message_id: realIds[0] } : { message_ids: realIds };
          await fetch(`/api/diagrams/${currentDiagramId}/messages/`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          });
        }
      }
    } catch (e) {
      console.error('Delete message error:', e);
    }
  }

  if (bulkDeleteBtn) {
    bulkDeleteBtn.addEventListener('click', async () => {
      const ids = Array.from(selectedMessageIds);
      if (ids.length === 0) return;
      const confirmed = await showCustomConfirm(`Удалить выбранные сообщения (${ids.length})?`, 'Удаление сообщений', 'Удалить', 'Отмена');
      if (confirmed) {
        await deleteMessages(ids);
        ids.forEach(id => {
          const b = chatContainer.querySelector(`.chat-bubble[data-id="${id}"]`);
          if (b) b.remove();
        });
        selectedMessageIds.clear();
        updateBulkDeleteBar();
        showToast(`Удалено сообщений: ${ids.length}`, 'info');
      }
    });
  }

  if (bulkCancelBtn) {
    bulkCancelBtn.addEventListener('click', () => {
      selectedMessageIds.clear();
      document.querySelectorAll('.chat-select-chk').forEach(c => (c.checked = false));
      updateBulkDeleteBar();
    });
  }

  if (clearChatBtn) {
    clearChatBtn.addEventListener('click', async () => {
      const confirmed = await showCustomConfirm('Очистить всю переписку по этой диаграмме?', 'Очистка чата', 'Очистить', 'Отмена');
      if (confirmed) {
        await deleteMessages([], true);
        if (chatContainer) chatContainer.innerHTML = '';
        selectedMessageIds.clear();
        updateBulkDeleteBar();
        showToast('Переписка очищена', 'info');
      }
    });
  }

  // ── Sidebar Drawer: Projects & Chats Navigation ────────────────────────
  function openSidebar() {
    if (sidebarDrawer) sidebarDrawer.classList.add('open');
    if (sidebarBackdrop) sidebarBackdrop.classList.add('open');
    refreshSidebarProjects();
  }

  function closeSidebar() {
    if (sidebarDrawer) sidebarDrawer.classList.remove('open');
    if (sidebarBackdrop) sidebarBackdrop.classList.remove('open');
  }

  if (sidebarToggleBtn) {
    sidebarToggleBtn.addEventListener('click', () => {
      if (sidebarDrawer && sidebarDrawer.classList.contains('open')) {
        closeSidebar();
      } else {
        openSidebar();
      }
    });
  }

  if (sidebarCloseBtn) sidebarCloseBtn.addEventListener('click', closeSidebar);
  if (sidebarBackdrop) sidebarBackdrop.addEventListener('click', closeSidebar);

  if (sidebarProjectsList) {
    sidebarProjectsList.addEventListener('auxclick', (e) => {
      e.preventDefault();
      e.stopPropagation();
    });
    sidebarProjectsList.addEventListener('dragstart', (e) => {
      e.preventDefault();
      e.stopPropagation();
    });
  }

  async function handleChatDeletion(diagId, diagName, projId) {
    if (!isAuth) {
      showToast('В гостевом режиме схема не сохранена в базе данных.', 'warn');
      return;
    }
    if (!diagId) return;
    const titleText = diagName ? `«${diagName}»` : 'этот чат';
    const confirmed = await showCustomConfirm(
      `Удалить ${titleText} со всей историей переписки? Это действие необратимо.`,
      'Удаление чата',
      'Удалить',
      'Отмена'
    );
    if (!confirmed) return;

    try {
      const resp = await fetch(`/api/diagrams/${diagId}/`, { method: 'DELETE' });
      const res = await resp.json();
      if (res.success) {
        if (diagId === currentDiagramId) {
          try {
            const pResp = await fetch('/api/projects/');
            const pData = await pResp.json();
            let nextDiag = null;
            let nextProj = null;
            if (pData && pData.projects) {
              const curP = pData.projects.find(p => p.id === (projId || currentProjectId));
              if (curP && curP.diagrams && curP.diagrams.length > 0) {
                nextDiag = curP.diagrams[0];
                nextProj = curP;
              } else {
                for (const p of pData.projects) {
                  if (p.diagrams && p.diagrams.length > 0) {
                    nextDiag = p.diagrams[0];
                    nextProj = p;
                    break;
                  }
                }
              }
            }
            if (nextDiag) {
              currentProjectId = nextProj.id;
              currentDiagramId = nextDiag.id;
              updateBrowserUrl(currentProjectId, currentDiagramId);
              await loadDiagram(currentDiagramId);
              await refreshSidebarProjects();
              showToast(`Чат ${titleText} удален`, 'info');
            } else {
              window.location.href = '/';
            }
          } catch (e) {
            location.reload();
          }
        } else {
          await refreshSidebarProjects();
          showToast(`Чат ${titleText} удален`, 'info');
        }
      } else {
        showToast(res.error || 'Ошибка удаления чата', 'error');
      }
    } catch (err) {
      showToast('Ошибка удаления: ' + err.message, 'error');
    }
  }

  function updateBrowserUrl(projectId, diagramId) {
    if (!projectId) return;
    try {
      const targetQuery = diagramId
        ? `/?project=${encodeURIComponent(projectId)}&diagram=${encodeURIComponent(diagramId)}`
        : `/?project=${encodeURIComponent(projectId)}`;
      const currentQuery = window.location.pathname + window.location.search;
      if (currentQuery !== targetQuery) {
        window.history.replaceState({ projectId, diagramId }, '', targetQuery);
      }
    } catch (err) {
      console.warn('URL update skipped:', err);
    }
  }

  function updateSidebarActiveStates() {
    if (!sidebarProjectsList) return;
    const groups = sidebarProjectsList.querySelectorAll('.sidebar-project-group');
    groups.forEach(g => {
      const isCur = String(g.dataset.id) === String(currentProjectId);
      g.classList.toggle('active', isCur);
    });
    const items = sidebarProjectsList.querySelectorAll('.sidebar-chat-item');
    items.forEach(it => {
      const isCur = String(it.dataset.did) === String(currentDiagramId);
      it.classList.toggle('active', isCur);
    });
  }

  async function refreshSidebarProjects() {
    if (!sidebarProjectsList) return;
    try {
      const resp = await fetch('/api/projects/');
      const data = await resp.json();
      if (!data.projects) return;

      sidebarProjectsList.innerHTML = '';

      data.projects.forEach(project => {
        const group = document.createElement('div');
        group.className = `sidebar-project-group ${project.id === currentProjectId ? 'active' : ''}`;
        group.dataset.id = project.id;

        const header = document.createElement('div');
        header.className = 'sidebar-project-header';
        header.setAttribute('draggable', 'false');
        header.innerHTML = `
          <i data-lucide="folder" class="icon-sm" style="color:var(--accent-primary);"></i>
          <span class="sidebar-project-name">${escapeHtml(project.name)}</span>
          <div class="sidebar-project-actions">
            <button type="button" class="btn btn-ghost btn-icon btn-sm action-add-chat" data-pid="${project.id}" title="Добавить чат/схему">
              <i data-lucide="plus" class="icon-sm"></i>
            </button>
            <button type="button" class="btn btn-ghost btn-icon btn-sm action-edit-project" data-pid="${project.id}" data-name="${escapeHtml(project.name)}" title="Переименовать проект">
              <i data-lucide="pencil" class="icon-sm"></i>
            </button>
            <button type="button" class="btn btn-ghost btn-icon btn-sm action-delete-project" data-pid="${project.id}" data-name="${escapeHtml(project.name)}" title="Удалить проект">
              <i data-lucide="trash-2" class="icon-sm"></i>
            </button>
          </div>
        `;

        const chatList = document.createElement('div');
        chatList.className = 'sidebar-chat-list';

        if (project.diagrams && project.diagrams.length > 0) {
          project.diagrams.forEach(diag => {
            const item = document.createElement('div');
            item.className = `sidebar-chat-item ${diag.id === currentDiagramId ? 'active' : ''}`;
            item.dataset.did = diag.id;
            item.setAttribute('draggable', 'false');
            item.innerHTML = `
              <div class="sidebar-chat-main">
                <i data-lucide="message-square" class="icon-sm"></i>
                <span class="sidebar-chat-title" title="${escapeHtml(diag.name)}">${escapeHtml(diag.name)}</span>
              </div>
              <div class="sidebar-chat-actions">
                <span class="sidebar-chat-time">${diag.updated_at ? diag.updated_at.split(' ')[1] : ''}</span>
                <button type="button" class="sidebar-chat-delete-btn" data-did="${diag.id}" data-name="${escapeHtml(diag.name)}" title="Удалить чат">
                  <i data-lucide="trash-2" class="icon-sm"></i>
                </button>
              </div>
            `;
            item.addEventListener('click', async (e) => {
              if (e.button !== 0) return;
              if (e.target.closest('.sidebar-chat-delete-btn')) return;
              e.preventDefault();
              e.stopPropagation();
              currentProjectId = project.id;
              currentDiagramId = diag.id;
              updateSidebarActiveStates();
              await loadDiagram(currentDiagramId);
              updateBrowserUrl(currentProjectId, diag.id);
              if (window.innerWidth < 800) closeSidebar();
            });

            const delChatBtn = item.querySelector('.sidebar-chat-delete-btn');
            if (delChatBtn) {
              delChatBtn.addEventListener('click', async (e) => {
                e.preventDefault();
                e.stopPropagation();
                await handleChatDeletion(diag.id, diag.name, project.id);
              });
            }

            chatList.appendChild(item);
          });
        } else {
          const empty = document.createElement('div');
          empty.style.padding = '6px 10px';
          empty.style.fontSize = '0.74rem';
          empty.style.color = 'var(--text-muted)';
          empty.textContent = 'Нет схем';
          chatList.appendChild(empty);
        }

        group.appendChild(header);
        group.appendChild(chatList);
        sidebarProjectsList.appendChild(group);

        header.addEventListener('click', (e) => {
          if (e.button !== 0) return;
          if (e.target.closest('.sidebar-project-actions')) return;
          e.preventDefault();
          e.stopPropagation();
          currentProjectId = project.id;
          if (project.diagrams && project.diagrams.length > 0) {
            currentDiagramId = project.diagrams[0].id;
            loadDiagram(currentDiagramId);
            updateBrowserUrl(currentProjectId, currentDiagramId);
          }
          updateSidebarActiveStates();
        });

        const addChatBtn = header.querySelector('.action-add-chat');
        if (addChatBtn) {
          addChatBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            currentProjectId = project.id;
            createNewDiagram();
          });
        }

        const editProjBtn = header.querySelector('.action-edit-project');
        if (editProjBtn) {
          editProjBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            const newName = await showCustomPrompt(
              'Введите новое название проекта:',
              editProjBtn.dataset.name,
              'Переименование проекта',
              'Сохранить',
              'Отмена'
            );
            if (newName && newName.trim()) {
              try {
                const resp = await fetch(`/api/projects/${project.id}/`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ name: newName.trim() })
                });
                const res = await resp.json();
                if (res.success) {
                  refreshSidebarProjects();
                  showToast('Проект переименован', 'success');
                } else {
                  showToast(res.error || 'Ошибка переименования', 'error');
                }
              } catch (err) {
                showToast('Ошибка сети: ' + err.message, 'error');
              }
            }
          });
        }

        const delProjBtn = header.querySelector('.action-delete-project');
        if (delProjBtn) {
          delProjBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            const confirmed = await showCustomConfirm(`Удалить проект «${delProjBtn.dataset.name}» со всеми его схемами и чатами?`, 'Удаление проекта', 'Удалить проект', 'Отмена');
            if (confirmed) {
              await fetch(`/api/projects/${project.id}/`, { method: 'DELETE' });
              location.reload();
            }
          });
        }
      });

      refreshIcons();
    } catch (err) {
      console.error('Failed to load sidebar projects:', err);
    }
  }

  // Initial Sidebar render
  refreshSidebarProjects();

  if (sidebarNewProjectBtn) {
    sidebarNewProjectBtn.addEventListener('click', () => {
      closeSidebar();
      if (!isAuth) {
        showToast('Для создания проектов необходимо войти или зарегистрироваться', 'warn');
        openAuthModal('register');
        return;
      }
      if (projectModal) {
        projectModal.classList.add('open');
        const inp = document.getElementById('modal-project-name');
        if (inp) inp.focus();
      }
    });
  }

  // ── Diagram Title & Auto-Save ──────────────────────────────────────────
  if (diagramTitleInput) {
    diagramTitleInput.addEventListener('change', async () => {
      const newName = diagramTitleInput.value.trim();
      if (!newName || !currentDiagramId) return;
      try {
        await fetch(`/api/diagrams/${currentDiagramId}/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: newName })
        });
        refreshSidebarProjects();
        showToast('Название диаграммы обновлено', 'info');
      } catch (e) {
        console.error('Rename diagram error:', e);
      }
    });
  }

  async function loadDiagram(diagramId) {
    try {
      const resp = await fetch(`/api/diagrams/${diagramId}/`);
      const data = await resp.json();
      if (data.diagram) {
        if (diagramTitleInput) diagramTitleInput.value = data.diagram.name;
        if (codeEditor) codeEditor.value = data.diagram.dsl_code || '';
        updateLineNumbers();
        updateDslHighlight();
        lastSourceOfChange = 'loaded';
        compileCode();

        if (chatContainer) chatContainer.innerHTML = '';
        if (data.diagram.messages) {
          const userMsgs = data.diagram.messages.filter(m => m.role === 'user');
          if (userMsgs.length > 0) {
            lastUserPromptText = userMsgs[userMsgs.length - 1].content || '';
          }
          data.diagram.messages.forEach(appendChatMessage);
          updateTraceability();
        }
      }
    } catch (e) {
      console.error('Load diagram error:', e);
    }
  }

  // ── New Chat/Diagram Button ───────────────────────────────────────────
  if (newChatBtn) {
    newChatBtn.addEventListener('click', createNewDiagram);
  }

  async function createNewDiagram() {
    if (!isAuth) {
      showToast('В гостевом режиме новые схемы не сохраняются. Пожалуйста, войдите или зарегистрируйтесь.', 'warn');
      openAuthModal('register');
      return;
    }
    if (!currentProjectId) {
      showToast('Сначала выберите или создайте проект', 'warn');
      return;
    }
    const name = await showCustomPrompt('Введите название новой диаграммы / процесса:', 'Новый процесс', 'Создание диаграммы', 'Создать', 'Отмена');
    if (!name || !name.trim()) return;

    try {
      const resp = await fetch('/api/diagrams/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: currentProjectId,
          name: name.trim(),
          dsl_code: `process "${name.trim()}"\n\nstart: s "Начало"\nend: e "Завершение"\n\ns -> e`
        })
      });
      const res = await resp.json();
      if (res.success) {
        currentDiagramId = res.diagram.id;
        await loadDiagram(currentDiagramId);
        refreshSidebarProjects();
        switchUnifiedTab('tab-chat');
        showToast(`Диаграмма «${res.diagram.name}» создана`, 'success');
        updateBrowserUrl(currentProjectId, res.diagram.id);
      } else {
        showToast(res.error || 'Ошибка при создании диаграммы', 'error');
      }
    } catch (err) {
      showToast('Ошибка создания диаграммы: ' + err.message, 'error');
    }
  }

  // ── Delete Chat/Diagram on main screen ────────────────────────────────
  if (deleteChatBtn) {
    deleteChatBtn.addEventListener('click', async () => {
      const diagTitle = diagramTitleInput && diagramTitleInput.value.trim()
        ? diagramTitleInput.value.trim()
        : '';
      await handleChatDeletion(currentDiagramId, diagTitle, currentProjectId);
    });
  }

  // ── New Project Form Submit ───────────────────────────────────────────
  if (modalCancelProject) {
    modalCancelProject.addEventListener('click', () => {
      if (projectModal) projectModal.classList.remove('open');
    });
  }

  if (projectForm) {
    projectForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const nameInp = document.getElementById('modal-project-name');
      const descInp = document.getElementById('modal-project-desc');
      const name = nameInp ? nameInp.value.trim() : '';
      const desc = descInp ? descInp.value.trim() : '';
      if (!name) return;

      try {
        const resp = await fetch('/api/projects/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, description: desc })
        });
        const res = await resp.json();
        if (res.success) {
          if (projectModal) projectModal.classList.remove('open');
          currentProjectId = res.project.id;
          if (res.diagram) {
            currentDiagramId = res.diagram.id;
            await loadDiagram(currentDiagramId);
            updateBrowserUrl(currentProjectId, res.diagram.id);
          }
          await refreshSidebarProjects();
          showToast(`Проект «${res.project.name}» успешно создан`, 'success');
        }
      } catch (err) {
        showToast('Ошибка создания проекта: ' + err.message, 'error');
      }
    });
  }

  // ── Save Diagram ───────────────────────────────────────────────────────
  async function saveCurrentDiagram(silent = false) {
    if (!isAuth) {
      if (!silent) {
        showToast('В гостевом режиме схемы не сохраняются в БД. Пожалуйста, войдите или зарегистрируйтесь.', 'warn');
        openAuthModal('register');
      }
      return { success: false, guest: true };
    }
    if (!currentDiagramId) return { success: false, error: 'Нет активной диаграммы' };
    let xml = '';
    if (lastSourceOfChange === 'visual' && modeler) {
      clearTimeout(visualSyncTimer);
      try {
        const res = await modeler.saveXML({ format: true });
        xml = res.xml;
        const newDsl = decompileXml(xml);
        if (newDsl && codeEditor) {
          codeEditor.value = newDsl;
          updateLineNumbers();
          updateDslHighlight();
        }
      } catch (e) {
        console.warn('saveCurrentDiagram visual sync error:', e);
      }
    } else {
      if (lastSourceOfChange === 'code') {
        clearTimeout(compileTimer);
        const comp = compileCode();
        if (comp && comp.xml) xml = comp.xml;
      }
      if (!xml && modeler) {
        try {
          const res = await modeler.saveXML({ format: true });
          xml = res.xml;
        } catch (e) {
          console.warn('saveCurrentDiagram xml fallback error:', e);
        }
      }
    }
    try {
      const resp = await fetch(`/api/diagrams/${currentDiagramId}/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dsl_code: codeEditor ? codeEditor.value : '',
          bpmn_xml: xml
        })
      });
      const res = await resp.json();
      if (res.auth_required) {
        if (!silent) {
          showToast(res.error || 'Для сохранения войдите в систему', 'warn');
          openAuthModal('register');
        }
        return res;
      }
      if (res.success && !silent) {
        updateStatusBadge('ok', 'Схема сохранена');
        showToast('Диаграмма сохранена', 'success');
        setTimeout(() => updateStatusBadge('', 'Готов'), 2000);
      }
      return res;
    } catch (e) {
      if (!silent) showToast('Ошибка сохранения: ' + e.message, 'error');
      return { success: false, error: e.message };
    }
  }

  if (saveBtn) {
    saveBtn.addEventListener('click', () => saveCurrentDiagram(false));
  }

  // ── Knowledge Base Management Modal ────────────────────────────────────
  let activeKbFile = null;

  if (kbModalBtn) {
    kbModalBtn.addEventListener('click', async () => {
      if (kbModal) kbModal.classList.add('open');
      await loadKbFiles();
    });
  }

  if (kbModalClose) {
    kbModalClose.addEventListener('click', () => {
      if (kbModal) kbModal.classList.remove('open');
    });
  }

  async function loadKbFiles() {
    if (!kbFilesList) return;
    try {
      const resp = await fetch('/api/kb/');
      const data = await resp.json();
      kbFilesList.innerHTML = '';
      if (data.files && data.files.length > 0) {
        data.files.forEach((f, i) => {
          const item = document.createElement('div');
          item.className = `kb-file-item ${i === 0 ? 'active' : ''}`;
          item.dataset.name = f.name;
          item.innerHTML = `
            <span>${escapeHtml(f.name)}</span>
            <button class="btn btn-ghost btn-icon btn-sm kb-del-file" title="Удалить файл">
              <i data-lucide="trash-2" class="icon-sm"></i>
            </button>
          `;
          item.addEventListener('click', (e) => {
            if (e.target.closest('.kb-del-file')) return;
            selectKbFile(f.name);
          });

          const delBtn = item.querySelector('.kb-del-file');
          if (delBtn) {
            delBtn.addEventListener('click', async (e) => {
              e.stopPropagation();
              if (!isAuth) {
                showToast('Для изменения базы знаний необходимо войти или зарегистрироваться', 'warn');
                openAuthModal('register');
                return;
              }
              const confirmed = await showCustomConfirm(`Удалить файл базы знаний «${f.name}»?`, 'Удаление файла базы знаний', 'Удалить', 'Отмена');
              if (confirmed) {
                await fetch(`/api/kb/${f.name}/`, { method: 'DELETE' });
                await loadKbFiles();
                showToast(`Файл «${f.name}» удален`, 'info');
              }
            });
          }

          kbFilesList.appendChild(item);
        });

        selectKbFile(data.files[0].name);
        refreshIcons();
      }
    } catch (e) {
      console.error('Load KB files error:', e);
    }
  }

  async function selectKbFile(fileName) {
    activeKbFile = fileName;
    document.querySelectorAll('.kb-file-item').forEach(el => {
      el.classList.toggle('active', el.dataset.name === fileName);
    });
    if (kbCurrentFileName) kbCurrentFileName.textContent = fileName;

    try {
      const resp = await fetch(`/api/kb/${fileName}/`);
      const data = await resp.json();
      if (kbFileEditor) kbFileEditor.value = data.content || '';
    } catch (e) {
      if (kbFileEditor) kbFileEditor.value = 'Ошибка загрузки файла: ' + e.message;
    }
  }

  if (kbSaveFileBtn) {
    kbSaveFileBtn.addEventListener('click', async () => {
      if (!isAuth) {
        showToast('Для изменения базы знаний необходимо войти или зарегистрироваться', 'warn');
        openAuthModal('register');
        return;
      }
      if (!activeKbFile) return;
      try {
        const resp = await fetch(`/api/kb/${activeKbFile}/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: kbFileEditor ? kbFileEditor.value : '' })
        });
        const res = await resp.json();
        if (res.success) {
          showToast(`Файл «${activeKbFile}» сохранен!`, 'success');
        }
      } catch (e) {
        showToast('Ошибка сохранения файла: ' + e.message, 'error');
      }
    });
  }

  if (kbNewFileBtn) {
    kbNewFileBtn.addEventListener('click', async () => {
      if (!isAuth) {
        showToast('Для добавления файлов в базу знаний необходимо войти или зарегистрироваться', 'warn');
        openAuthModal('register');
        return;
      }
      const name = await showCustomPrompt('Введите имя нового файла базы знаний:', '06_rules.md', 'Новый файл базы знаний', 'Создать', 'Отмена');
      if (!name || !name.trim()) return;
      try {
        const resp = await fetch('/api/kb/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: name.trim(), content: `# ${name.trim()}\n\n` })
        });
        const res = await resp.json();
        if (res.success) {
          await loadKbFiles();
          selectKbFile(res.file.name);
          showToast(`Файл «${res.file.name}» создан`, 'success');
        } else {
          showToast(res.error || 'Ошибка создания файла', 'error');
        }
      } catch (e) {
        showToast('Ошибка: ' + e.message, 'error');
      }
    });
  }

  // KB File Upload & Format Validation
  if (kbUploadZone && kbUploadInput) {
    kbUploadZone.addEventListener('click', () => kbUploadInput.click());

    kbUploadInput.addEventListener('change', async () => {
      const file = kbUploadInput.files[0];
      if (!file) return;

      if (!isAuth) {
        showToast('Для загрузки файлов в базу знаний необходимо войти или зарегистрироваться', 'warn');
        openAuthModal('register');
        kbUploadInput.value = '';
        return;
      }

      const forbidden = ['.exe', '.bat', '.cmd', '.sh', '.py', '.bin', '.dll', '.msi', '.js', '.vbs'];
      const ext = '.' + file.name.split('.').pop().toLowerCase();
      if (forbidden.includes(ext)) {
        showCustomAlert(`Загрузка файлов формата ${ext} строго запрещена из соображений безопасности.`, 'Недопустимый формат');
        kbUploadInput.value = '';
        return;
      }

      const formData = new FormData();
      formData.append('file', file);

      try {
        const resp = await fetch('/api/kb/upload/', {
          method: 'POST',
          body: formData
        });
        const res = await resp.json();
        if (res.success) {
          showToast(`Файл «${file.name}» успешно добавлен в базу знаний!`, 'success');
          await loadKbFiles();
          selectKbFile(res.file.name);
        } else {
          showToast(res.error || 'Ошибка загрузки файла', 'error');
        }
      } catch (err) {
        showToast('Ошибка отправки файла: ' + err.message, 'error');
      } finally {
        kbUploadInput.value = '';
      }
    });
  }

  function adjustDropdownPosition(menu) {
    if (!menu) return;
    menu.style.marginLeft = '0px';
    menu.style.marginRight = '0px';
    requestAnimationFrame(() => {
      if (!menu.classList.contains('open')) return;
      const rect = menu.getBoundingClientRect();
      const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
      if (rect.right > viewportWidth - 8) {
        const overflow = rect.right - (viewportWidth - 8);
        menu.style.marginRight = `${overflow}px`;
      } else if (rect.left < 8) {
        const underflow = 8 - rect.left;
        menu.style.marginLeft = `${underflow}px`;
      }
    });
  }

  // ── Robust Export Engine (PDF, PNG, SVG, BPMN XML, DSL) ────────────────
  if (exportBtn && exportMenu) {
    exportBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      exportMenu.classList.toggle('open');
      if (exportMenu.classList.contains('open')) {
        if (mobileMoreMenu) mobileMoreMenu.classList.remove('open');
        adjustDropdownPosition(exportMenu);
      }
    });

    document.addEventListener('click', (e) => {
      if (!exportMenu.contains(e.target) && e.target !== exportBtn && !exportBtn.contains(e.target)) {
        exportMenu.classList.remove('open');
      }
    });
  }

  function getDiagramFilename(ext) {
    const title = diagramTitleInput && diagramTitleInput.value.trim()
      ? diagramTitleInput.value.trim().replace(/[^a-zA-Z0-9а-яА-ЯёЁ_-]+/g, '_')
      : 'diagram';
    return `${title}.${ext}`;
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // ── Safe SVG Extraction Helper (Works even when canvas is hidden in mobile view) ──
  async function getExportSvg() {
    if (!modeler) throw new Error('Модель BPMN не инициализирована');

    const panelCanvas = document.getElementById('panel-canvas');
    const isHidden = !panelCanvas || panelCanvas.offsetWidth === 0 || panelCanvas.offsetHeight === 0;
    let cleanup = null;

    if (isHidden && panelCanvas) {
      // Temporarily render canvas offscreen so bpmn-js/diagram-js can measure layout & elements
      const prev = {
        position: panelCanvas.style.position,
        left: panelCanvas.style.left,
        top: panelCanvas.style.top,
        width: panelCanvas.style.width,
        height: panelCanvas.style.height,
        visibility: panelCanvas.style.visibility,
        display: panelCanvas.style.display,
        zIndex: panelCanvas.style.zIndex
      };

      panelCanvas.style.setProperty('position', 'fixed', 'important');
      panelCanvas.style.setProperty('left', '-9999px', 'important');
      panelCanvas.style.setProperty('top', '0', 'important');
      panelCanvas.style.setProperty('width', '1400px', 'important');
      panelCanvas.style.setProperty('height', '900px', 'important');
      panelCanvas.style.setProperty('visibility', 'hidden', 'important');
      panelCanvas.style.setProperty('display', 'flex', 'important');
      panelCanvas.style.setProperty('z-index', '-999', 'important');

      try {
        const canvas = modeler.get('canvas');
        if (canvas) {
          canvas.resized();
          canvas.zoom('fit-viewport');
        }
      } catch (e) {
        console.warn('Canvas resize skipped:', e);
      }

      cleanup = () => {
        if (prev.position) panelCanvas.style.position = prev.position; else panelCanvas.style.removeProperty('position');
        if (prev.left) panelCanvas.style.left = prev.left; else panelCanvas.style.removeProperty('left');
        if (prev.top) panelCanvas.style.top = prev.top; else panelCanvas.style.removeProperty('top');
        if (prev.width) panelCanvas.style.width = prev.width; else panelCanvas.style.removeProperty('width');
        if (prev.height) panelCanvas.style.height = prev.height; else panelCanvas.style.removeProperty('height');
        if (prev.visibility) panelCanvas.style.visibility = prev.visibility; else panelCanvas.style.removeProperty('visibility');
        if (prev.display) panelCanvas.style.display = prev.display; else panelCanvas.style.removeProperty('display');
        if (prev.zIndex) panelCanvas.style.zIndex = prev.zIndex; else panelCanvas.style.removeProperty('z-index');
      };
    }

    try {
      const result = await modeler.saveSVG();
      const svg = result.svg;

      // Sanitize and ensure positive dimensions and viewBox
      const parser = new DOMParser();
      const doc = parser.parseFromString(svg, 'image/svg+xml');
      const svgEl = doc.documentElement;

      let width = parseFloat(svgEl.getAttribute('width'));
      let height = parseFloat(svgEl.getAttribute('height'));

      const viewBoxAttr = svgEl.getAttribute('viewBox');
      let vbWidth = 0;
      let vbHeight = 0;
      if (viewBoxAttr) {
        const parts = viewBoxAttr.trim().split(/[\s,]+/).map(parseFloat);
        if (parts.length === 4 && parts[2] > 10 && parts[3] > 10) {
          vbWidth = parts[2];
          vbHeight = parts[3];
        }
      }

      if (!width || width < 20 || isNaN(width)) {
        width = vbWidth > 20 ? vbWidth : 1200;
      }
      if (!height || height < 20 || isNaN(height)) {
        height = vbHeight > 20 ? vbHeight : 800;
      }

      svgEl.setAttribute('width', String(Math.round(width)));
      svgEl.setAttribute('height', String(Math.round(height)));

      if (!viewBoxAttr || vbWidth < 20 || vbHeight < 20) {
        svgEl.setAttribute('viewBox', `0 0 ${Math.round(width)} ${Math.round(height)}`);
      }

      if (!svgEl.getAttribute('xmlns')) {
        svgEl.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
      }

      const cleanSvg = new XMLSerializer().serializeToString(svgEl);
      return { svg: cleanSvg, width: Math.round(width), height: Math.round(height) };
    } finally {
      if (cleanup) cleanup();
    }
  }

  // Export BPMN 2.0 XML (.bpmn)
  const exportBpmnBtn = document.getElementById('export-bpmn-btn');
  if (exportBpmnBtn) {
    exportBpmnBtn.addEventListener('click', async () => {
      if (exportMenu) exportMenu.classList.remove('open');
      try {
        let xml = '';
        if (modeler) {
          const res = await modeler.saveXML({ format: true });
          xml = res.xml;
        } else if (codeEditor && window.BpmnAsCode) {
          const res = window.BpmnAsCode.compile(codeEditor.value);
          xml = res.xml;
        }
        if (!xml) {
          throw new Error('Диаграмма пуста или не скомпилирована');
        }
        const blob = new Blob([xml], { type: 'application/xml;charset=utf-8' });
        downloadBlob(blob, getDiagramFilename('bpmn'));
        showToast('Диаграмма экспортирована в BPMN 2.0 (.bpmn)', 'success');
      } catch (e) {
        console.error('BPMN Export failed:', e);
        showToast('Ошибка экспорта BPMN: ' + (e.message || e), 'error');
      }
    });
  }

  // Export SVG
  const exportSvgBtn = document.getElementById('export-svg-btn');
  if (exportSvgBtn) {
    exportSvgBtn.addEventListener('click', async () => {
      if (exportMenu) exportMenu.classList.remove('open');
      try {
        const { svg } = await getExportSvg();
        const blob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
        downloadBlob(blob, getDiagramFilename('svg'));
        showToast('Диаграмма экспортирована в SVG', 'success');
      } catch (e) {
        showToast('Ошибка экспорта SVG: ' + e.message, 'error');
      }
    });
  }

  // Export PNG
  const exportPngBtn = document.getElementById('export-png-btn');
  if (exportPngBtn) {
    exportPngBtn.addEventListener('click', async () => {
      if (exportMenu) exportMenu.classList.remove('open');
      try {
        const { svg, width, height } = await getExportSvg();

        const svgBlob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
        const url = URL.createObjectURL(svgBlob);

        const img = new Image();
        await new Promise((resolve, reject) => {
          img.onload = () => resolve();
          img.onerror = () => reject(new Error('Не удалось отрисовать SVG на холсте'));
          img.src = url;
        });

        const scale = 2;
        const canvas = document.createElement('canvas');
        canvas.width = width * scale;
        canvas.height = height * scale;
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        URL.revokeObjectURL(url);

        canvas.toBlob((blob) => {
          if (!blob) {
            showToast('Ошибка создания PNG файла', 'error');
            return;
          }
          downloadBlob(blob, getDiagramFilename('png'));
          showToast('Диаграмма экспортирована в PNG (2x)', 'success');
        }, 'image/png');
      } catch (e) {
        console.error('PNG Export failed:', e);
        showToast('Ошибка экспорта PNG: ' + (e.message || e), 'error');
      }
    });
  }

  // Export PDF (Reliable High-DPI Canvas-to-PDF Engine)
  const exportPdfBtn = document.getElementById('export-pdf-btn');
  if (exportPdfBtn) {
    exportPdfBtn.addEventListener('click', async () => {
      if (exportMenu) exportMenu.classList.remove('open');
      try {
        const { svg, width, height } = await getExportSvg();

        const orientation = width > height ? 'landscape' : 'portrait';
        const jsPdfClass = window.jspdf && window.jspdf.jsPDF ? window.jspdf.jsPDF : window.jsPDF;

        if (!jsPdfClass) {
          throw new Error('Библиотека jsPDF не загружена');
        }

        const pdf = new jsPdfClass({
          orientation: orientation,
          unit: 'pt',
          format: [width + 60, height + 60]
        });

        const scale = 2;
        const canvas = document.createElement('canvas');
        canvas.width = width * scale;
        canvas.height = height * scale;
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        const svgBlob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
        const url = URL.createObjectURL(svgBlob);
        const img = new Image();

        await new Promise((resolve, reject) => {
          img.onload = () => {
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            URL.revokeObjectURL(url);
            resolve();
          };
          img.onerror = () => {
            URL.revokeObjectURL(url);
            reject(new Error('Ошибка загрузки векторного изображения SVG'));
          };
          img.src = url;
        });

        const imgData = canvas.toDataURL('image/png');
        if (!imgData || imgData === 'data:,' || imgData.length < 50) {
          throw new Error('Не удалось сформировать растровое изображение диаграммы');
        }

        pdf.addImage(imgData, 'PNG', 30, 30, width, height);
        pdf.save(getDiagramFilename('pdf'));
        showToast('Диаграмма экспортирована в PDF', 'success');
      } catch (e) {
        console.error('PDF Export failed:', e);
        showToast('Ошибка экспорта PDF: ' + (e.message || e), 'error');
      }
    });
  }
  // Export DSL Code
  const exportDslBtn = document.getElementById('export-dsl-btn');
  if (exportDslBtn) {
    exportDslBtn.addEventListener('click', () => {
      if (exportMenu) exportMenu.classList.remove('open');
      const blob = new Blob([codeEditor ? codeEditor.value : ''], { type: 'text/plain;charset=utf-8' });
      downloadBlob(blob, getDiagramFilename('bac'));
      showToast('Код BPMN-as-Code экспортирован', 'success');
    });
  }

  // ── Theme Toggle ───────────────────────────────────────────────────────
  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('aibpmn_theme', theme);
  }

  if (themeToggleBtn) {
    themeToggleBtn.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme') || 'dark';
      applyTheme(current === 'dark' ? 'light' : 'dark');
    });
  }

  // ── Mobile View Toggle & More Menu ────────────────────────────────────
  function setMobileView(view) {
    if (view === 'canvas') {
      if (lastSourceOfChange === 'code') {
        clearTimeout(compileTimer);
        compileCode();
      }
      document.body.classList.remove('mobile-view-panel');
      document.body.classList.add('mobile-view-canvas');
      if (mobileBtnCanvas) {
        mobileBtnCanvas.classList.add('active');
      }
      if (mobileBtnPanel) {
        mobileBtnPanel.classList.remove('active');
      }
      if (modeler) {
        setTimeout(() => {
          safeFitViewport();
        }, 80);
      }
    } else {
      if (lastSourceOfChange === 'visual' && modeler && !isImporting) {
        clearTimeout(visualSyncTimer);
        modeler.saveXML({ format: true }).then(({ xml }) => {
          const newDsl = decompileXml(xml);
          if (newDsl && codeEditor) {
            codeEditor.value = newDsl;
            updateLineNumbers();
            updateDslHighlight();
          }
        }).catch(() => {});
      }
      document.body.classList.remove('mobile-view-canvas');
      document.body.classList.add('mobile-view-panel');
      if (mobileBtnPanel) {
        mobileBtnPanel.classList.add('active');
      }
      if (mobileBtnCanvas) {
        mobileBtnCanvas.classList.remove('active');
      }
    }
  }

  if (mobileBtnPanel) {
    mobileBtnPanel.addEventListener('click', () => setMobileView('panel'));
  }

  if (mobileBtnCanvas) {
    mobileBtnCanvas.addEventListener('click', () => setMobileView('canvas'));
  }

  // Mobile More Dropdown Handlers
  if (mobileMoreBtn && mobileMoreMenu) {
    mobileMoreBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      mobileMoreMenu.classList.toggle('open');
      if (mobileMoreMenu.classList.contains('open')) {
        if (exportMenu) exportMenu.classList.remove('open');
        adjustDropdownPosition(mobileMoreMenu);
      }
    });

    document.addEventListener('click', (e) => {
      if (!mobileMoreMenu.contains(e.target) && e.target !== mobileMoreBtn && !mobileMoreBtn.contains(e.target)) {
        mobileMoreMenu.classList.remove('open');
      }
    });

    window.addEventListener('resize', () => {
      if (exportMenu && exportMenu.classList.contains('open')) adjustDropdownPosition(exportMenu);
      if (mobileMoreMenu && mobileMoreMenu.classList.contains('open')) adjustDropdownPosition(mobileMoreMenu);
    });

    if (mobileKbBtn) {
      mobileKbBtn.addEventListener('click', () => {
        mobileMoreMenu.classList.remove('open');
        if (kbModalBtn) kbModalBtn.click();
      });
    }

    if (mobileThemeBtn) {
      mobileThemeBtn.addEventListener('click', () => {
        mobileMoreMenu.classList.remove('open');
        if (themeToggleBtn) themeToggleBtn.click();
      });
    }

    if (mobileDeleteChatBtn) {
      mobileDeleteChatBtn.addEventListener('click', () => {
        mobileMoreMenu.classList.remove('open');
        if (deleteChatBtn) deleteChatBtn.click();
      });
    }
  }

  // ── Import .bac (DSL) and .bpmn (XML) Files ────────────────────────────
  if (importDslBtn && importDslInput) {
    importDslBtn.addEventListener('click', () => {
      importDslInput.click();
    });

    importDslInput.addEventListener('change', async (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;

      if (file.size > 10 * 1024 * 1024) {
        showToast('Файл слишком велик (максимальный размер 10 МБ)', 'error');
        importDslInput.value = '';
        return;
      }

      const reader = new FileReader();
      reader.onload = async (ev) => {
        try {
          const text = ev.target.result || '';
          if (text.trim().startsWith('<')) {
            // BPMN 2.0 XML file
            await loadIntoModeler(text);
            const decomp = decompileXml(text);
            if (codeEditor && decomp) {
              codeEditor.value = decomp;
              updateLineNumbers();
              updateDslHighlight();
            }
            lastSourceOfChange = 'visual';
            await saveCurrentDiagram(true);
            showToast(`Файл BPMN XML «${file.name}» успешно импортирован`, 'success');
          } else {
            // DSL file
            if (codeEditor) {
              codeEditor.value = text;
              updateLineNumbers();
              updateDslHighlight();
            }
            lastSourceOfChange = 'code';
            const compResult = compileCode();
            if (compResult.valid) {
              await saveCurrentDiagram(true);
              showToast(`Файл DSL «${file.name}» успешно импортирован и сохранен`, 'success');
            } else {
              showToast(`Файл «${file.name}» импортирован, но содержит синтаксические ошибки`, 'warn');
            }
          }
        } catch (err) {
          showToast('Ошибка импорта файла: ' + err.message, 'error');
        } finally {
          importDslInput.value = '';
        }
      };
      reader.onerror = () => {
        showToast('Ошибка чтения DSL файла', 'error');
        importDslInput.value = '';
      };
      reader.readAsText(file);
    });
  }


  // ── Authentication & Password Complexity Rules ──────────────────────────
  const authTabBtns = document.querySelectorAll('.auth-tab-btn');
  const authLoginForm = document.getElementById('auth-login-form');
  const authRegisterForm = document.getElementById('auth-register-form');
  const authModalTitle = document.getElementById('auth-modal-title');
  const loginUsername = document.getElementById('login-username');
  const loginPassword = document.getElementById('login-password');
  const loginErrorMsg = document.getElementById('login-error-msg');
  const loginSubmitBtn = document.getElementById('login-submit-btn');

  const regUsername = document.getElementById('reg-username');
  const regPassword = document.getElementById('reg-password');
  const regPasswordConfirm = document.getElementById('reg-password-confirm');
  const regErrorMsg = document.getElementById('reg-error-msg');
  const regSubmitBtn = document.getElementById('reg-submit-btn');

  function setRuleStatus(id, isValid, isDirty) {
    const el = document.getElementById(id);
    if (!el) return;
    const textSpan = el.querySelector('span');
    const text = textSpan ? textSpan.textContent : '';
    let iconName = 'circle';
    if (isValid) {
      el.classList.add('valid');
      el.classList.remove('invalid');
      iconName = 'check-circle-2';
    } else if (isDirty) {
      el.classList.add('invalid');
      el.classList.remove('valid');
      iconName = 'x-circle';
    } else {
      el.classList.remove('valid', 'invalid');
      iconName = 'circle';
    }
    el.innerHTML = `<i data-lucide="${iconName}" class="rule-icon"></i><span>${escapeHtml(text)}</span>`;
    if (window.lucide) {
      window.lucide.createIcons({ root: el });
    }
  }

  function validateRegFormRealtime() {
    const u = (regUsername ? regUsername.value : '').trim();
    const p = regPassword ? regPassword.value : '';
    const pc = regPasswordConfirm ? regPasswordConfirm.value : '';

    const uDirty = u.length > 0;
    const pDirty = p.length > 0;
    const pcDirty = pc.length > 0;

    const validEnLogin = /^[a-zA-Z0-9_.-]+$/.test(u) && /[a-zA-Z]/.test(u) && u.length >= 3 && u.length <= 30;
    const validEnPwd = /^[a-zA-Z0-9!@#$%^&*()_+\-=\[\]{}|;:\'",./<>?~` ]+$/.test(p) && p.length > 0;
    const validLen = p.length >= 8;
    const validCase = /[A-Z]/.test(p) && /[a-z]/.test(p);
    const validDigitSym = /[0-9]/.test(p) && /[!@#$%^&*()_+\-=\[\]{}|;:\'",./<>?~` ]/.test(p);
    const validNoMatch = p.length > 0 && (!u || (p.toLowerCase() !== u.toLowerCase() && !p.toLowerCase().includes(u.toLowerCase())));
    const validConfirm = pc.length > 0 && pc === p;

    setRuleStatus('rule-en-login', validEnLogin, uDirty);
    setRuleStatus('rule-en-pwd', validEnPwd, pDirty);
    setRuleStatus('rule-len', validLen, pDirty);
    setRuleStatus('rule-case', validCase, pDirty);
    setRuleStatus('rule-digit-sym', validDigitSym, pDirty);
    setRuleStatus('rule-no-match', validNoMatch, pDirty);
    setRuleStatus('rule-confirm', validConfirm, pcDirty);

    return validEnLogin && validEnPwd && validLen && validCase && validDigitSym && validNoMatch && validConfirm;
  }

  function openAuthModal(tab = 'login') {
    if (!authModal) return;
    authModal.classList.add('open');
    switchAuthTab(tab);
    if (tab === 'login' && loginUsername && typeof loginUsername.focus === 'function') {
      setTimeout(() => loginUsername.focus(), 60);
    } else if (tab === 'register' && regUsername && typeof regUsername.focus === 'function') {
      setTimeout(() => regUsername.focus(), 60);
    }
  }

  function closeAuthModal() {
    if (!authModal) return;
    authModal.classList.remove('open');
    if (loginErrorMsg) loginErrorMsg.style.display = 'none';
    if (regErrorMsg) regErrorMsg.style.display = 'none';
  }

  function switchAuthTab(tab) {
    if (authTabBtns) {
      authTabBtns.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.authTab === tab);
      });
    }

    if (tab === 'register') {
      if (authLoginForm) authLoginForm.style.display = 'none';
      if (authRegisterForm) authRegisterForm.style.display = 'block';
      if (authModalTitle) authModalTitle.textContent = 'Регистрация учетной записи';
      validateRegFormRealtime();
    } else {
      if (authLoginForm) authLoginForm.style.display = 'block';
      if (authRegisterForm) authRegisterForm.style.display = 'none';
      if (authModalTitle) authModalTitle.textContent = 'Вход в систему';
    }
    refreshIcons();
  }

  if (openAuthBtn) {
    openAuthBtn.addEventListener('click', () => openAuthModal('login'));
  }
  if (mobileAuthBtn) {
    mobileAuthBtn.addEventListener('click', () => {
      if (mobileMoreMenu) mobileMoreMenu.classList.remove('open');
      openAuthModal('login');
    });
  }
  if (authModalClose) {
    authModalClose.addEventListener('click', closeAuthModal);
  }
  if (authModal) {
    authModal.addEventListener('click', (e) => {
      if (e.target === authModal) closeAuthModal();
    });
  }

  authTabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      switchAuthTab(btn.dataset.authTab);
    });
  });

  if (regUsername) regUsername.addEventListener('input', validateRegFormRealtime);
  if (regPassword) regPassword.addEventListener('input', validateRegFormRealtime);
  if (regPasswordConfirm) regPasswordConfirm.addEventListener('input', validateRegFormRealtime);

  // Login form submit
  if (authLoginForm) {
    authLoginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (loginErrorMsg) {
        loginErrorMsg.style.display = 'none';
        loginErrorMsg.textContent = '';
      }

      const username = (loginUsername ? loginUsername.value : '').trim();
      const password = loginPassword ? loginPassword.value : '';

      if (!username || !password) {
        if (loginErrorMsg) {
          loginErrorMsg.textContent = 'Введите логин и пароль.';
          loginErrorMsg.style.display = 'block';
        }
        return;
      }

      if (loginSubmitBtn) {
        loginSubmitBtn.disabled = true;
      }

      try {
        const resp = await fetch('/api/auth/login/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password })
        });
        const data = await resp.json();
        if (data.success) {
          showToast(`Вход выполнен! Добро пожаловать, ${data.user?.username || username}!`, 'success');
          setTimeout(() => {
            window.location.href = data.redirect || '/';
          }, 450);
        } else {
          if (loginErrorMsg) {
            loginErrorMsg.textContent = data.error || 'Неверный логин или пароль';
            loginErrorMsg.style.display = 'block';
          }
        }
      } catch (err) {
        if (loginErrorMsg) {
          loginErrorMsg.textContent = 'Ошибка сети при авторизации: ' + err.message;
          loginErrorMsg.style.display = 'block';
        }
      } finally {
        if (loginSubmitBtn) {
          loginSubmitBtn.disabled = false;
        }
      }
    });
  }

  // Register form submit
  if (authRegisterForm) {
    authRegisterForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (regErrorMsg) {
        regErrorMsg.style.display = 'none';
        regErrorMsg.textContent = '';
      }

      const isValid = validateRegFormRealtime();
      if (!isValid) {
        if (regErrorMsg) {
          regErrorMsg.textContent = 'Пожалуйста, выполните все требования к безопасности пароля и логина.';
          regErrorMsg.style.display = 'block';
        }
        return;
      }

      const username = (regUsername ? regUsername.value : '').trim();
      const password = regPassword ? regPassword.value : '';
      const passwordConfirm = regPasswordConfirm ? regPasswordConfirm.value : '';

      if (regSubmitBtn) {
        regSubmitBtn.disabled = true;
      }

      try {
        const resp = await fetch('/api/auth/register/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            username: username,
            password: password,
            password_confirm: passwordConfirm
          })
        });
        const data = await resp.json();
        if (data.success) {
          showToast(`Регистрация успешна! Добро пожаловать, ${data.user?.username || username}!`, 'success');
          setTimeout(() => {
            window.location.href = data.redirect || '/';
          }, 500);
        } else {
          if (regErrorMsg) {
            regErrorMsg.textContent = data.error || 'Ошибка при регистрации';
            regErrorMsg.style.display = 'block';
          }
        }
      } catch (err) {
        if (regErrorMsg) {
          regErrorMsg.textContent = 'Ошибка сети при регистрации: ' + err.message;
          regErrorMsg.style.display = 'block';
        }
      } finally {
        if (regSubmitBtn) {
          regSubmitBtn.disabled = false;
        }
      }
    });
  }

  // Logout handler
  async function handleLogout() {
    const confirmed = await showCustomConfirm(
      'Вы уверены, что хотите выйти из своей учетной записи?',
      'Выход из аккаунта',
      'Выйти',
      'Отмена'
    );
    if (!confirmed) return;

    try {
      const resp = await fetch('/api/auth/logout/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await resp.json();
      if (data.success) {
        showToast('Вы вышли из системы', 'info');
        setTimeout(() => {
          window.location.href = data.redirect || '/';
        }, 350);
      }
    } catch (err) {
      showToast('Ошибка при выходе: ' + err.message, 'error');
    }
  }

  if (logoutBtn) {
    logoutBtn.addEventListener('click', handleLogout);
  }
  if (mobileLogoutBtn) {
    mobileLogoutBtn.addEventListener('click', () => {
      if (mobileMoreMenu) mobileMoreMenu.classList.remove('open');
      handleLogout();
    });
  }

  // ── Profile Settings (Password Change & Account Deletion) ───────────────
  const userBadge = document.getElementById('user-badge');
  const mobileProfileBtn = document.getElementById('mobile-profile-btn');
  const profileModal = document.getElementById('profile-modal');
  const profileModalClose = document.getElementById('profile-modal-close');
  const profileTabBtns = document.querySelectorAll('[data-profile-tab]');
  const profilePasswordForm = document.getElementById('profile-password-form');
  const profileDeleteForm = document.getElementById('profile-delete-form');
  const profileOldPassword = document.getElementById('profile-old-password');
  const profileNewPassword = document.getElementById('profile-new-password');
  const profileNewPasswordConfirm = document.getElementById('profile-new-password-confirm');
  const profilePwdErrorMsg = document.getElementById('profile-pwd-error-msg');
  const profilePwdSubmitBtn = document.getElementById('profile-pwd-submit-btn');
  const profileDeletePassword = document.getElementById('profile-delete-password');
  const profileDeleteConfirmCheck = document.getElementById('profile-delete-confirm-check');
  const profileDelErrorMsg = document.getElementById('profile-del-error-msg');
  const profileDelSubmitBtn = document.getElementById('profile-del-submit-btn');

  function validateProfilePwdRealtime() {
    const currentUsername = (window.INITIAL_DATA && window.INITIAL_DATA.username) || '';
    const p = profileNewPassword ? profileNewPassword.value : '';
    const pc = profileNewPasswordConfirm ? profileNewPasswordConfirm.value : '';

    const pDirty = p.length > 0;
    const pcDirty = pc.length > 0;

    const validEnPwd = /^[a-zA-Z0-9!@#$%^&*()_+\-=\[\]{}|;:\'",./<>?~` ]+$/.test(p) && p.length > 0;
    const validLen = p.length >= 8;
    const validCase = /[A-Z]/.test(p) && /[a-z]/.test(p);
    const validDigitSym = /[0-9]/.test(p) && /[!@#$%^&*()_+\-=\[\]{}|;:\'",./<>?~` ]/.test(p);
    const validNoMatch = p.length > 0 && (!currentUsername || (p.toLowerCase() !== currentUsername.toLowerCase() && !p.toLowerCase().includes(currentUsername.toLowerCase())));
    const validConfirm = pc.length > 0 && pc === p;

    setRuleStatus('prule-en-pwd', validEnPwd, pDirty);
    setRuleStatus('prule-len', validLen, pDirty);
    setRuleStatus('prule-case', validCase, pDirty);
    setRuleStatus('prule-digit-sym', validDigitSym, pDirty);
    setRuleStatus('prule-no-match', validNoMatch, pDirty);
    setRuleStatus('prule-confirm', validConfirm, pcDirty);

    return validEnPwd && validLen && validCase && validDigitSym && validNoMatch && validConfirm;
  }

  function openProfileModal(tab = 'password') {
    if (!profileModal) return;
    profileModal.classList.add('open');
    switchProfileTab(tab);
    if (tab === 'password' && profileOldPassword && typeof profileOldPassword.focus === 'function') {
      setTimeout(() => profileOldPassword.focus(), 60);
    }
  }

  function closeProfileModal() {
    if (!profileModal) return;
    profileModal.classList.remove('open');
    if (profilePwdErrorMsg) profilePwdErrorMsg.style.display = 'none';
    if (profileDelErrorMsg) profileDelErrorMsg.style.display = 'none';
    if (profilePasswordForm) profilePasswordForm.reset();
    if (profileDeleteForm) profileDeleteForm.reset();
    validateProfilePwdRealtime();
  }

  function switchProfileTab(tab) {
    if (profileTabBtns) {
      profileTabBtns.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.profileTab === tab);
      });
    }

    if (tab === 'delete') {
      if (profilePasswordForm) profilePasswordForm.style.display = 'none';
      if (profileDeleteForm) profileDeleteForm.style.display = 'block';
    } else {
      if (profilePasswordForm) profilePasswordForm.style.display = 'block';
      if (profileDeleteForm) profileDeleteForm.style.display = 'none';
      validateProfilePwdRealtime();
    }
    refreshIcons();
  }

  if (userBadge) {
    userBadge.addEventListener('click', () => openProfileModal('password'));
  }
  if (mobileProfileBtn) {
    mobileProfileBtn.addEventListener('click', () => {
      if (mobileMoreMenu) mobileMoreMenu.classList.remove('open');
      openProfileModal('password');
    });
  }
  if (profileModalClose) {
    profileModalClose.addEventListener('click', closeProfileModal);
  }
  if (profileModal) {
    profileModal.addEventListener('click', (e) => {
      if (e.target === profileModal) closeProfileModal();
    });
  }

  profileTabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      switchProfileTab(btn.dataset.profileTab);
    });
  });

  if (profileNewPassword) profileNewPassword.addEventListener('input', validateProfilePwdRealtime);
  if (profileNewPasswordConfirm) profileNewPasswordConfirm.addEventListener('input', validateProfilePwdRealtime);

  // Profile change password submit
  if (profilePasswordForm) {
    profilePasswordForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (profilePwdErrorMsg) {
        profilePwdErrorMsg.style.display = 'none';
        profilePwdErrorMsg.textContent = '';
      }

      const isValid = validateProfilePwdRealtime();
      if (!isValid) {
        if (profilePwdErrorMsg) {
          profilePwdErrorMsg.textContent = 'Пожалуйста, выполните все требования к надежности пароля.';
          profilePwdErrorMsg.style.display = 'block';
        }
        return;
      }

      const oldPassword = profileOldPassword ? profileOldPassword.value : '';
      const newPassword = profileNewPassword ? profileNewPassword.value : '';
      const newPasswordConfirm = profileNewPasswordConfirm ? profileNewPasswordConfirm.value : '';

      if (!oldPassword || !newPassword) {
        if (profilePwdErrorMsg) {
          profilePwdErrorMsg.textContent = 'Заполните все поля.';
          profilePwdErrorMsg.style.display = 'block';
        }
        return;
      }

      if (profilePwdSubmitBtn) {
        profilePwdSubmitBtn.disabled = true;
      }

      try {
        const resp = await fetch('/api/auth/change-password/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            old_password: oldPassword,
            new_password: newPassword,
            new_password_confirm: newPasswordConfirm
          })
        });
        const data = await resp.json();
        if (data.success) {
          showToast(data.message || 'Пароль успешно обновлен!', 'success');
          closeProfileModal();
        } else {
          if (profilePwdErrorMsg) {
            profilePwdErrorMsg.textContent = data.error || 'Ошибка смены пароля';
            profilePwdErrorMsg.style.display = 'block';
          }
        }
      } catch (err) {
        if (profilePwdErrorMsg) {
          profilePwdErrorMsg.textContent = 'Ошибка сети: ' + err.message;
          profilePwdErrorMsg.style.display = 'block';
        }
      } finally {
        if (profilePwdSubmitBtn) {
          profilePwdSubmitBtn.disabled = false;
        }
      }
    });
  }

  // Profile delete account submit
  if (profileDeleteForm) {
    profileDeleteForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (profileDelErrorMsg) {
        profileDelErrorMsg.style.display = 'none';
        profileDelErrorMsg.textContent = '';
      }

      const password = profileDeletePassword ? profileDeletePassword.value : '';
      const isConfirmed = profileDeleteConfirmCheck ? profileDeleteConfirmCheck.checked : false;

      if (!password) {
        if (profileDelErrorMsg) {
          profileDelErrorMsg.textContent = 'Введите текущий пароль для подтверждения.';
          profileDelErrorMsg.style.display = 'block';
        }
        return;
      }

      if (!isConfirmed) {
        if (profileDelErrorMsg) {
          profileDelErrorMsg.textContent = 'Необходимо подтвердить флажок удаления аккаунта.';
          profileDelErrorMsg.style.display = 'block';
        }
        return;
      }

      const userConfirmed = await showCustomConfirm(
        'Внимание! Все ваши проекты, схемы и база знаний будут навсегда удалены без возможности восстановления. Вы точно уверены?',
        'Безвозвратное удаление аккаунта',
        'Да, удалить навсегда',
        'Отмена'
      );
      if (!userConfirmed) return;

      if (profileDelSubmitBtn) {
        profileDelSubmitBtn.disabled = true;
      }

      try {
        const resp = await fetch('/api/auth/delete-account/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password })
        });
        const data = await resp.json();
        if (data.success) {
          showToast('Аккаунт успешно удален', 'info');
          setTimeout(() => {
            window.location.href = data.redirect || '/';
          }, 450);
        } else {
          if (profileDelErrorMsg) {
            profileDelErrorMsg.textContent = data.error || 'Ошибка удаления аккаунта';
            profileDelErrorMsg.style.display = 'block';
          }
        }
      } catch (err) {
        if (profileDelErrorMsg) {
          profileDelErrorMsg.textContent = 'Ошибка сети: ' + err.message;
          profileDelErrorMsg.style.display = 'block';
        }
      } finally {
        if (profileDelSubmitBtn) {
          profileDelSubmitBtn.disabled = false;
        }
      }
    });
  }

  // ── DSL Documentation Modal ─────────────────────────────────────────────
  const dslDocsBtn = document.getElementById('dsl-docs-btn');
  const dslDocsModal = document.getElementById('dsl-docs-modal');
  const dslDocsClose = document.getElementById('dsl-docs-close');
  const dslDocTabBtns = document.querySelectorAll('.dsl-doc-tab-btn');
  const dslDocSections = document.querySelectorAll('.dsl-doc-section');

  function openDslDocsModal(tab = 'quickstart') {
    if (!dslDocsModal) return;
    dslDocsModal.classList.add('open');
    switchDslDocTab(tab);
    refreshIcons();
  }

  function closeDslDocsModal() {
    if (!dslDocsModal) return;
    dslDocsModal.classList.remove('open');
  }

  function switchDslDocTab(tab) {
    if (dslDocTabBtns) {
      dslDocTabBtns.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.docTab === tab);
      });
    }
    if (dslDocSections) {
      dslDocSections.forEach(sec => {
        sec.classList.toggle('active', sec.id === `dsl-doc-${tab}`);
      });
    }
    refreshIcons();
  }

  if (dslDocsBtn) {
    dslDocsBtn.addEventListener('click', () => openDslDocsModal('quickstart'));
  }
  if (dslDocsClose) {
    dslDocsClose.addEventListener('click', closeDslDocsModal);
  }
  if (dslDocsModal) {
    dslDocsModal.addEventListener('click', (e) => {
      if (e.target === dslDocsModal) closeDslDocsModal();
    });
  }

  dslDocTabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      switchDslDocTab(btn.dataset.docTab);
    });
  });

  // Copy sample code
  document.querySelectorAll('.btn-copy-sample').forEach(btn => {
    btn.addEventListener('click', async () => {
      const targetId = btn.dataset.target;
      const targetEl = document.getElementById(targetId);
      if (!targetEl) return;
      const code = targetEl.textContent.trim();
      try {
        await navigator.clipboard.writeText(code);
        showToast('Пример скопирован в буфер обмена!', 'success');
      } catch (err) {
        showToast('Не удалось скопировать: ' + err.message, 'error');
      }
    });
  });

  // Insert sample code into editor
  document.querySelectorAll('.btn-insert-sample').forEach(btn => {
    btn.addEventListener('click', async () => {
      const targetId = btn.dataset.target;
      const targetEl = document.getElementById(targetId);
      if (!targetEl || !codeEditor) return;
      const code = targetEl.textContent.trim();

      if (codeEditor.value && codeEditor.value.trim().length > 0) {
        const replaceOk = await showCustomConfirm(
          'Заменить текущий код в редакторе этим примером?',
          'Вставка примера процесса',
          'Заменить код',
          'Отмена'
        );
        if (!replaceOk) return;
      }

      codeEditor.value = code;
      updateLineNumbers();
      updateDslHighlight();
      compileCode();
      closeDslDocsModal();
      switchUnifiedTab('tab-dsl');
      showToast('Пример успешно вставлен в редактор!', 'success');
    });
  });

  // Close modals on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if (profileModal && profileModal.classList.contains('open')) {
        closeProfileModal();
      }
      if (dslDocsModal && dslDocsModal.classList.contains('open')) {
        closeDslDocsModal();
      }
      if (authModal && authModal.classList.contains('open')) {
        closeAuthModal();
      }
    }
  });

  // ── Cookie Consent Banner ───────────────────────────────────────────────
  const cookieBanner = document.getElementById('cookie-consent-banner');
  const cookieAcceptBtn = document.getElementById('cookie-accept-btn');

  if (cookieBanner) {
    const consent = localStorage.getItem('aibpmn_cookie_consent');
    if (!consent) {
      cookieBanner.style.display = 'block';
    } else {
      cookieBanner.style.display = 'none';
    }

    if (cookieAcceptBtn) {
      cookieAcceptBtn.addEventListener('click', () => {
        localStorage.setItem('aibpmn_cookie_consent', 'accepted_' + Date.now());
        cookieBanner.style.opacity = '0';
        cookieBanner.style.transition = 'opacity 0.25s ease';
        setTimeout(() => {
          cookieBanner.style.display = 'none';
        }, 260);
        showToast('Настройки cookie сохранены', 'info');
      });
    }
  }

  // Set default view on load & resize
  function checkMobileViewport() {
    if (window.innerWidth <= 800) {
      if (!document.body.classList.contains('mobile-view-canvas') && !document.body.classList.contains('mobile-view-panel')) {
        setMobileView('panel');
      }
    } else {
      document.body.classList.remove('mobile-view-panel', 'mobile-view-canvas');
      if (modeler) {
        try {
          modeler.get('canvas').resized();
        } catch (e) { }
      }
    }
  }

  window.addEventListener('resize', checkMobileViewport);
  checkMobileViewport();

  // ── Initial Load ───────────────────────────────────────────────────────
  if (currentDiagramId && currentDiagramId !== 0) {
    loadDiagram(currentDiagramId);
  } else {
    if (window.INITIAL_DATA && window.INITIAL_DATA.messages && window.INITIAL_DATA.messages.length > 0) {
      if (chatContainer) chatContainer.innerHTML = '';
      window.INITIAL_DATA.messages.forEach(appendChatMessage);
    }
    if (codeEditor && codeEditor.value && codeEditor.value.trim()) {
      updateLineNumbers();
      updateDslHighlight();
      compileCode();
    }
  }

  switchUnifiedTab('tab-chat');

  // ── PWA Service Worker Registration ─────────────────────────────────────
  if ('serviceWorker' in navigator && (window.location.protocol === 'https:' || window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js', { scope: '/' })
        .then((reg) => {
          console.log('[PWA] ServiceWorker registered with scope:', reg.scope);
        })
        .catch((err) => {
          console.warn('[PWA] ServiceWorker registration failed:', err);
        });
    });
  }

  // Final icons pass
  refreshIcons();

  // ── Global Handlers for Edge / Chromium PWA ─────────────────────────────
  // Prevent middle-click (auxclick) on UI elements from opening about:blank in Edge
  document.addEventListener('auxclick', (e) => {
    if (e.target.closest('#sidebar-drawer, .navbar, .modal, .sidebar-project-header, .sidebar-chat-item, .sidebar-footer, a[href]')) {
      e.preventDefault();
      e.stopPropagation();
    }
  });

  // Ensure internal link clicks (e.g. /terms/, /privacy/, /) stay in the same window/PWA
  document.addEventListener('click', (e) => {
    if (e.button !== 0) return;
    const link = e.target.closest('a[href]');
    if (!link) return;
    const href = link.getAttribute('href');
    if (!href) return;
    if (href.startsWith('/') && !href.startsWith('//') && !link.hasAttribute('target') && !link.hasAttribute('download')) {
      if (!href.startsWith('/api/') && !href.startsWith('/admin/')) {
        e.preventDefault();
        e.stopPropagation();
        window.location.assign(href);
      }
    }
  });
});
