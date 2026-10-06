/* A small progressive editor: content remains editable without JavaScript. */
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
      card.classList.toggle('is-hidden', lastSaved);
    } catch {
      checkbox.checked = lastSaved;
      error.hidden = false;
    } finally {
      checkbox.disabled = false;
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
