/* A small progressive editor: content remains editable without JavaScript. */
document.querySelectorAll('[data-cover-crop]').forEach((editor) => {
  const prefix = editor.dataset.prefix;
  const field = document.getElementById(`${prefix}_position`);
  const zoomField = document.getElementById(`${prefix}_zoom`);
  const source = document.getElementById(editor.dataset.source);
  const upload = document.getElementById(editor.dataset.upload);
  const frame = editor.querySelector('.cover-crop');
  const image = frame.querySelector('img');
  const selection = frame.querySelector('.crop-selection');
  const center = editor.querySelector('[data-crop-center]');
  const messages = ['empty', 'loading', 'error'];
  let position = (field.value || '50% 50%').split(/\s+/).map(parseFloat);
  if (position.length !== 2 || position.some(value => !Number.isFinite(value))) position = [50, 50];
  let zoom = Math.max(1, Math.min(10, Number(zoomField.value) || 1));
  let rect;
  const ratio = Number(editor.dataset.ratio);
  const circular = editor.classList.contains('circular-crop');
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  let drag = null;
  let revision = 0;
  let timer;

  function status(name) {
    messages.forEach(key => { editor.querySelector(`[data-crop-${key}]`).hidden = key !== name; });
  }
  function maxWidth() {
    return Math.min(image.naturalWidth, image.naturalHeight * ratio);
  }
  function render(save = false) {
    if (!rect) return;
    selection.style.left = `${rect.x / image.naturalWidth * 100}%`;
    selection.style.top = `${rect.y / image.naturalHeight * 100}%`;
    selection.style.width = `${rect.w / image.naturalWidth * 100}%`;
    selection.style.height = `${rect.w / ratio / image.naturalHeight * 100}%`;
    if (save) {
      position = [image.naturalWidth - rect.w > 0.001 ? rect.x / (image.naturalWidth - rect.w) * 100 : 50,
        image.naturalHeight - rect.w / ratio > 0.001 ? rect.y / (image.naturalHeight - rect.w / ratio) * 100 : 50];
      zoom = maxWidth() / rect.w;
      field.value = position.map(value => `${Number(value.toFixed(6))}%`).join(' ');
      zoomField.value = zoom.toFixed(6);
    }
  }
  function move(x, y, w = rect.w) {
    w = clamp(w, maxWidth() / 10, maxWidth());
    rect = { x: clamp(x, 0, image.naturalWidth - w), y: clamp(y, 0, image.naturalHeight - w / ratio), w };
    render(true);
  }
  function previewURL(value) {
    value = value.trim();
    if (value.startsWith('assets/')) value = '/' + value;
    const url = new URL(value, location.origin);
    if (!(url.protocol === 'https:' || (url.origin === location.origin && value.startsWith('/')))) throw new Error();
    if (url.hostname === 'drive.google.com') {
      const id = url.pathname.match(/^\/file\/d\/([\w-]+)/)?.[1] || url.searchParams.get('id');
      if (!id || !/^[\w-]+$/.test(id)) throw new Error();
      return `https://lh3.googleusercontent.com/d/${id}=s1600`;
    }
    return url.href;
  }
  function refresh() {
    const current = ++revision;
    frame.hidden = center.hidden = true;
    image.removeAttribute('src');
    const file = upload.files[0];
    status(file || source.value.trim() ? 'loading' : 'empty');
    if (file) {
      const reader = new FileReader();
      reader.onload = () => { if (current === revision) image.src = reader.result; };
      reader.onerror = () => { if (current === revision) status('error'); };
      reader.readAsDataURL(file);
    } else if (source.value.trim()) {
      try { image.src = previewURL(source.value); } catch { status('error'); }
    }
  }
  image.addEventListener('load', () => {
    frame.hidden = center.hidden = false;
    const w = maxWidth() / zoom;
    rect = { w, x: (image.naturalWidth - w) * clamp(position[0], 0, 100) / 100,
      y: (image.naturalHeight - w / ratio) * clamp(position[1], 0, 100) / 100 };
    render();
    status(null);
  });
  image.addEventListener('error', () => {
    if (!image.hasAttribute('src')) return;
    frame.hidden = center.hidden = true;
    status('error');
  });
  source.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(refresh, 200); });
  upload.addEventListener('change', refresh);
  center.addEventListener('click', () => {
    const w = maxWidth();
    move((image.naturalWidth - w) / 2, (image.naturalHeight - w / ratio) / 2, w);
  });
  function circleEdge(event) {
    if (!circular || !rect) return null;
    const bounds = selection.getBoundingClientRect();
    const dx = event.clientX - bounds.left - bounds.width / 2;
    const dy = event.clientY - bounds.top - bounds.height / 2;
    if (Math.abs(Math.hypot(dx, dy) - bounds.width / 2) > 8) return null;
    return Math.abs(dx) > Math.abs(dy) * 2 ? 'ew-resize'
      : Math.abs(dy) > Math.abs(dx) * 2 ? 'ns-resize'
      : dx * dy > 0 ? 'nwse-resize' : 'nesw-resize';
  }
  frame.addEventListener('pointerdown', event => {
    if (!event.isPrimary || event.button !== 0 || !event.target.closest('.crop-selection')) return;
    event.preventDefault();
    frame.focus({ preventScroll: true });
    frame.setPointerCapture(event.pointerId);
    drag = { id: event.pointerId, x: event.clientX, y: event.clientY, rect: { ...rect },
      corner: event.target.dataset.corner, scale: image.naturalWidth / frame.clientWidth };
    if (circleEdge(event)) {
      const bounds = frame.getBoundingClientRect();
      const x = rect.x + rect.w / 2, y = rect.y + rect.w / 2;
      drag.circle = { x, y, distance: Math.hypot((event.clientX - bounds.left) * drag.scale - x,
        (event.clientY - bounds.top) * drag.scale - y) };
    }
    frame.classList.add('is-dragging');
  });
  frame.addEventListener('pointermove', event => {
    if (!drag) {
      if (circular) selection.style.cursor = circleEdge(event) || 'grab';
      return;
    }
    if (event.pointerId !== drag.id) return;
    if (drag.circle) {
      const bounds = frame.getBoundingClientRect();
      const { x, y, distance } = drag.circle;
      const radius = Math.hypot((event.clientX - bounds.left) * drag.scale - x,
        (event.clientY - bounds.top) * drag.scale - y);
      const maximum = Math.min(x, y, image.naturalWidth - x, image.naturalHeight - y) * 2;
      const width = clamp(drag.rect.w + 2 * (radius - distance), maxWidth() / 10, maximum);
      return move(x - width / 2, y - width / 2, width);
    }
    const dx = (event.clientX - drag.x) * drag.scale;
    const dy = (event.clientY - drag.y) * drag.scale;
    const start = drag.rect;
    if (!drag.corner) return move(start.x + dx, start.y + dy);
    const sx = drag.corner.includes('e') ? 1 : -1;
    const sy = drag.corner.includes('s') ? 1 : -1;
    const ax = start.x + (sx < 0 ? start.w : 0);
    const ay = start.y + (sy < 0 ? start.w / ratio : 0);
    const maximum = Math.min(sx > 0 ? image.naturalWidth - ax : ax,
      (sy > 0 ? image.naturalHeight - ay : ay) * ratio);
    const width = clamp(start.w + (sx * dx + sy * dy / ratio) / (1 + 1 / ratio ** 2), maxWidth() / 10, maximum);
    move(sx > 0 ? ax : ax - width, sy > 0 ? ay : ay - width / ratio, width);
  });
  for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) {
    frame.addEventListener(type, () => { drag = null; frame.classList.remove('is-dragging'); });
  }
  frame.addEventListener('keydown', event => {
    if (event.key === '+' || event.key === '-' || event.key === '=') {
      event.preventDefault();
      const w = clamp(rect.w * (event.key === '-' ? 0.95 : 1.05), maxWidth() / 10, maxWidth());
      return move(rect.x + (rect.w - w) / 2, rect.y + (rect.w - w) / ratio / 2, w);
    }
    const directions = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
    if (!directions[event.key]) return;
    event.preventDefault();
    const step = maxWidth() * (event.shiftKey ? 0.05 : 0.01);
    move(rect.x + directions[event.key][0] * step, rect.y + directions[event.key][1] * step);
  });
  refresh();
});

