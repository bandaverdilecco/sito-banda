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

document.querySelectorAll("button[data-pending-label]").forEach((button) => {
  button.form.addEventListener("submit", () => {
    button.disabled = true;
    button.textContent = button.dataset.pendingLabel;
  });
});
