/* OmniScribe web — desktop UX behaviors */
const OmniScribe = {
  initApiStatus() {
    const pill = document.getElementById("api-status-pill");
    const text = document.getElementById("api-status-text");
    if (!pill || !text) return;

    fetch("/api/health/")
      .then((r) => r.json())
      .then((data) => {
        const state =
          data.state === "ready" || data.state === "ok"
            ? "ok"
            : data.state === "loading"
              ? "loading"
              : "error";
        pill.className = `status-pill ${state}`;
        // Use generic labels without provider names
        if (state === "ok") {
          text.textContent = "API reachable";
        } else if (state === "loading") {
          text.textContent = "Connecting…";
        } else {
          text.textContent = "API unavailable";
        }
      })
      .catch(() => {
        pill.className = "status-pill error";
        text.textContent = "API unavailable";
      });
  },

  initMultiFileDrop(zoneId, inputId, listId) {
    const zone = document.getElementById(zoneId);
    const input = document.getElementById(inputId);
    const list = document.getElementById(listId);
    if (!zone || !input) return;

    const render = () => {
      if (!list) return;
      list.innerHTML = "";
      Array.from(input.files || []).forEach((f) => {
        const li = document.createElement("li");
        li.textContent = f.name;
        list.appendChild(li);
      });
    };

    zone.addEventListener("click", () => input.click());
    zone.addEventListener("dragover", (e) => {
      e.preventDefault();
      zone.classList.add("dragover");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("dragover");
      input.files = e.dataTransfer.files;
      render();
    });
    input.addEventListener("change", render);
  },

  initAudioPage() {
    this.initMultiFileDrop("audio-drop-zone", "audio_file", "audio-attachment-list");
    this.initMultiFileDrop("docs-drop-zone", "document_files", "docs-attachment-list");

    const form = document.getElementById("audio-upload-form");
    const progress = document.getElementById("pipeline-progress");
    const stageLabel = document.getElementById("stage-label");
    const stageTime = document.getElementById("stage-time");
    const spinner = document.getElementById("spinner");
    const frames = ["◐", "◓", "◑", "◒"];
    let frameIdx = 0;
    let timer = null;
    let start = null;

    if (form && progress) {
      form.addEventListener("submit", () => {
        progress.classList.add("visible");
        start = Date.now();
        if (stageLabel) stageLabel.textContent = "Uploading audio…";
        timer = setInterval(() => {
          frameIdx = (frameIdx + 1) % frames.length;
          if (spinner) spinner.textContent = frames[frameIdx];
          if (stageTime && start) {
            stageTime.textContent = `${((Date.now() - start) / 1000).toFixed(1)}s`;
          }
        }, 100);
      });
    }

    // In-browser recording (desktop Record tab parity)
    const recordStart = document.getElementById("record-start");
    const recordStop = document.getElementById("record-stop");
    const recordStatus = document.getElementById("record-status");
    const recordPreview = document.getElementById("record-preview");
    const recordedInput = document.getElementById("recorded_audio");
    const transcribeRecBtn = document.getElementById("transcribe-recording-btn");
    let mediaRecorder = null;
    let chunks = [];

    if (recordStart && navigator.mediaDevices) {
      recordStart.addEventListener("click", async () => {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          chunks = [];
          mediaRecorder = new MediaRecorder(stream);
          mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
          mediaRecorder.onstop = () => {
            const blob = new Blob(chunks, { type: "audio/webm" });
            const file = new File([blob], "recording.webm", { type: "audio/webm" });
            const dt = new DataTransfer();
            dt.items.add(file);
            if (recordedInput) recordedInput.files = dt.files;
            if (recordPreview) {
              recordPreview.src = URL.createObjectURL(blob);
              recordPreview.classList.remove("hidden");
            }
            if (transcribeRecBtn) transcribeRecBtn.disabled = false;
            if (recordStatus) recordStatus.textContent = "Recording ready — transcribe when ready";
            stream.getTracks().forEach((t) => t.stop());
          };
          mediaRecorder.start();
          recordStart.disabled = true;
          recordStop.disabled = false;
          if (recordStatus) recordStatus.textContent = "Recording…";
        } catch (err) {
          if (recordStatus) recordStatus.textContent = "Microphone access denied or unavailable";
        }
      });
    }

    if (recordStop) {
      recordStop.addEventListener("click", () => {
        if (mediaRecorder && mediaRecorder.state !== "inactive") {
          mediaRecorder.stop();
        }
        recordStart.disabled = false;
        recordStop.disabled = true;
      });
    }
  },

  initQuiz() {
    const btn = document.getElementById("quiz-submit-btn");
    if (!btn) return;
    btn.addEventListener("click", () => {
      const cards = document.querySelectorAll(".quiz-card");
      let correct = 0;
      cards.forEach((card) => {
        const answer = card.dataset.answer;
        const explanation = card.dataset.explanation || "";
        const result = card.querySelector(".quiz-result");
        const radios = card.querySelectorAll('input[type="radio"]');
        let selected = null;
        radios.forEach((r) => {
          if (r.checked) selected = r.value;
        });
        if (!result) return;
        result.style.display = "block";
        if (!selected) {
          result.className = "quiz-result";
          result.textContent = "No answer selected";
        } else if (selected === answer) {
          correct += 1;
          result.className = "quiz-result correct";
          result.textContent = `Correct — ${explanation}`;
        } else {
          result.className = "quiz-result incorrect";
          result.textContent = `Incorrect (answer: ${answer}) — ${explanation}`;
        }
      });
      const score = document.getElementById("quiz-score");
      if (score) score.textContent = `Score: ${correct} / ${cards.length}`;
    });
  },

  initFlashcards() {
    const cards = document.querySelectorAll(".flashcard");
    if (!cards.length) return;
    cards.forEach((card) => {
      card.addEventListener("click", () => {
        card.classList.toggle("flipped");
      });
    });
  },

  initAuthValidation() {
    const form = document.querySelector('[data-auth="register"]');
    if (!form) return;

    const usernameInput = form.querySelector("#id_username");
    const emailInput = form.querySelector("#id_email");
    const passwordInput = form.querySelector("#id_password1");
    const confirmInput = form.querySelector("#id_password2");
    const usernameList = form.querySelector('[data-validate="username"]');
    const passwordList = form.querySelector('[data-validate="password"]');
    const confirmList = form.querySelector('[data-validate="confirm"]');

    const setListActive = (list) => {
      if (!list) return;
      if (!list.classList.contains("is-active")) {
        list.classList.add("is-active");
        list.setAttribute("aria-hidden", "false");
      }
    };

    const setItemState = (item, state) => {
      if (!item) return;
      item.classList.remove("is-ok", "is-error", "is-neutral");
      item.classList.add(`is-${state}`);
    };

    const getItem = (list, rule) =>
      list ? list.querySelector(`[data-rule="${rule}"]`) : null;

    const hasValue = (value) => value && value.length > 0;

    const hasSimilarity = (password) => {
      const lower = (password || "").toLowerCase();
      if (!lower) return false;
      const username = (usernameInput?.value || "").trim().toLowerCase();
      const email = (emailInput?.value || "").trim().toLowerCase();
      const emailUser = email.includes("@") ? email.split("@")[0] : "";
      const candidates = [username, emailUser].filter((part) => part.length >= 3);
      return candidates.some((part) => lower.includes(part));
    };

    const validateUsername = () => {
      const value = (usernameInput?.value || "").trim();
      const lengthItem = getItem(usernameList, "length");
      const charsetItem = getItem(usernameList, "charset");

      if (!hasValue(value)) {
        setItemState(lengthItem, "neutral");
        setItemState(charsetItem, "neutral");
        return;
      }

      const lengthOk = value.length <= 150;
      const charsetOk = /^[A-Za-z0-9@._+-]+$/.test(value);

      setItemState(lengthItem, lengthOk ? "ok" : "error");
      setItemState(charsetItem, charsetOk ? "ok" : "error");
    };

    const validatePassword = () => {
      const value = passwordInput?.value || "";
      const minLenItem = getItem(passwordList, "min-length");
      const complexityItem = getItem(passwordList, "complexity");
      const symbolItem = getItem(passwordList, "symbol");
      const nonNumericItem = getItem(passwordList, "non-numeric");
      const similarityItem = getItem(passwordList, "similarity");

      if (!hasValue(value)) {
        [minLenItem, complexityItem, symbolItem, nonNumericItem, similarityItem].forEach(
          (item) => setItemState(item, "neutral")
        );
        validateConfirm();
        return;
      }

      const minLenOk = value.length >= 8;
      const hasLetter = /[A-Za-z]/.test(value);
      const hasNumber = /[0-9]/.test(value);
      const complexityOk = hasLetter && hasNumber;
      const symbolOk = /[^A-Za-z0-9]/.test(value);
      const nonNumericOk = !/^\d+$/.test(value);
      const similarityOk = !hasSimilarity(value);

      setItemState(minLenItem, minLenOk ? "ok" : "error");
      setItemState(complexityItem, complexityOk ? "ok" : "error");
      setItemState(symbolItem, symbolOk ? "ok" : "error");
      setItemState(nonNumericItem, nonNumericOk ? "ok" : "error");
      setItemState(similarityItem, similarityOk ? "ok" : "error");
      validateConfirm();
    };

    const validateConfirm = () => {
      const confirmValue = confirmInput?.value || "";
      const matchItem = getItem(confirmList, "match");

      if (!hasValue(confirmValue)) {
        setItemState(matchItem, "neutral");
        return;
      }

      const matchOk = confirmValue === (passwordInput?.value || "");
      setItemState(matchItem, matchOk ? "ok" : "error");
    };

    const attach = (input, handler, list) => {
      if (!input) return;
      const run = () => {
        if (list) setListActive(list);
        handler();
      };
      input.addEventListener("input", run);
      input.addEventListener("focus", run);
    };

    attach(usernameInput, validateUsername, usernameList);
    attach(passwordInput, validatePassword, passwordList);
    attach(confirmInput, validateConfirm, confirmList);

    if (emailInput) {
      emailInput.addEventListener("input", validatePassword);
    }

    validateUsername();
    validatePassword();
    validateConfirm();
  },
};

