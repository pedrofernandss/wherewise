/* Chat flutuante da Mbula ("chuva" em lingala), a assistente hídrica: bolha no canto inferior direito
 * + janela que conversa com POST /api/chat. */
(function () {
  "use strict";

  const history = [];   // [{role, content}] enviado a cada pergunta
  let busy = false;

  const NAME = "Mbula";
  let gid = 0;
  // mascote: gota de chuva com rosto (SVG inline; gradiente com id único por instância)
  function mascot(size) {
    const id = "cw-drop-" + gid++;
    return `<svg class="cw-mascot" viewBox="0 0 64 64" width="${size}" height="${size}" aria-hidden="true">
      <defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#8fdcec"/><stop offset="1" stop-color="#1f7fa8"/></linearGradient></defs>
      <path d="M32 3C32 3 11 27 11 41a21 21 0 0 0 42 0C53 27 32 3 32 3Z" fill="url(#${id})" stroke="#0f5f7d" stroke-width="2"/>
      <ellipse cx="21.5" cy="31" rx="3.2" ry="7" fill="#fff" opacity=".55" transform="rotate(25 21.5 31)"/>
      <g class="cw-eyes" fill="#0b2e3b"><ellipse cx="25" cy="40" rx="3" ry="3.6"/><ellipse cx="39" cy="40" rx="3" ry="3.6"/></g>
      <circle cx="26" cy="38.8" r="1" fill="#fff"/><circle cx="40" cy="38.8" r="1" fill="#fff"/>
      <circle cx="19.5" cy="47" r="3" fill="#ff8fa3" opacity=".55"/><circle cx="44.5" cy="47" r="3" fill="#ff8fa3" opacity=".55"/>
      <path d="M27 48.5q5 4.5 10 0" fill="none" stroke="#0b2e3b" stroke-width="2.2" stroke-linecap="round"/>
    </svg>`;
  }
  const ICON_CLOSE = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M6.4 5 12 10.6 17.6 5 19 6.4 13.4 12l5.6 5.6-1.4 1.4-5.6-5.6L6.4 19 5 17.6l5.6-5.6L5 6.4Z"/></svg>';
  const ICON_SEND = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M3 20.5V14l9-2-9-2V3.5L22 12Z"/></svg>';

  function el(tag, cls, attrs) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    for (const k in attrs || {}) n.setAttribute(k, attrs[k]);
    return n;
  }

  // markdown leve via DOM (sem innerHTML do modelo): **negrito**, *itálico*, `código`, listas, links
  function appendMarks(node, text) {
    const re = /\*\*\*(.+?)\*\*\*|\*\*(.+?)\*\*|__(.+?)__|`([^`]+)`|\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)|(https?:\/\/[^\s<>()"']+[^\s<>()"'.,;:!?])|\*(?!\s)(.+?)\*(?!\*)|_(?!\s)(.+?)_(?!_)/g;
    let last = 0, m;
    while ((m = re.exec(text))) {
      if (m.index > last) node.appendChild(document.createTextNode(text.slice(last, m.index)));
      if (m[1]) {
        const s = el("strong"), em = el("em");
        em.textContent = m[1];
        s.appendChild(em);
        node.appendChild(s);
      } else if (m[2] || m[3]) {
        const s = el("strong");
        s.textContent = m[2] || m[3];
        node.appendChild(s);
      } else if (m[4]) {
        const code = el("code");
        code.textContent = m[4];
        node.appendChild(code);
      } else if (m[5] && m[6]) {
        const a = el("a", null, { href: m[6], target: "_blank", rel: "noopener noreferrer" });
        a.textContent = m[5];
        node.appendChild(a);
      } else if (m[7]) {
        const a = el("a", null, { href: m[7], target: "_blank", rel: "noopener noreferrer" });
        a.textContent = m[7];
        node.appendChild(a);
      } else {
        const em = el("em");
        em.textContent = m[8] || m[9];
        node.appendChild(em);
      }
      last = m.index + m[0].length;
    }
    if (last < text.length) node.appendChild(document.createTextNode(text.slice(last)));
  }

  function appendInline(node, text) {
    const parts = text.split("\n");
    parts.forEach((part, i) => {
      appendMarks(node, part);
      if (i < parts.length - 1) node.appendChild(el("br"));
    });
  }

  function renderMd(root, text) {
    const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
    let i = 0;
    while (i < lines.length) {
      if (!lines[i].trim()) { i++; continue; }
      const heading = /^(#{1,3})\s+(.+)$/.exec(lines[i]);
      if (heading) {
        const h = el("h" + (heading[1].length + 1));
        appendInline(h, heading[2]);
        root.appendChild(h);
        i++;
        continue;
      }
      const isUl = /^[-*]\s+/.test(lines[i]);
      const isOl = /^\d+[.)]\s+/.test(lines[i]);
      if (isUl || isOl) {
        const list = el(isUl ? "ul" : "ol");
        while (i < lines.length) {
          const item = isUl ? /^[-*]\s+(.+)$/.exec(lines[i]) : /^\d+[.)]\s+(.+)$/.exec(lines[i]);
          if (!item) break;
          const li = el("li");
          appendInline(li, item[1]);
          list.appendChild(li);
          i++;
        }
        root.appendChild(list);
        continue;
      }
      const bits = [];
      while (i < lines.length && lines[i].trim() &&
             !/^#{1,3}\s+/.test(lines[i]) && !/^[-*]\s+/.test(lines[i]) && !/^\d+[.)]\s+/.test(lines[i])) {
        bits.push(lines[i]);
        i++;
      }
      const p = el("p");
      appendInline(p, bits.join("\n"));
      root.appendChild(p);
    }
  }

  const bubble = el("button", "cw-bubble", { type: "button", "aria-label": `Chat with ${NAME}, the water assistant`,
                                             "aria-expanded": "false", "aria-controls": "cw-panel" });
  bubble.innerHTML = mascot(50);

  // balão de boas-vindas ao lado da bolha (some sozinho ou ao abrir o chat)
  const hint = el("div", "cw-hint", { role: "status" });
  hint.textContent = `Hi! I'm ${NAME}. Can I help with water in the DRC?`;
  hint.hidden = true;

  const panel = el("section", "cw-panel", { id: "cw-panel", role: "dialog", "aria-label": `${NAME}, water assistant` });
  panel.hidden = true;
  panel.innerHTML =
    '<header class="cw-head"><span class="cw-avatar cw-avatar-lg">' + mascot(38) + "</span>" +
    `<div class="cw-title"><strong>${NAME}</strong>` +
    '<span>Water assistant · climate, aquifers and legislation in the DRC</span></div>' +
    '<button type="button" class="cw-close" aria-label="Close">' + ICON_CLOSE + "</button></header>" +
    '<div class="cw-msgs" aria-live="polite"></div>' +
    '<form class="cw-form"><textarea rows="1" placeholder="Type your question…" aria-label="Message" maxlength="4000"></textarea>' +
    '<button type="submit" class="cw-send" aria-label="Send">' + ICON_SEND + "</button></form>";

  const msgs = panel.querySelector(".cw-msgs");
  const form = panel.querySelector(".cw-form");
  const input = panel.querySelector("textarea");
  const send = panel.querySelector(".cw-send");

  // mensagens da Mbula vêm com o avatar ao lado
  function place(m, withAvatar) {
    if (!withAvatar) return msgs.appendChild(m);
    const row = el("div", "cw-row");
    const av = el("span", "cw-avatar");
    av.innerHTML = mascot(28);
    row.append(av, m);
    msgs.appendChild(row);
    return row;
  }

  function addMsg(role, text, sources) {
    const m = el("div", "cw-msg cw-" + role);
    const body = el("div", "cw-text");
    renderMd(body, text);
    m.appendChild(body);
    if (sources && sources.length) {
      const list = el("ol", "cw-sources");
      for (const s of sources) {
        const li = el("li");
        const a = el("a", null, { href: s.url, target: "_blank", rel: "noopener noreferrer", title: s.url });
        a.textContent = s.title || s.url;
        li.appendChild(a);
        list.appendChild(li);
      }
      const cap = el("div", "cw-sources-cap");
      cap.textContent = "Sources";
      m.append(cap, list);
    }
    place(m, role === "assistant");
    msgs.scrollTop = msgs.scrollHeight;
  }

  function typing(on) {
    let t = msgs.querySelector(".cw-thinking");
    if (on && !t) {
      const m = el("div", "cw-msg cw-assistant cw-typing", { "aria-label": `${NAME} is searching` });
      m.innerHTML = "<span></span><span></span><span></span>";
      t = place(m, true);
      t.classList.add("cw-thinking");
      msgs.scrollTop = msgs.scrollHeight;
    } else if (!on && t) t.remove();
  }

  function setBusy(b) {
    busy = b;
    send.disabled = b;
    input.disabled = b;
    typing(b);
  }

  function autosize() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 120) + "px";
  }

  async function ask(text) {
    addMsg("user", text);
    setBusy(true);
    try {
      const r = await fetch("api/chat", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, history }),
      });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const data = await r.json();
      history.push({ role: "user", content: text }, { role: "assistant", content: data.answer });
      addMsg("assistant", data.answer, data.sources);
    } catch (e) {
      addMsg("error", "Could not reach the assistant (" + e.message + "). Please try again.");
    } finally {
      setBusy(false);
      input.focus();
    }
  }

  function setHint(on) {
    hint.hidden = !on;
    document.body.classList.toggle("cw-hint-open", on);
    if (on) {
      requestAnimationFrame(() => {
        const h = hint.getBoundingClientRect().height;
        document.documentElement.style.setProperty("--cw-hint-lift", Math.ceil(h + 36) + "px");
      });
    }
  }

  function toggle(open) {
    panel.hidden = !open;
    bubble.setAttribute("aria-expanded", String(open));
    bubble.classList.toggle("cw-open", open);
    setHint(false);
    if (open) {
      if (!msgs.childElementCount)
        addMsg("assistant", `Hi! I'm ${NAME}, which means "rain" in Lingala. Ask me about rainfall, aquifers, boreholes or water legislation in the Democratic Republic of the Congo (DRC). I search the web and cite my sources.`);
      input.focus();
    } else bubble.focus();
  }

  function openWith(text) {
    const q = String(text || "").trim();
    toggle(true);
    if (!q) return;
    if (busy) {
      input.value = q;
      autosize();
      return;
    }
    input.value = "";
    autosize();
    ask(q);
  }
  window.MbulaChat = { open: () => toggle(true), ask: openWith };

  bubble.addEventListener("click", () => toggle(panel.hidden));
  panel.querySelector(".cw-close").addEventListener("click", () => toggle(false));
  panel.addEventListener("keydown", (e) => { if (e.key === "Escape") toggle(false); });
  input.addEventListener("input", autosize);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || busy) return;
    input.value = "";
    autosize();
    ask(text);
  });

  hint.addEventListener("click", () => toggle(true));
  document.body.append(panel, hint, bubble);
  setTimeout(() => { if (panel.hidden) setHint(true); }, 1200);
  setTimeout(() => setHint(false), 9000);
})();