document.querySelectorAll("textarea[data-richtext]").forEach((textarea) => {
  const wrapper = document.createElement("div");
  wrapper.className = "rich-editor";
  const toolbar = document.createElement("div");
  toolbar.className = "editor-toolbar";
  toolbar.setAttribute("role", "toolbar");
  toolbar.setAttribute("aria-label", "Formattazione del testo");
  const editor = document.createElement("div");
  editor.className = "editor-content";
  editor.contentEditable = "true";
  editor.setAttribute("role", "textbox");
  editor.setAttribute("aria-multiline", "true");
  editor.setAttribute(
    "aria-label",
    document.querySelector(`label[for="${textarea.id}"]`)?.textContent ||
      "Testo",
  );
  if (textarea.required) editor.setAttribute("aria-required", "true");

  // Copy only editorial markup, including when redisplaying an invalid form.
  const allowed = new Set([
    "P",
    "BR",
    "DIV",
    "SPAN",
    "STRONG",
    "B",
    "EM",
    "I",
    "U",
    "UL",
    "OL",
    "LI",
    "BLOCKQUOTE",
    "H2",
    "H3",
    "H4",
    "A",
    "IMG",
    "FIGURE",
    "FIGCAPTION",
  ]);
  function safeHref(value) {
    return /^(https?:\/\/|mailto:|tel:|\/(?!\/)|#)/i.test(value) ? value : null;
  }
  function copySafe(node, destination) {
    if (node.nodeType === Node.TEXT_NODE) {
      destination.append(document.createTextNode(node.textContent));
      return;
    }
    if (
      node.nodeType !== Node.ELEMENT_NODE ||
      ["SCRIPT", "STYLE", "IFRAME", "OBJECT", "SVG", "MATH"].includes(
        node.tagName,
      )
    )
      return;
    const target = allowed.has(node.tagName)
      ? document.createElement(node.tagName.toLowerCase())
      : document.createDocumentFragment();
    if (node.tagName === "A") {
      const href = safeHref(node.getAttribute("href") || "");
      if (href) target.setAttribute("href", href);
    }
    if (node.tagName === "IMG") {
      const src = node.getAttribute("src") || "";
      if (!/^(https?:\/\/|\/(?!\/))/i.test(src)) return;
      target.setAttribute("src", src);
      target.setAttribute("alt", node.getAttribute("alt") || "");
      ["width", "height"].forEach((attribute) => {
        const value = node.getAttribute(attribute);
        if (/^\d{1,4}$/.test(value || ""))
          target.setAttribute(attribute, value);
      });
    }
    if (
      target.nodeType === Node.ELEMENT_NODE &&
      /^[\w\s-]+$/.test(node.className || "")
    )
      target.className = node.className;
    Array.from(node.childNodes).forEach((child) => copySafe(child, target));
    destination.append(target);
  }
  const parsed = new DOMParser().parseFromString(textarea.value, "text/html");
  Array.from(parsed.body.childNodes).forEach((node) => copySafe(node, editor));

  [
    ["bold", "Grassetto", "G"],
    ["italic", "Corsivo", "C"],
    ["insertUnorderedList", "Elenco puntato", "• Elenco"],
    ["insertOrderedList", "Elenco numerato", "1. Elenco"],
    ["createLink", "Inserisci collegamento", "Link"],
    ["removeFormat", "Rimuovi formattazione", "Testo semplice"],
  ].forEach(([command, label, text]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = text;
    button.title = label;
    button.setAttribute("aria-label", label);
    if (command === "bold") button.style.fontWeight = "700";
    if (command === "italic") button.style.fontStyle = "italic";
    button.addEventListener("mousedown", (event) => event.preventDefault());
    button.addEventListener("click", () => {
      editor.focus();
      if (command === "createLink") {
        const value = window.prompt("Indirizzo del collegamento (https://…):");
        if (value && safeHref(value.trim()))
          document.execCommand(command, false, value.trim());
      } else {
        document.execCommand(command, false, null);
      }
    });
    toolbar.append(button);
  });
  editor.addEventListener("paste", (event) => {
    event.preventDefault();
    document.execCommand(
      "insertText",
      false,
      event.clipboardData.getData("text/plain"),
    );
  });
  editor.addEventListener("drop", (event) => event.preventDefault());
  wrapper.append(toolbar, editor);
  textarea.after(wrapper);
  textarea.hidden = true;
  const required = textarea.required;
  textarea.required = false;
  textarea.form.addEventListener("submit", (event) => {
    if (required && !editor.textContent.trim()) {
      event.preventDefault();
      editor.focus();
      editor.setAttribute("aria-invalid", "true");
      return;
    }
    editor.removeAttribute("aria-invalid");
    textarea.value = editor.innerHTML;
  });
});

document.querySelectorAll("form[data-photo-visibility]").forEach((form) => {
  const checkbox = form.querySelector('input[name="hidden"]');
  const card = form.closest('.photo-card');
  const error = form.querySelector('[data-visibility-error]');
  let lastSaved = checkbox.checked;
  form.querySelector('button[type="submit"]:not([data-cover-button])').hidden = true;
  checkbox.addEventListener('change', () => form.requestSubmit());
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const body = new FormData(form);
    checkbox.disabled = true;
    error.hidden = true;
    try {
      const response = await fetch(form.action, {
        method: 'POST', body, headers: { Accept: 'application/json' },
        credentials: 'same-origin',
      });
      if (!response.ok || response.redirected) throw new Error('save_failed');
      const result = await response.json();
      if (typeof result.published !== 'boolean') throw new Error('invalid_response');
      lastSaved = checkbox.checked = !result.published;
      card.classList.toggle('is-hidden', lastSaved);
    } catch {
      checkbox.checked = lastSaved;
      error.hidden = false;
    } finally {
      checkbox.disabled = false;
    }
  });
});