// Handle dynamic course selection visibility
function handleCourseSelection(selectElement, prefix = '') {
  const courseId = selectElement.value;
  const titleRowId = prefix ? `${prefix}_course_title_row` : 'course_title_row';
  const titleRow = document.getElementById(titleRowId);
  
  if (titleRow) {
    // Show title input only when "Create new course" is selected (empty value)
    titleRow.style.display = courseId === '' ? 'block' : 'none';
  }
}

// Floating chat assistant
function initFloatingChat() {
  const openBtn = document.getElementById("open-chat-btn");
  const closeBtn = document.getElementById("close-chat");
  const drawer = document.getElementById("floating-chat-drawer");
  const form = document.getElementById("floating-chat-form");
  const body = document.getElementById("floating-chat-body");
  const lectureInput = document.getElementById("floating-chat-lecture-id");
  
  if (!openBtn || !drawer) return;
  
  openBtn.addEventListener("click", () => {
    drawer.style.display = "flex";
    openBtn.style.display = "none";
  });
  
  if (closeBtn) {
    closeBtn.addEventListener("click", () => {
      drawer.style.display = "none";
      openBtn.style.display = "flex";
    });
  }
  
  if (form) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const input = document.getElementById("floating-chat-input");
      const message = input.value.trim();
      if (!message) return;

      const csrfToken = form.querySelector('input[name="csrfmiddlewaretoken"]')?.value;
      
      // Add user message to chat
      const userMsg = document.createElement("div");
      userMsg.style.cssText = "margin:8px 0;padding:8px;background:var(--accent);color:white;border-radius:8px;text-align:right";
      userMsg.textContent = message;
      body.appendChild(userMsg);
      input.value = "";
      body.scrollTop = body.scrollHeight;

      const payload = new URLSearchParams();
      payload.append("message", message);
      if (lectureInput && lectureInput.value) {
        payload.append("lecture_id", lectureInput.value);
      }

      fetch("/api/chat/", {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          "X-CSRFToken": csrfToken || "",
        },
        body: payload.toString(),
      })
        .then((r) => r.json())
        .then((data) => {
          const botMsg = document.createElement("div");
          botMsg.style.cssText = "margin:8px 0;padding:8px;background:var(--bg2);border-radius:8px";
          if (data.error) {
            botMsg.textContent = data.error;
          } else {
            let answer = data.answer || "No response.";
            if (data.sources && data.sources.length) {
              answer += `\n\nSources: ${data.sources.join(", ")}`;
            }
            botMsg.textContent = answer;
          }
          body.appendChild(botMsg);
          body.scrollTop = body.scrollHeight;
        })
        .catch(() => {
          const botMsg = document.createElement("div");
          botMsg.style.cssText = "margin:8px 0;padding:8px;background:var(--bg2);border-radius:8px";
          botMsg.textContent = "Unable to reach the AI assistant.";
          body.appendChild(botMsg);
          body.scrollTop = body.scrollHeight;
        });
    });
  }

  // Set lecture_id from URL if present
  if (lectureInput) {
    const params = new URLSearchParams(window.location.search);
    const lectureId = params.get("lecture_id");
    if (lectureId) lectureInput.value = lectureId;
  }
}