document.querySelectorAll('form[data-photo-cover]').forEach((form) => {
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const buttons = [...document.querySelectorAll('[data-cover-button]')];
    if (buttons.some(button => button.disabled)) return;
    buttons.forEach(button => { button.disabled = true; });
    const error = form.querySelector('[data-cover-error]');
    error.hidden = true;
    try {
      const response = await fetch(form.action, {
        method: 'POST', body: new FormData(form), credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      });
      if (!response.ok || response.redirected) throw new Error('save_failed');
      const result = await response.json();
      if (String(result.photo_id) !== form.dataset.photoId) throw new Error('invalid_response');
      buttons.forEach(button => button.setAttribute('aria-pressed', String(button.form === form)));
    } catch {
      error.hidden = false;
    } finally {
      buttons.forEach(button => { button.disabled = false; });
    }
  });
});

document.querySelectorAll('form[data-publication]').forEach((form) => {
  const checkbox = form.querySelector('input[name="hidden"]');
  const error = form.querySelector('[data-publication-error]');
  let lastSaved = checkbox.checked;
  form.querySelector('button[type="submit"]').hidden = true;
  checkbox.addEventListener('change', () => form.requestSubmit());
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const body = new FormData(form);
    checkbox.disabled = true;
    error.hidden = true;
    try {
      const response = await fetch(form.action, {
        method: 'POST', body, headers: { Accept: 'application/json' },
        credentials: 'same-origin',
      });
      if (!response.ok || response.redirected) throw new Error('save_failed');
      const result = await response.json();
      if (typeof result.published !== 'boolean') throw new Error('invalid_response');
      lastSaved = checkbox.checked = !result.published;
      form.closest('.content-row').classList.toggle('is-unpublished', lastSaved);
    } catch {
      checkbox.checked = lastSaved;
      error.hidden = false;
    } finally {
      checkbox.disabled = false;
    }
  });
});

document.querySelectorAll('.content-list').forEach((list) => {
  const forms = [...list.querySelectorAll('form.order-actions')];
  if (!forms.length) return;
  let busy = false;
  forms.forEach((form) => form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = event.submitter;
    if (busy || !button || button.disabled) return;
    busy = true;
    const body = new FormData(form);
    body.set('direction', button.value);
    list.setAttribute('aria-busy', 'true');
    forms.forEach((item) => {
      item.querySelector('[data-order-error]').hidden = true;
      item.querySelectorAll('button').forEach((control) => { control.disabled = true; });
    });
    try {
      const response = await fetch(form.action, {
        method: 'POST', body, headers: { Accept: 'application/json' },
        credentials: 'same-origin',
      });
      if (!response.ok || response.redirected) throw new Error('save_failed');
      const result = await response.json();
      const rows = new Map([...list.children].map((row) => [row.id, row]));
      if (!Array.isArray(result.ids) || result.ids.length !== rows.size ||
          new Set(result.ids).size !== rows.size ||
          result.ids.some((id) => !rows.has(`entry-${id}`))) throw new Error('stale_list');
      result.ids.forEach((id) => list.append(rows.get(`entry-${id}`)));
    } catch {
      form.querySelector('[data-order-error]').hidden = false;
    } finally {
      [...list.children].forEach((row, index) => {
        row.querySelector('button[value="up"]').disabled = index === 0;
        row.querySelector('button[value="down"]').disabled = index === list.children.length - 1;
      });
      list.setAttribute('aria-busy', 'false');
      busy = false;
      const focusTarget = button.disabled
        ? form.querySelector('button:not(:disabled)') : button;
      if (focusTarget) focusTarget.focus({ preventScroll: true });
    }
  }));
});