function initRenameModal() {
  const modal = document.getElementById("rename-modal");
  const form = document.getElementById("rename-modal-form");
  const input = document.getElementById("rename-modal-input");
  const actionInput = document.getElementById("rename-modal-action");
  const courseIdInput = document.getElementById("rename-modal-course-id");
  const lectureIdInput = document.getElementById("rename-modal-lecture-id");
  const titleEl = document.getElementById("rename-modal-title");
  const closeBtn = document.getElementById("rename-modal-close");
  const cancelBtn = document.getElementById("rename-modal-cancel");

  if (!modal || !form || !input || !actionInput) return;

  const openModal = (type, id, title) => {
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
    form.action = window.location.pathname;
    input.value = title || "";
    if (type === "course") {
      actionInput.value = "rename_course";
      courseIdInput.value = id;
      lectureIdInput.value = "";
      if (titleEl) titleEl.textContent = "Rename course";
    } else {
      actionInput.value = "rename_lecture";
      lectureIdInput.value = id;
      courseIdInput.value = "";
      if (titleEl) titleEl.textContent = "Rename lecture";
    }
    input.focus();
    input.select();
  };

  document.querySelectorAll("[data-rename]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const type = btn.getAttribute("data-rename");
      const id = btn.getAttribute("data-rename-id");
      const title = btn.getAttribute("data-rename-title");
      openModal(type, id, title);
    });
  });

  const closeModal = () => {
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
  };

  if (closeBtn) closeBtn.addEventListener("click", closeModal);
  if (cancelBtn) cancelBtn.addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });
}

function initChatEnterSend() {
  document.querySelectorAll(".chat-input-bar textarea").forEach((textarea) => {
    textarea.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const form = textarea.closest("form");
        if (form) form.requestSubmit();
      }
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  OmniScribe.initApiStatus();
  setInterval(() => OmniScribe.initApiStatus(), 20000);
  
  // Initialize floating chat
  initFloatingChat();
  initRenameModal();
  initChatEnterSend();
  OmniScribe.initAuthValidation();
  
  // Initialize course selection visibility
  const courseSelects = document.querySelectorAll('[name="course_id"]');
  courseSelects.forEach(select => {
    // Trigger initial state
    handleCourseSelection(select, select.id.includes('record') ? 'record' : '');
  });
});