document.querySelectorAll("button[data-pending-label]").forEach((button) => {
  button.form.addEventListener("submit", () => {
    button.disabled = true;
    button.textContent = button.dataset.pendingLabel;
  });
});

// Compare actual form values, including crops and rich text, so undoing changes
// restores the clean state. Autosaving controls are deliberately not tracked.
(() => {
  const forms = [...document.querySelectorAll('form.edit-form, .photo-add form')];
  if (!forms.length) return;
  function snapshot(form) {
    const values = [...form.elements].filter(field =>
      field.name && field.name !== 'csrf_token' && field.matches('input, textarea, select') &&
      !['submit', 'button', 'reset'].includes(field.type)
    ).map(field => {
      if (field.type === 'file') {
        return [field.name, [...field.files].map(file => [file.name, file.size, file.lastModified])];
      }
      if (field.type === 'checkbox' || field.type === 'radio') return [field.name, field.value, field.checked];
      if (field.multiple) return [field.name, [...field.selectedOptions].map(option => option.value)];
      return [field.name, field.value];
    });
    const richText = [...form.querySelectorAll('.editor-content')].map(editor => editor.innerHTML);
    return JSON.stringify([values, richText]);
  }
  const initial = new Map(forms.map(form => [form, snapshot(form)]));
  const rejectedSubmission = document.body.dataset.unsavedForm === 'true';
  let submitting = null;
  document.addEventListener('submit', event => {
    // Runs after form validation and the rich-text editor's submit handler.
    if (!event.defaultPrevented && forms.includes(event.target)) submitting = event.target;
  });
  window.addEventListener('pageshow', () => { submitting = null; });
  window.addEventListener('beforeunload', event => {
    if (!forms.some(form => form !== submitting && (rejectedSubmission || snapshot(form) !== initial.get(form)))) return;
    event.preventDefault();
    event.returnValue = '';
  });
})();
