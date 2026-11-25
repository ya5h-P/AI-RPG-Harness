(() => {
  // Prevent iOS Safari / WKWebView pinch-to-zoom and multi-touch gestures (capture phase)
  ["gesturestart", "gesturechange", "gestureend"].forEach((evt) => {
    window.addEventListener(evt, (e) => e.preventDefault(), { passive: false, capture: true });
  });
  ["touchstart", "touchmove"].forEach((evt) => {
    document.addEventListener(
      evt,
      (e) => {
        if (e.touches && e.touches.length > 1) {
          e.preventDefault();
        }
      },
      { passive: false, capture: true }
    );
  });

  const state = {
    stories: [],
    scenarios: [],
    scripts: [],
    defaultAiInstructions: "",
    llmReady: false,
    llmMaxContext: null,
    llmMaxContextSource: null,
    llmThinkingMode: "none",
    currentStory: null,
    mode: "do",
    isGenerating: false,
    abortController: null,
    editingSegmentId: null,
    activeToolbarSegmentId: null,
    editingScenarioId: null,
    editingScenarioChoices: [],
    editingScenarioCards: [],
    editingScenarioBuiltinScript: { enabled: true, library: "", input: "", context: "", output: "" },
    editingScenarioAttachedScripts: [],
    playSetup: null,
    scriptEditor: null,
    activeView: "home",
    homeTab: "adventures",
  };

  const els = {
    storyTitle: document.getElementById("story-title"),
    homeBrand: document.getElementById("home-brand"),
    btnHome: document.getElementById("btn-home"),
    llmPill: document.getElementById("llm-pill"),
    btnStartLlm: document.getElementById("btn-start-llm"),
    btnEndpoint: document.getElementById("btn-endpoint"),
    endpointBtnLabel: document.getElementById("endpoint-btn-label"),

    endpointModal: document.getElementById("endpoint-modal"),
    btnCloseEndpoint: document.getElementById("btn-close-endpoint"),
    btnCancelEndpoint: document.getElementById("btn-cancel-endpoint"),
    btnSaveEndpoint: document.getElementById("btn-save-endpoint"),
    epUrlInput: document.getElementById("ep-url-input"),
    epKeyInput: document.getElementById("ep-key-input"),
    btnEpClearKey: document.getElementById("btn-ep-clear-key"),
    epModelInput: document.getElementById("ep-model-input"),
    btnEpRefreshModels: document.getElementById("btn-ep-refresh-models"),
    epModelSelect: document.getElementById("ep-model-select"),
    epModelsDatalist: document.getElementById("ep-models-datalist"),
    epStatusMsg: document.getElementById("ep-status-msg"),

    homeView: document.getElementById("home-view"),
    stageView: document.getElementById("stage-view"),
    homeTabs: Array.from(document.querySelectorAll(".home-tab")),
    homePaneAdventures: document.getElementById("home-pane-adventures"),
    homePaneScenarios: document.getElementById("home-pane-scenarios"),
    homeAdventuresGrid: document.getElementById("home-adventures-grid"),
    homeScenariosGrid: document.getElementById("home-scenarios-grid"),
    btnHomeCreateScenario: document.getElementById("btn-home-create-scenario"),
    btnHomeImportScenario: document.getElementById("btn-home-import-scenario"),

    scenarioModal: document.getElementById("scenario-modal"),
    btnCloseScenarios: document.getElementById("btn-close-scenarios"),
    scenariosGrid: document.getElementById("scenarios-grid"),
    scenarioFormHeading: document.getElementById("scenario-form-heading"),
    scenarioNameInput: document.getElementById("scenario-name-input"),
    scenarioTypeSelect: document.getElementById("scenario-type-select"),
    scenarioOpeningWrap: document.getElementById("scenario-opening-wrap"),
    scenarioOpeningInput: document.getElementById("scenario-opening-input"),
    scenarioOpeningCount: document.getElementById("scenario-opening-count"),
    scenarioChoicesWrap: document.getElementById("scenario-choices-wrap"),
    scenarioChoicesList: document.getElementById("scenario-choices-list"),
    btnAddScenarioChoice: document.getElementById("btn-add-scenario-choice"),
    scenarioCcNote: document.getElementById("scenario-cc-note"),
    scenarioAiInstructions: document.getElementById("scenario-ai-instructions"),
    btnInsertDefaultScenarioInstructions: document.getElementById("btn-insert-default-scenario-instructions"),
    scenarioStorySummary: document.getElementById("scenario-story-summary"),
    scenarioPlotEssentials: document.getElementById("scenario-plot-essentials"),
    scenarioAuthorsNote: document.getElementById("scenario-authors-note"),
    scenarioThirdPerson: document.getElementById("scenario-third-person"),
    scenarioThirdPersonFields: document.getElementById("scenario-third-person-fields"),
    scenarioCharacterName: document.getElementById("scenario-character-name"),
    btnAddScenarioCard: document.getElementById("btn-add-scenario-card"),
    scenarioCardsList: document.getElementById("scenario-cards-list"),
    scenarioScriptStatus: document.getElementById("scenario-script-status"),
    btnEditScenarioScript: document.getElementById("btn-edit-scenario-script"),
    scenarioAttachScriptSelect: document.getElementById("scenario-attach-script-select"),
    btnAttachScenarioScript: document.getElementById("btn-attach-scenario-script"),
    scenarioAttachedScriptsList: document.getElementById("scenario-attached-scripts-list"),
    scenarioFormError: document.getElementById("scenario-form-error"),
    btnCancelEditScenario: document.getElementById("btn-cancel-edit-scenario"),
    btnSaveScenario: document.getElementById("btn-save-scenario"),
    btnSavePlayScenario: document.getElementById("btn-save-play-scenario"),

    btnSettings: document.getElementById("btn-settings"),
    btnCloseSettings: document.getElementById("btn-close-settings"),
    drawerSettings: document.getElementById("drawer-settings"),
    settingsMainTabs: Array.from(document.querySelectorAll("[data-settings-tab]")),
    settingsPaneAdventure: document.getElementById("settings-pane-adventure"),
    settingsPaneAi: document.getElementById("settings-pane-ai"),
    drawerTabs: Array.from(document.querySelectorAll("[data-drawer-tab]")),
    tabPanePlot: document.getElementById("tab-pane-plot"),
    tabPaneCards: document.getElementById("tab-pane-cards"),
    tabPaneScripts: document.getElementById("tab-pane-scripts"),
    tabPaneDetails: document.getElementById("tab-pane-details"),
    storyDetailsTitle: document.getElementById("story-details-title"),
    storyDetailsDesc: document.getElementById("story-details-desc"),
    storyDetailsTags: document.getElementById("story-details-tags"),
    btnDownloadAdventure: document.getElementById("btn-download-adventure"),
    storyBuiltinStatus: document.getElementById("story-builtin-status"),
    storyBuiltinEnabled: document.getElementById("story-builtin-enabled"),
    btnEditStoryBuiltinScript: document.getElementById("btn-edit-story-builtin-script"),
    storyAttachScriptSelect: document.getElementById("story-attach-script-select"),
    btnAttachStoryScript: document.getElementById("btn-attach-story-script"),
    btnNewReusableScript: document.getElementById("btn-new-reusable-script"),
    btnInstallInnerSelf: document.getElementById("btn-install-inner-self"),
    btnInstallAutoCards: document.getElementById("btn-install-auto-cards"),
    storyAttachedScriptsList: document.getElementById("story-attached-scripts-list"),
    storyScriptLogs: document.getElementById("story-script-logs"),
    btnClearStoryLogs: document.getElementById("btn-clear-story-logs"),
    storyCardsSearch: document.getElementById("story-cards-search"),
    storyCardsTypeFilter: document.getElementById("story-cards-type-filter"),
    btnAddStoryCard: document.getElementById("btn-add-story-card"),
    btnImportCards: document.getElementById("btn-import-cards"),
    btnExportCards: document.getElementById("btn-export-cards"),
    importCardsFileInput: document.getElementById("import-cards-file-input"),
    storyCardsList: document.getElementById("story-cards-list"),
    storyAiInstructions: document.getElementById("story-ai-instructions"),
    btnInsertDefaultStoryInstructions: document.getElementById("btn-insert-default-story-instructions"),
    storySummaryInput: document.getElementById("story-summary-input"),
    btnAutoSummarize: document.getElementById("btn-auto-summarize"),
    plotEssentialsInput: document.getElementById("plot-essentials-input"),
    authorsNoteInput: document.getElementById("authors-note-input"),
    storyThirdPerson: document.getElementById("story-third-person"),
    storyThirdPersonFields: document.getElementById("story-third-person-fields"),
    storyCharacterName: document.getElementById("story-character-name"),
    storyThirdPersonStatus: document.getElementById("story-third-person-status"),
    settingTemp: document.getElementById("setting-temp"),
    settingMaxTokens: document.getElementById("setting-max-tokens"),
    settingTopP: document.getElementById("setting-top-p"),
    settingTopK: document.getElementById("setting-top-k"),
    settingRepeatPenalty: document.getElementById("setting-repeat-penalty"),
    settingPresencePenalty: document.getElementById("setting-presence-penalty"),
    settingFrequencyPenalty: document.getElementById("setting-frequency-penalty"),
    settingContextLengthSlider: document.getElementById("setting-context-length-slider"),
    settingContextLength: document.getElementById("setting-context-length"),
    settingContextMaxLabel: document.getElementById("setting-context-max-label"),
    settingAutoSummarize: document.getElementById("setting-auto-summarize"),
    settingMemoryBank: document.getElementById("setting-memory-bank"),
    settingRawOutput: document.getElementById("setting-raw-output"),
    settingFollowLatest: document.getElementById("setting-follow-latest"),
    settingThinkingToggleRow: document.getElementById("setting-thinking-toggle-row"),
    settingThinking: document.getElementById("setting-thinking"),
    settingEffortControl: document.getElementById("setting-effort-control"),
    settingReasoningEffort: document.getElementById("setting-reasoning-effort"),
    settingEffortBadge: document.getElementById("setting-effort-badge"),
    settingEffortFill: document.getElementById("setting-effort-fill"),
    settingEffortDesc: document.getElementById("setting-effort-desc"),
    effortStops: Array.from(document.querySelectorAll(".effort-stop")),
    settingsSaveStatus: document.getElementById("settings-save-status"),

    btnContext: document.getElementById("btn-context"),
    btnContextNext: document.getElementById("btn-context-next"),
    btnContextLast: document.getElementById("btn-context-last"),
    contextModal: document.getElementById("context-modal"),
    btnCloseContext: document.getElementById("btn-close-context"),
    contextTotalSummary: document.getElementById("context-total-summary"),
    contextSectionsList: document.getElementById("context-sections-list"),

    playSetupModal: document.getElementById("play-setup-modal"),
    playSetupTitle: document.getElementById("play-setup-title"),
    playSetupSubtitle: document.getElementById("play-setup-subtitle"),
    playSetupBody: document.getElementById("play-setup-body"),
    btnSetupInnerSelf: document.getElementById("btn-setup-inner-self"),
    btnSetupAutoCards: document.getElementById("btn-setup-auto-cards"),
    btnClosePlaySetup: document.getElementById("btn-close-play-setup"),
    btnCancelPlaySetup: document.getElementById("btn-cancel-play-setup"),
    btnBackPlaySetup: document.getElementById("btn-back-play-setup"),
    btnNextPlaySetup: document.getElementById("btn-next-play-setup"),
    btnConfirmPlaySetup: document.getElementById("btn-confirm-play-setup"),

    storyFeed: document.getElementById("story-feed"),
    scriptMessageBanner: document.getElementById("script-message-banner"),
    errorBanner: document.getElementById("error-banner"),

    scriptEditorModal: document.getElementById("script-editor-modal"),
    scriptEditorTitle: document.getElementById("script-editor-title"),
    btnCloseScriptEditor: document.getElementById("btn-close-script-editor"),
    scriptMetaFields: document.getElementById("script-meta-fields"),
    scriptMetaName: document.getElementById("script-meta-name"),
    scriptMetaVersion: document.getElementById("script-meta-version"),
    scriptMetaDesc: document.getElementById("script-meta-desc"),
    scriptHookTabs: Array.from(document.querySelectorAll(".script-hook-tab")),
    scriptCodeEditor: document.getElementById("script-code-editor"),
    scriptTestHook: document.getElementById("script-test-hook"),
    scriptTestInput: document.getElementById("script-test-input"),
    btnRunScriptTest: document.getElementById("btn-run-script-test"),
    scriptTestOutput: document.getElementById("script-test-output"),
    btnCancelScriptEditor: document.getElementById("btn-cancel-script-editor"),
    btnSaveScriptEditor: document.getElementById("btn-save-script-editor"),

    btnOpenImport: document.getElementById("btn-open-import"),
    importModal: document.getElementById("import-modal"),
    btnCloseImport: document.getElementById("btn-close-import"),
    btnCancelImport: document.getElementById("btn-cancel-import"),
    importUrlInput: document.getElementById("import-url-input"),
    btnImportUrl: document.getElementById("btn-import-url"),
    importFileInput: document.getElementById("import-file-input"),
    importJsonInput: document.getElementById("import-json-input"),
    importError: document.getElementById("import-error"),
    btnConfirmImport: document.getElementById("btn-confirm-import"),

    modeSwitcher: document.getElementById("mode-switcher"),
    btnModeCollapse: document.getElementById("btn-mode-collapse"),
    modeBtns: Array.from(document.querySelectorAll(".mode-btn")),
    segmentActionBar: document.getElementById("segment-action-bar"),
    composer: document.querySelector(".composer"),
    playerInput: document.getElementById("player-input"),
    btnSend: document.getElementById("btn-send"),
    btnAddOnly: document.getElementById("btn-add-only"),
    btnUndo: document.getElementById("btn-undo"),
    btnRedo: document.getElementById("btn-redo"),
    btnRetry: document.getElementById("btn-retry"),
    btnRetryChanges: document.getElementById("btn-retry-changes"),
    retryChangesBar: document.getElementById("retry-changes-bar"),
    retryChangesInput: document.getElementById("retry-changes-input"),
    btnSubmitRetryChanges: document.getElementById("btn-submit-retry-changes"),
    btnCancelRetryChanges: document.getElementById("btn-cancel-retry-changes"),
    btnContinue: document.getElementById("btn-continue"),
    btnErase: document.getElementById("btn-erase"),
  };

  const MODE_META = {
    do: { placeholder: "What do you do? (e.g., pick up a bucket)" },
    say: { placeholder: "What do you say? (e.g., Anyone here?)" },
    story: { placeholder: "Write narrative text to add directly inline..." },
    guide: { placeholder: "Give the AI an out-of-character direction for this turn (not added to story text)..." },
  };

  function showError(msg) {
    if (!msg) {
      els.errorBanner.classList.add("hidden");
      els.errorBanner.textContent = "";
      return;
    }
    els.errorBanner.textContent = msg;
    els.errorBanner.classList.remove("hidden");
  }

  async function api(path, options = {}) {
    const resp = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(data.error || `Request failed (${resp.status})`);
    }
    return data;
  }

  function updateModeUI() {
    els.modeBtns.forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.mode === state.mode);
    });
    els.playerInput.placeholder = MODE_META[state.mode].placeholder;
  }

  function setModeExpanded(expanded) {
    const open = Boolean(expanded);
    els.modeSwitcher.classList.toggle("expanded", open);
    els.modeSwitcher.closest(".composer-top")?.classList.toggle("mode-expanded", open);
  }

  function setMode(mode) {
    if (!MODE_META[mode]) return;
    state.mode = mode;
    updateModeUI();
    setModeExpanded(false);
    if (document.activeElement !== els.playerInput) {
      els.playerInput.focus({ preventScroll: true });
    }
  }

  function updateControlsState() {
    const busy = state.isGenerating;
    const segs = state.currentStory?.segments || [];
    const hasStory = Boolean(state.currentStory);
    const lastIsAi = segs.length > 0 && segs[segs.length - 1].kind === "ai";
    const onlyFixedOpening = segs.length === 1 && segs[0].kind === "opening";

    const hasUndoStack = (state.currentStory?.undo_stack || []).length > 0;
    const hasRedoStack = (state.currentStory?.redo_stack || []).length > 0;

    els.btnSend.textContent = busy ? "Stop" : "Send";
    els.btnSend.classList.toggle("danger", busy);
    els.btnSend.disabled = !hasStory && !busy;
    els.btnAddOnly.disabled = busy || !hasStory || state.mode === "guide";
    els.btnUndo.disabled = busy || !hasStory || (!hasUndoStack && (segs.length === 0 || onlyFixedOpening));
    els.btnRedo.disabled = busy || !hasStory || !hasRedoStack;
    els.btnRetry.disabled = busy || !hasStory || !lastIsAi;
    els.btnRetryChanges.disabled = busy || !hasStory || !lastIsAi;
    els.btnContinue.disabled = busy || !hasStory;
    els.btnErase.disabled = busy || !hasStory || segs.length === 0 || onlyFixedOpening;
  }

  function scrollFeedToBottom(force = false) {
    if (force || state.currentStory?.settings?.follow_latest_text !== false) {
      els.storyFeed.scrollTop = els.storyFeed.scrollHeight;
    }
  }

  function getStreamingScrollTop(anchorEl) {
    const feed = els.storyFeed;
    const maxFeedScroll = Math.max(0, feed.scrollHeight - feed.clientHeight);
    if (!anchorEl || !anchorEl.isConnected) return maxFeedScroll;
    const feedRect = feed.getBoundingClientRect();
    const anchorRect = anchorEl.getBoundingClientRect();
    const prevEl = anchorEl.previousElementSibling;
    let topMargin = 14;
    if (prevEl) {
      const prevRect = prevEl.getBoundingClientRect();
      const cs = getComputedStyle(prevEl);
      const lineHeight = parseFloat(cs.lineHeight) || 27;
      const padBottom = parseFloat(cs.paddingBottom) || 4;
      const gap = Math.max(0, anchorRect.top - prevRect.bottom);
      // Leave the last ~1 line of the preceding/user message visible at the top of the feed.
      const keepEndHeight = Math.min(prevRect.height, lineHeight + padBottom + 6);
      topMargin = keepEndHeight + gap;
    } else if (anchorEl.classList.contains("stream-continuation")) {
      const cs = getComputedStyle(anchorEl);
      const lineHeight = parseFloat(cs.lineHeight) || 29;
      // Leave ~1 line of the existing AI prose visible above the continuation point.
      topMargin = lineHeight + 10;
    }
    const topLimit = Math.max(0, feed.scrollTop + (anchorRect.top - feedRect.top) - topMargin);
    return Math.min(maxFeedScroll, topLimit);
  }

  function hasIncompleteTail(text) {
    const prev = String(text || "").trimEnd();
    if (!prev) return false;
    if (prev.endsWith("...") || prev.endsWith("…")) return true;
    const lastPara = prev.split("\n").pop() || "";
    const dblCount = (lastPara.match(/"/g) || []).length;
    if (dblCount % 2 === 1) return true;
    const openCurly = (lastPara.match(/\u201c/g) || []).length;
    const closeCurly = (lastPara.match(/\u201d/g) || []).length;
    if (openCurly > closeCurly) return true;
    const last = prev[prev.length - 1];
    if ("—–-,;:(".includes(last)) return true;
    const endedSentence =
      ".!?".includes(last) ||
      (prev.length >= 2 && "\"\u201d'\u2019)".includes(last) && ".!?".includes(prev[prev.length - 2]));
    return !endedSentence;
  }

  function continuationSeparator(prevText, firstToken) {
    const prev = String(prevText || "").trimEnd();
    const add = String(firstToken || "").trimStart();
    if (!prev || !add) return "";
    if (',.;:!?")\u201d\u2019]'.includes(add[0])) return "";
    if ("—–-\u201c".includes(prev[prev.length - 1])) return "";
    if (hasIncompleteTail(prev) || /^[a-z]/.test(add)) return " ";
    return "\n\n";
  }

  function segmentJoinSeparator(prevSeg, nextSeg) {
    if (!prevSeg || !nextSeg) return "";
    const prevText = String(prevSeg.text || "").trimEnd();
    const nextText = String(nextSeg.text || "").trimStart();
    if (!prevText || !nextText) return "";
    if (
      prevSeg.kind === "do" ||
      prevSeg.kind === "say" ||
      nextSeg.kind === "do" ||
      nextSeg.kind === "say"
    ) {
      return "\n\n";
    }
    if (prevSeg.kind === "story" && (nextSeg.kind === "ai" || nextSeg.kind === "story")) {
      if (!prevText.includes("\n")) {
        return ',.;:!?")\u201d\u2019]'.includes(nextText[0]) ? "" : " ";
      }
      return continuationSeparator(prevText, nextText);
    }
    return continuationSeparator(prevText, nextText);
  }

  function updateStoryThirdPersonUI() {
    const on = els.storyThirdPerson.checked;
    els.storyThirdPersonFields.classList.toggle("hidden", !on);
    els.storyThirdPersonStatus.textContent = on
      ? "Third-person input on."
      : "Third-person input off.";
  }

  function updateScenarioThirdPersonUI() {
    const on = els.scenarioThirdPerson.checked;
    els.scenarioThirdPersonFields.classList.toggle("hidden", !on);
  }

  function updateScenarioOpeningCounter() {
    const len = els.scenarioOpeningInput.value.length;
    els.scenarioOpeningCount.textContent = `${len} / 4000`;
  }

  function renderCardEditors(
    container,
    cards,
    {
      search = "",
      cardType = "",
      onChange,
      allowAiGenerate = false,
      showCcFields = false,
    } = {}
  ) {
    container.innerHTML = "";
    const q = search.trim().toLowerCase();
    const filtered = cards.filter((c) => {
      if (cardType && (c.card_type || "Custom") !== cardType) return false;
      if (!q) return true;
      return (
        (c.title || "").toLowerCase().includes(q) ||
        (c.keys || "").toLowerCase().includes(q) ||
        (c.entry || "").toLowerCase().includes(q) ||
        (c.description || "").toLowerCase().includes(q)
      );
    });

    if (filtered.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.style.fontSize = "0.84rem";
      empty.textContent = cards.length === 0
        ? "No Story Cards yet."
        : "No Story Cards match the current filter.";
      container.appendChild(empty);
      return;
    }

    filtered.forEach((card) => {
      const idx = cards.indexOf(card);
      const box = document.createElement("div");
      box.className = "story-card-editor";

      const row = document.createElement("div");
      row.className = "story-card-editor-row";

      const titleInput = document.createElement("input");
      titleInput.type = "text";
      titleInput.placeholder = "Title (player-facing, e.g., Grue)";
      titleInput.value = card.title || "";
      titleInput.oninput = () => {
        card.title = titleInput.value;
      };

      const typeInput = document.createElement("input");
      typeInput.type = "text";
      typeInput.setAttribute("list", "card-type-options");
      typeInput.placeholder = "Type";
      typeInput.style.maxWidth = "116px";
      typeInput.value = card.card_type || "Custom";
      typeInput.oninput = () => {
        card.card_type = typeInput.value;
      };

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "clear-card-btn";
      delBtn.title = "Remove Story Card";
      delBtn.textContent = "🗑";
      delBtn.onclick = () => {
        cards.splice(idx, 1);
        if (onChange) onChange();
      };

      row.append(titleInput, typeInput, delBtn);

      const keysInput = document.createElement("input");
      keysInput.type = "text";
      keysInput.placeholder = "Trigger keywords (comma-separated, e.g., grue, dark)";
      keysInput.value = card.keys || "";
      keysInput.oninput = () => {
        card.keys = keysInput.value;
      };

      const entryInput = document.createElement("textarea");
      entryInput.rows = 3;
      entryInput.placeholder = "Entry (what the AI sees when triggered—mention the card's name here)";
      entryInput.value = card.entry || "";
      entryInput.oninput = () => {
        card.entry = entryInput.value;
      };

      const pinLabel = document.createElement("label");
      pinLabel.className = "checkbox-row";
      pinLabel.style.fontSize = "0.78rem";
      const pinCb = document.createElement("input");
      pinCb.type = "checkbox";
      pinCb.checked = Boolean(card.is_pinned);
      pinCb.onchange = () => {
        card.is_pinned = pinCb.checked;
      };
      const pinTxt = document.createElement("span");
      pinTxt.textContent = "Pinned (always active in context)";
      pinLabel.append(pinCb, pinTxt);

      box.append(row, keysInput, entryInput, pinLabel);
      if (allowAiGenerate && state.currentStory) {
        const genRow = document.createElement("div");
        genRow.style.display = "flex";
        genRow.style.gap = "6px";
        genRow.style.alignItems = "center";

        const genBtn = document.createElement("button");
        genBtn.type = "button";
        genBtn.className = "chip-btn";
        genBtn.textContent = "✨ Generate Entry";
        genBtn.onclick = async () => {
          const title = (card.title || "").trim();
          if (!title) {
            showError("Enter a Card Title before generating its Entry.");
            return;
          }
          genBtn.disabled = true;
          genBtn.textContent = "Generating...";
          try {
            const res = await api(
              `/api/stories/${encodeURIComponent(state.currentStory.id)}/cards/generate`,
              {
                method: "POST",
                body: JSON.stringify({
                  title,
                  card_type: card.card_type || "Custom",
                }),
              }
            );
            if ((card.entry || "").trim() && !(card.description || "").trim()) {
              card.description = card.entry.trim();
            }
            card.entry = res.entry || "";
            entryInput.value = card.entry;
            if (!(card.keys || "").trim()) {
              card.keys = title;
              keysInput.value = card.keys;
            }
          } catch (err) {
            showError(err.message);
          } finally {
            genBtn.disabled = false;
            genBtn.textContent = "✨ Generate Entry";
          }
        };
        genRow.appendChild(genBtn);
        box.appendChild(genRow);
      }
      const descInput = document.createElement("textarea");
      descInput.rows = 2;
      descInput.placeholder = showCcFields
        ? "Notes / Description (shown to players during Character Creation; AI doesn't see this)"
        : "Notes / Description (player/script notes; AI doesn't see this)";
      descInput.value = card.description || "";
      descInput.oninput = () => {
        card.description = descInput.value;
      };
      box.append(descInput);

      if (showCcFields) {
        const ccLabel = document.createElement("label");
        ccLabel.className = "checkbox-row";
        ccLabel.style.fontSize = "0.78rem";
        const ccCb = document.createElement("input");
        ccCb.type = "checkbox";
        ccCb.checked = Boolean(card.use_for_character_creation);
        ccCb.onchange = () => {
          card.use_for_character_creation = ccCb.checked;
        };
        const ccTxt = document.createElement("span");
        ccTxt.textContent = "Selectable in Character Creator";
        ccLabel.append(ccCb, ccTxt);
        box.append(ccLabel);
      }
      container.appendChild(box);
    });
  }

  function renderStoryCardsList() {
    const cards = state.currentStory?.story_cards || [];
    const currentFilter = els.storyCardsTypeFilter.value;
    const types = Array.from(new Set(cards.map((c) => c.card_type || "Custom"))).sort();
    els.storyCardsTypeFilter.innerHTML = '<option value="">All Types</option>';
    for (const t of types) {
      const opt = document.createElement("option");
      opt.value = t;
      opt.textContent = t;
      els.storyCardsTypeFilter.appendChild(opt);
    }
    if (types.includes(currentFilter)) {
      els.storyCardsTypeFilter.value = currentFilter;
    }

    renderCardEditors(els.storyCardsList, cards, {
      search: els.storyCardsSearch.value,
      cardType: els.storyCardsTypeFilter.value,
      allowAiGenerate: true,
      onChange: renderStoryCardsList,
    });
  }

  function renderScenarioCardsList() {
    renderCardEditors(els.scenarioCardsList, state.editingScenarioCards, {
      showCcFields: true,
      onChange: renderScenarioCardsList,
    });
  }

  function hasAnyScriptCode(scObj) {
    if (!scObj) return false;
    return ["library", "input", "context", "output"].some((k) => Boolean((scObj[k] || "").trim()));
  }

  function renderScriptMessageBanner() {
    const msg = state.currentStory?.script_state?.message;
    const dismissed = state.currentStory?.dismissed_script_message;
    if (msg && String(msg).trim() && String(msg) !== String(dismissed || "")) {
      els.scriptMessageBanner.textContent = String(msg);
      els.scriptMessageBanner.classList.remove("hidden");
    } else {
      els.scriptMessageBanner.textContent = "";
      els.scriptMessageBanner.classList.add("hidden");
    }
  }

  function renderScriptSelectOptions(selectEl) {
    selectEl.innerHTML = "";
    if (state.scripts.length === 0) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "No saved scripts yet";
      selectEl.appendChild(opt);
      return;
    }
    for (const sc of state.scripts) {
      const opt = document.createElement("option");
      opt.value = sc.id;
      opt.textContent = `${sc.name} (${sc.version || "1.0"})`;
      selectEl.appendChild(opt);
    }
  }

  function renderAttachedScripts(container, attachedList, onChange) {
    container.innerHTML = "";
    if (!attachedList || attachedList.length === 0) {
      const empty = document.createElement("div");
      empty.className = "cards-help";
      empty.textContent = "No attached Scripts yet.";
      container.appendChild(empty);
      return;
    }

    attachedList.forEach((entry, idx) => {
      const meta = state.scripts.find((s) => s.id === entry.script_id);
      const card = document.createElement("div");
      card.className = "attached-script-card" + (entry.enabled === false ? " disabled" : "");

      const head = document.createElement("div");
      head.className = "attached-script-head";

      const name = document.createElement("div");
      name.className = "attached-script-name";
      name.textContent = meta ? meta.name : `Missing Script (${entry.script_id})`;

      const ctrls = document.createElement("div");
      ctrls.className = "attached-script-controls";

      const upBtn = document.createElement("button");
      upBtn.type = "button";
      upBtn.className = "mini-btn";
      upBtn.textContent = "↑";
      upBtn.disabled = idx === 0;
      upBtn.onclick = () => {
        const tmp = attachedList[idx - 1];
        attachedList[idx - 1] = attachedList[idx];
        attachedList[idx] = tmp;
        onChange();
      };

      const downBtn = document.createElement("button");
      downBtn.type = "button";
      downBtn.className = "mini-btn";
      downBtn.textContent = "↓";
      downBtn.disabled = idx === attachedList.length - 1;
      downBtn.onclick = () => {
        const tmp = attachedList[idx + 1];
        attachedList[idx + 1] = attachedList[idx];
        attachedList[idx] = tmp;
        onChange();
      };

      const toggleLabel = document.createElement("label");
      toggleLabel.className = "toggle-switch";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = entry.enabled !== false;
      cb.onchange = () => {
        entry.enabled = cb.checked;
        onChange();
      };
      const slider = document.createElement("span");
      slider.className = "toggle-slider";
      toggleLabel.append(cb, slider);

      ctrls.append(upBtn, downBtn, toggleLabel);
      head.append(name, ctrls);
      card.appendChild(head);

      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.className = "cards-help";
      summary.style.cursor = "pointer";
      summary.textContent = meta ? `v${meta.version || "1.0"} · Details & Actions` : "Details";
      details.appendChild(summary);

      const desc = document.createElement("div");
      desc.className = "cards-help";
      desc.style.marginTop = "6px";
      desc.textContent = meta?.description || "No description.";
      details.appendChild(desc);

      const rowActions = document.createElement("div");
      rowActions.className = "plot-card-foot";
      rowActions.style.marginTop = "6px";
      if (meta) {
        const editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "chip-btn";
        editBtn.textContent = "Edit Code";
        editBtn.onclick = () => openScriptEditor("reusable", meta);
        rowActions.appendChild(editBtn);
      }
      const remBtn = document.createElement("button");
      remBtn.type = "button";
      remBtn.className = "chip-btn";
      remBtn.textContent = "Remove";
      remBtn.onclick = () => {
        attachedList.splice(idx, 1);
        onChange();
      };
      rowActions.appendChild(remBtn);
      details.appendChild(rowActions);
      card.appendChild(details);
      container.appendChild(card);
    });
  }

  function renderStoryScriptsPanel() {
    const s = state.currentStory;
    if (!s) return;
    if (!s.builtin_script) {
      s.builtin_script = { enabled: true, library: "", input: "", context: "", output: "" };
    }
    if (!Array.isArray(s.attached_scripts)) s.attached_scripts = [];
    els.storyBuiltinEnabled.checked = s.builtin_script.enabled !== false;
    els.storyBuiltinStatus.textContent = hasAnyScriptCode(s.builtin_script) ? "Active" : "Empty";
    renderScriptSelectOptions(els.storyAttachScriptSelect);
    renderAttachedScripts(els.storyAttachedScriptsList, s.attached_scripts, renderStoryScriptsPanel);
    const logs = s.script_logs || [];
    els.storyScriptLogs.textContent = logs.length > 0 ? logs.join("\n") : "(No logs yet)";
  }

  function renderScenarioScriptsPanel() {
    els.scenarioScriptStatus.textContent = hasAnyScriptCode(state.editingScenarioBuiltinScript)
      ? "Configured"
      : "Empty";
    renderScriptSelectOptions(els.scenarioAttachScriptSelect);
    renderAttachedScripts(
      els.scenarioAttachedScriptsList,
      state.editingScenarioAttachedScripts,
      renderScenarioScriptsPanel
    );
  }

  function openScriptEditor(target, reusableObj = null) {
    let draft;
    let title = "Built-in Script";
    const showMeta = target === "reusable" || target === "new_reusable";
    if (target === "reusable" && reusableObj) {
      draft = { ...reusableObj };
      title = `Edit Script: ${reusableObj.name}`;
    } else if (target === "new_reusable") {
      draft = { name: "", version: "1.0", description: "", library: "", input: "", context: "", output: "" };
      title = "Create Reusable Script";
    } else if (target === "scenario_builtin") {
      draft = { ...state.editingScenarioBuiltinScript };
      title = "Scenario Built-in Script";
    } else {
      draft = { ...(state.currentStory?.builtin_script || { enabled: true, library: "", input: "", context: "", output: "" }) };
      title = "Adventure Built-in Script";
    }

    state.scriptEditor = { target, hook: "input", draft };
    els.scriptEditorTitle.textContent = title;
    els.scriptMetaFields.classList.toggle("hidden", !showMeta);
    if (showMeta) {
      els.scriptMetaName.value = draft.name || "";
      els.scriptMetaVersion.value = draft.version || "1.0";
      els.scriptMetaDesc.value = draft.description || "";
    }
    els.scriptHookTabs.forEach((t) => t.classList.toggle("active", t.dataset.hookTab === "input"));
    els.scriptCodeEditor.value = draft.input || "";
    els.scriptTestOutput.classList.add("hidden");
    els.scriptTestOutput.textContent = "";
    els.scriptEditorModal.classList.remove("hidden");
  }

  function populateSettingsPanel() {
    const s = state.currentStory;
    if (!s) return;
    if (!Array.isArray(s.story_cards)) s.story_cards = [];
    els.storyTitle.value = s.title || "Untitled Adventure";
    els.storyDetailsTitle.value = s.title || "Untitled Adventure";
    els.storyDetailsDesc.value = s.description || "";
    els.storyDetailsTags.value = (s.tags || []).join(", ");
    els.storyAiInstructions.value = s.ai_instructions || "";
    els.storySummaryInput.value = s.story_summary || "";
    els.plotEssentialsInput.value = s.plot_essentials || "";
    els.authorsNoteInput.value = s.authors_note || "";
    els.storyThirdPerson.checked = Boolean(s.third_person);
    els.storyCharacterName.value = s.character_name || "";
    updateStoryThirdPersonUI();
    renderStoryCardsList();
    renderStoryScriptsPanel();
    renderScriptMessageBanner();
    els.settingTemp.value = s.settings?.temperature ?? 0.85;
    els.settingMaxTokens.value = s.settings?.max_tokens ?? 320;
    els.settingTopP.value = s.settings?.top_p ?? 0.95;
    els.settingTopK.value = s.settings?.top_k ?? 64;
    els.settingRepeatPenalty.value = s.settings?.repeat_penalty ?? 1.05;
    els.settingPresencePenalty.value = s.settings?.presence_penalty ?? 0;
    els.settingFrequencyPenalty.value = s.settings?.frequency_penalty ?? 0;
    syncContextLengthControls(s.settings?.context_length ?? 16384);
    els.settingAutoSummarize.checked = Boolean(s.settings?.auto_summarize);
    els.settingMemoryBank.checked = Boolean(s.settings?.memory_bank_enabled);
    els.settingRawOutput.checked = Boolean(s.settings?.raw_model_output);
    els.settingFollowLatest.checked = s.settings?.follow_latest_text !== false;
    const effort = normalizeReasoningEffort(
      s.settings?.reasoning_effort,
      s.settings?.enable_thinking
    );
    syncReasoningEffortUI(effort);
  }

  async function cycleRetryVariant(dir, variantIdx = null) {
    if (!state.currentStory || state.isGenerating) return;
    const payload = variantIdx !== null ? { variant_idx: variantIdx } : { direction: dir };
    const res = await api(
      `/api/stories/${encodeURIComponent(state.currentStory.id)}/retry-cycle`,
      { method: "POST", body: JSON.stringify(payload) }
    );
    state.currentStory = res.story;
    if (variantIdx === null) {
      renderStoryFeed();
    }
    refreshStoriesList();
  }

  function renderSegmentActionBar() {
    const bar = els.segmentActionBar;
    if (!bar) return;
    const segs = state.currentStory?.segments || [];
    const seg = segs.find((s) => s.id === state.activeToolbarSegmentId);
    if (!seg || state.isGenerating || state.editingSegmentId) {
      bar.innerHTML = "";
      bar.classList.add("hidden");
      return;
    }

    bar.innerHTML = "";
    const badge = document.createElement("span");
    badge.className = "seg-badge";
    badge.textContent = seg.kind === "opening" ? "opening (fixed)" : seg.kind;
    bar.appendChild(badge);

    if (seg.kind !== "opening") {
      const editBtn = document.createElement("button");
      editBtn.type = "button";
      editBtn.className = "seg-action-btn";
      editBtn.textContent = "Edit";
      editBtn.onclick = () => {
        state.activeToolbarSegmentId = null;
        state.editingSegmentId = seg.id;
        renderStoryFeed();
      };

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "seg-action-btn del";
      delBtn.textContent = "Delete";
      delBtn.onclick = async () => {
        state.activeToolbarSegmentId = null;
        await deleteSegment(seg.id);
      };

      const eraseBtn = document.createElement("button");
      eraseBtn.type = "button";
      eraseBtn.className = "seg-action-btn del";
      eraseBtn.title = "Erase this and all following segments (/eth)";
      eraseBtn.textContent = "Erase to Here";
      eraseBtn.onclick = async () => {
        state.activeToolbarSegmentId = null;
        const res = await api(
          `/api/stories/${encodeURIComponent(state.currentStory.id)}/erase-to-here`,
          { method: "POST", body: JSON.stringify({ seg_id: seg.id }) }
        );
        state.currentStory = res.story;
        renderStoryFeed();
        refreshStoriesList();
      };

      bar.append(editBtn, delBtn, eraseBtn);

      if (seg.kind === "ai" && state.currentStory?.last_generation_context) {
        const ctxBtn = document.createElement("button");
        ctxBtn.type = "button";
        const ctxWarnings = state.currentStory.last_generation_context.warnings || [];
        ctxBtn.className = "seg-action-btn" + (ctxWarnings.length > 0 ? " has-warning" : "");
        ctxBtn.title =
          ctxWarnings.length > 0
            ? `Context Warning: ${ctxWarnings[0]}`
            : "Inspect the context sent for the last AI generation";
        ctxBtn.textContent = ctxWarnings.length > 0 ? "⚠ View Context" : "View Context";
        ctxBtn.onclick = () => openContextViewer("last");
        bar.appendChild(ctxBtn);
      }

      const isLastAiMulti =
        seg.kind === "ai" &&
        seg.id === segs[segs.length - 1]?.id &&
        Array.isArray(seg.variants) &&
        seg.variants.length > 1;
      if (isLastAiMulti) {
        const prevV = document.createElement("button");
        prevV.type = "button";
        prevV.className = "seg-action-btn";
        prevV.textContent = "‹";
        prevV.title = "Previous retry generation";
        prevV.onclick = () => cycleRetryVariant(-1);

        const badgeV = document.createElement("span");
        badgeV.className = "seg-action-btn";
        badgeV.style.cursor = "default";
        badgeV.textContent = `${(seg.variant_idx ?? 0) + 1}/${seg.variants.length}`;

        const nextV = document.createElement("button");
        nextV.type = "button";
        nextV.className = "seg-action-btn";
        nextV.textContent = "›";
        nextV.title = "Next retry generation";
        nextV.onclick = () => cycleRetryVariant(1);

        bar.append(prevV, badgeV, nextV);
      }

      if (seg.kind === "do" || seg.kind === "say") {
        const nameBtn = document.createElement("button");
        nameBtn.type = "button";
        nameBtn.className = "seg-action-btn";
        nameBtn.title = "Set or update Third Person character name";
        nameBtn.textContent = "Change Name";
        nameBtn.onclick = async () => {
          const next = window.prompt(
            "Character Name (enables Third Person / character.name):",
            state.currentStory?.character_name || ""
          );
          if (next === null) return;
          const data = await api(`/api/stories/${encodeURIComponent(state.currentStory.id)}`, {
            method: "PATCH",
            body: JSON.stringify({
              character_name: next.trim(),
              third_person: Boolean(next.trim()) || Boolean(state.currentStory?.third_person),
            }),
          });
          state.currentStory = data.story;
          populateSettingsPanel();
          updateModeUI();
        };
        bar.appendChild(nameBtn);
      }
    }

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "seg-action-btn seg-bar-close";
    closeBtn.textContent = "×";
    closeBtn.title = "Deselect";
    closeBtn.onclick = () => {
      state.activeToolbarSegmentId = null;
      els.storyFeed.querySelectorAll(".segment.toolbar-open").forEach((node) => {
        node.classList.remove("toolbar-open");
      });
      renderSegmentActionBar();
    };
    bar.appendChild(closeBtn);
    bar.classList.remove("hidden");
  }

  function renderStoryFeed() {
    const feed = els.storyFeed;
    feed.innerHTML = "";

    const worldDesc = (state.currentStory?.world_description || "").trim();
    if (worldDesc) {
      const wd = document.createElement("div");
      wd.className = "world-desc-banner";
      wd.textContent = worldDesc;
      feed.appendChild(wd);
    }

    const segs = state.currentStory?.segments || [];
    if (segs.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = worldDesc
        ? "Generating your opening scene, or type below to start..."
        : "Your story is a blank page. Use Story mode to set the scene, or Do / Say to jump right in.";
      feed.appendChild(empty);
      renderSegmentActionBar();
      updateControlsState();
      return;
    }

    let activeProseRun = null;
    let prevInlineSeg = null;

    for (const seg of segs) {
      const canSwipeRetry =
        !state.isGenerating &&
        state.editingSegmentId !== seg.id &&
        seg.kind === "ai" &&
        seg.id === segs[segs.length - 1]?.id &&
        Array.isArray(seg.variants) &&
        seg.variants.length > 1;
      const isEditing = state.editingSegmentId === seg.id;

      if (isEditing) {
        activeProseRun = null;
        prevInlineSeg = null;
        const el = document.createElement("div");
        el.className = `segment kind-${seg.kind} segment-editing`;
        el.dataset.segId = seg.id;

        const box = document.createElement("div");
        box.className = "segment-edit-box";
        const ta = document.createElement("textarea");
        ta.rows = Math.max(2, Math.min(10, seg.text.split("\n").length + 1));
        ta.value = seg.text;
        const actions = document.createElement("div");
        actions.className = "segment-edit-actions";

        const cancelBtn = document.createElement("button");
        cancelBtn.type = "button";
        cancelBtn.className = "secondary-btn";
        cancelBtn.textContent = "Cancel";
        cancelBtn.onclick = () => {
          state.editingSegmentId = null;
          renderStoryFeed();
        };

        const saveBtn = document.createElement("button");
        saveBtn.type = "button";
        saveBtn.className = "primary-btn";
        saveBtn.textContent = "Save";
        saveBtn.onclick = async () => {
          await saveEditedSegment(seg.id, ta.value);
        };

        actions.append(cancelBtn, saveBtn);
        box.append(ta, actions);
        el.appendChild(box);
        feed.appendChild(el);
        continue;
      }

      const bindSegmentToolbarClick = (el, shouldIgnore = null) => {
        el.addEventListener("click", (e) => {
          if (
            (shouldIgnore && shouldIgnore()) ||
            state.isGenerating ||
            e.target.closest(".segment-edit-box") ||
            window.getSelection()?.toString()
          ) {
            return;
          }
          state.activeToolbarSegmentId =
            state.activeToolbarSegmentId === seg.id ? null : seg.id;
          feed.querySelectorAll(".segment").forEach((node) => {
            node.classList.toggle(
              "toolbar-open",
              node.dataset.segId === state.activeToolbarSegmentId
            );
          });
          renderSegmentActionBar();
        });
      };

      if (seg.kind === "do" || seg.kind === "say") {
        activeProseRun = null;
        prevInlineSeg = null;
        const el = document.createElement("div");
        el.className =
          `segment segment-action kind-${seg.kind}` +
          (state.activeToolbarSegmentId === seg.id ? " toolbar-open" : "");
        el.dataset.segId = seg.id;

        const textSpan = document.createElement("span");
        textSpan.className = "segment-text";
        textSpan.textContent = seg.text;

        el.appendChild(textSpan);
        bindSegmentToolbarClick(el);
        feed.appendChild(el);
        continue;
      }

      const el = document.createElement("span");
      el.className =
        `segment segment-inline kind-${seg.kind}` +
        (state.activeToolbarSegmentId === seg.id ? " toolbar-open" : "") +
        (canSwipeRetry ? " swipable-retry" : "");
      el.dataset.segId = seg.id;

      let justSwiped = false;
      const textSpan = document.createElement("span");
      textSpan.className = "segment-text";
      textSpan.textContent = seg.text;
      el.appendChild(textSpan);

      if (canSwipeRetry) {
        let startX = 0;
        let startY = 0;
        let startTime = 0;
        let dragDx = 0;
        let axisLock = null;

        el.addEventListener(
          "touchstart",
          (e) => {
            if (e.touches.length !== 1) return;
            startX = e.touches[0].clientX;
            startY = e.touches[0].clientY;
            startTime = Date.now();
            dragDx = 0;
            axisLock = null;
          },
          { passive: true }
        );
        el.addEventListener(
          "touchmove",
          (e) => {
            if (e.touches.length !== 1 || axisLock === "y") return;
            const dx = e.touches[0].clientX - startX;
            const dy = e.touches[0].clientY - startY;
            if (axisLock === null) {
              if (Math.abs(dx) > 14 && Math.abs(dx) > Math.abs(dy) * 1.4) {
                axisLock = "x";
                justSwiped = true;
              } else if (Math.abs(dy) > 12) {
                axisLock = "y";
                return;
              } else {
                return;
              }
            }
            dragDx = dx;
          },
          { passive: true }
        );
        const finishDrag = (commit) => {
          if (axisLock === "x") {
            const elapsed = Math.max(1, Date.now() - startTime);
            const vx = dragDx / elapsed;
            if (commit && !window.getSelection()?.toString()) {
              if (dragDx < -80 || (dragDx < -48 && vx < -0.5)) {
                cycleRetryVariant(1).catch((err) => showError(err.message));
              } else if (dragDx > 80 || (dragDx > 48 && vx > 0.5)) {
                cycleRetryVariant(-1).catch((err) => showError(err.message));
              }
            }
            setTimeout(() => {
              justSwiped = false;
            }, 140);
          }
          axisLock = null;
        };
        el.addEventListener("touchend", () => finishDrag(true), { passive: true });
        el.addEventListener("touchcancel", () => finishDrag(false), { passive: true });
      }

      bindSegmentToolbarClick(el, () => justSwiped);

      if (!activeProseRun) {
        activeProseRun = document.createElement("div");
        activeProseRun.className = "prose-run";
        feed.appendChild(activeProseRun);
      }
      if (prevInlineSeg) {
        const sep = segmentJoinSeparator(prevInlineSeg, seg);
        if (sep) {
          activeProseRun.appendChild(document.createTextNode(sep));
        }
      }
      activeProseRun.appendChild(el);
      prevInlineSeg = seg;
    }

    renderSegmentActionBar();
    updateControlsState();
  }

  function setHomeTab(tab) {
    state.homeTab = tab === "scenarios" ? "scenarios" : "adventures";
    els.homeTabs.forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.homeTab === state.homeTab);
    });
    els.homePaneAdventures.classList.toggle("hidden", state.homeTab !== "adventures");
    els.homePaneScenarios.classList.toggle("hidden", state.homeTab !== "scenarios");
  }

  function setActiveView(view) {
    const isPlay = view === "play" && Boolean(state.currentStory);
    state.activeView = isPlay ? "play" : "home";
    els.homeView.classList.toggle("hidden", isPlay);
    els.stageView.classList.toggle("hidden", !isPlay);
    els.llmPill.classList.toggle("hidden", !isPlay);
    els.btnHome.classList.toggle("hidden", !isPlay);
    els.homeBrand.classList.toggle("hidden", isPlay);
    els.storyTitle.classList.toggle("hidden", !isPlay);
    els.btnEndpoint.classList.toggle("hidden", isPlay);
    els.btnUndo.classList.toggle("hidden", !isPlay);
    els.btnRedo.classList.toggle("hidden", !isPlay);
    els.btnContext.classList.toggle("hidden", !isPlay);
    els.btnSettings.classList.toggle("hidden", !isPlay);
    if (!isPlay) {
      els.drawerSettings.classList.add("hidden");
    }
  }

  function renderStoriesList() {
    els.homeAdventuresGrid.innerHTML = "";
    if (state.stories.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "No adventures yet. Switch to the Scenarios tab to start one!";
      els.homeAdventuresGrid.appendChild(empty);
      return;
    }

    for (const item of state.stories) {
      const card = document.createElement("div");
      card.className = "home-card clickable";
      card.onclick = () => loadStoryById(item.id);

      const head = document.createElement("div");
      head.className = "home-card-head";

      const title = document.createElement("div");
      title.className = "home-card-title";
      title.textContent = item.title || "Untitled Adventure";

      const badge = document.createElement("span");
      badge.className = "home-card-badge";
      badge.textContent = `${item.segment_count ?? 1} segs`;

      head.append(title, badge);

      const preview = document.createElement("div");
      preview.className = "home-card-desc";
      preview.textContent = item.preview || "Empty story";

      const actions = document.createElement("div");
      actions.className = "home-card-actions";

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "ghost-btn del";
      delBtn.textContent = "Delete";
      delBtn.onclick = async (e) => {
        e.stopPropagation();
        await deleteStoryById(item.id);
      };

      actions.append(delBtn);
      card.append(head, preview, actions);
      els.homeAdventuresGrid.appendChild(card);
    }
  }

  function showScenarioError(msg) {
    if (!msg) {
      els.scenarioFormError.classList.add("hidden");
      els.scenarioFormError.textContent = "";
      return;
    }
    els.scenarioFormError.textContent = msg;
    els.scenarioFormError.classList.remove("hidden");
  }

  function makeBlankChoice() {
    return {
      id: Math.random().toString(16).slice(2, 10),
      label: "",
      description: "",
      opening: "",
      plot_essentials: "",
      ai_instructions: "",
      story_summary: "",
      authors_note: "",
      third_person: null,
      character_name: "",
      story_cards: [],
      choices: [],
    };
  }

  function cloneChoiceNode(ch) {
    return {
      ...ch,
      story_cards: (ch.story_cards || []).map((c) => ({ ...c })),
      attached_scripts: (ch.attached_scripts || []).map((s) => ({ ...s })),
      choices: (ch.choices || []).map(cloneChoiceNode),
    };
  }

  function renderChoiceNodes(nodes, container, depth = 0) {
    nodes.forEach((ch, idx) => {
      if (!Array.isArray(ch.choices)) ch.choices = [];
      const box = document.createElement("div");
      box.className = "choice-editor-box" + (depth > 0 ? " nested" : "");

      const head = document.createElement("div");
      head.className = "choice-editor-head";
      const badge = document.createElement("span");
      badge.className = "choice-depth-badge";
      badge.textContent = depth === 0 ? `Option ${idx + 1}` : `Sub-Option (L${depth + 1}.${idx + 1})`;

      const headActions = document.createElement("div");
      headActions.className = "choice-head-actions";
      if (depth < 4) {
        const subBtn = document.createElement("button");
        subBtn.type = "button";
        subBtn.className = "chip-btn";
        subBtn.textContent = "+ Sub-Choice";
        subBtn.onclick = () => {
          ch.choices.push(makeBlankChoice());
          renderScenarioChoicesList();
        };
        headActions.appendChild(subBtn);
      }

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "clear-card-btn";
      delBtn.textContent = "🗑";
      delBtn.onclick = () => {
        nodes.splice(idx, 1);
        renderScenarioChoicesList();
      };
      headActions.appendChild(delBtn);
      head.append(badge, headActions);

      const labelInput = document.createElement("input");
      labelInput.type = "text";
      labelInput.placeholder = "Choice label (e.g., Play as the Vampire)";
      labelInput.value = ch.label || "";
      labelInput.oninput = () => {
        ch.label = labelInput.value;
      };

      const descInput = document.createElement("input");
      descInput.type = "text";
      descInput.placeholder = "Player-facing description (optional)";
      descInput.value = ch.description || "";
      descInput.oninput = () => {
        ch.description = descInput.value;
      };

      const openInput = document.createElement("textarea");
      openInput.rows = ch.choices.length > 0 ? 2 : 3;
      openInput.placeholder =
        ch.choices.length > 0
          ? "Optional group/branch opening (inherited by child options if empty)..."
          : "Opening prompt for this choice...";
      openInput.value = ch.opening || "";
      openInput.oninput = () => {
        ch.opening = openInput.value;
      };

      const adv = document.createElement("details");
      adv.className = "choice-advanced-details";
      if (ch.ai_instructions || ch.plot_essentials || ch.authors_note) {
        adv.open = true;
      }
      const sum = document.createElement("summary");
      sum.textContent = "Option Plot Overrides (AI Instructions, Plot Essentials, Author's Note)";
      adv.appendChild(sum);

      const aiInp = document.createElement("textarea");
      aiInp.rows = 2;
      aiInp.placeholder = "Option AI Instructions (optional)...";
      aiInp.value = ch.ai_instructions || "";
      aiInp.oninput = () => {
        ch.ai_instructions = aiInp.value;
      };

      const peInp = document.createElement("textarea");
      peInp.rows = 2;
      peInp.placeholder = "Option Plot Essentials (optional)...";
      peInp.value = ch.plot_essentials || "";
      peInp.oninput = () => {
        ch.plot_essentials = peInp.value;
      };

      const anInp = document.createElement("input");
      anInp.type = "text";
      anInp.placeholder = "Option Author's Note (optional)...";
      anInp.value = ch.authors_note || "";
      anInp.oninput = () => {
        ch.authors_note = anInp.value;
      };

      adv.append(aiInp, peInp, anInp);
      box.append(head, labelInput, descInput, openInput, adv);

      if (ch.choices.length > 0) {
        const subWrap = document.createElement("div");
        subWrap.className = "choice-children-wrap";
        renderChoiceNodes(ch.choices, subWrap, depth + 1);
        box.appendChild(subWrap);
      }

      container.appendChild(box);
    });
  }

  function renderScenarioChoicesList() {
    els.scenarioChoicesList.innerHTML = "";
    renderChoiceNodes(state.editingScenarioChoices, els.scenarioChoicesList, 0);
  }

  function updateScenarioTypeUI() {
    const stype = els.scenarioTypeSelect.value;
    const showOpening = stype === "story" || stype === "character_creator";
    els.scenarioOpeningWrap.classList.toggle("hidden", !showOpening);
    els.scenarioOpeningCount.classList.toggle("hidden", !showOpening);
    els.scenarioOpeningInput.placeholder =
      stype === "character_creator"
        ? "World Description / Premise (AI uses this + selected Character Cards to generate the opening scene)"
        : "How does your story begin? Example: You are ${character.name}, a knight from ${enter a country...}";
    els.scenarioChoicesWrap.classList.toggle("hidden", stype !== "multiple_choice");
    els.scenarioCcNote.classList.toggle("hidden", stype !== "character_creator");
  }

  function resetScenarioForm() {
    state.editingScenarioId = null;
    state.editingScenarioChoices = [];
    state.editingScenarioCards = [];
    state.editingScenarioBuiltinScript = { enabled: true, library: "", input: "", context: "", output: "" };
    state.editingScenarioAttachedScripts = [];
    els.scenarioFormHeading.textContent = "Create Scenario";
    els.scenarioNameInput.value = "";
    els.scenarioTypeSelect.value = "story";
    els.scenarioOpeningInput.value = "";
    els.scenarioAiInstructions.value = "";
    els.scenarioStorySummary.value = "";
    els.scenarioPlotEssentials.value = "";
    els.scenarioAuthorsNote.value = "";
    els.scenarioThirdPerson.checked = false;
    els.scenarioCharacterName.value = "";
    updateScenarioTypeUI();
    updateScenarioOpeningCounter();
    updateScenarioThirdPersonUI();
    renderScenarioChoicesList();
    renderScenarioCardsList();
    renderScenarioScriptsPanel();
    els.btnCancelEditScenario.classList.add("hidden");
    showScenarioError("");
  }

  function openScenarioModal() {
    showScenarioError("");
    els.btnCloseScenarios.classList.remove("hidden");
    els.scenarioModal.classList.remove("hidden");
  }

  function closeScenarioModal() {
    els.scenarioModal.classList.add("hidden");
  }

  function loadScenarioIntoEditor(sc) {
    state.editingScenarioId = sc.id;
    state.editingScenarioChoices = (sc.choices || []).map(cloneChoiceNode);
    state.editingScenarioCards = (sc.story_cards || []).map((c) => ({ ...c }));
    state.editingScenarioBuiltinScript = { ...(sc.builtin_script || { enabled: true, library: "", input: "", context: "", output: "" }) };
    state.editingScenarioAttachedScripts = (sc.attached_scripts || []).map((x) => ({ ...x }));
    els.scenarioFormHeading.textContent = "Edit Scenario";
    els.scenarioNameInput.value = sc.name;
    els.scenarioTypeSelect.value = sc.scenario_type || "story";
    els.scenarioOpeningInput.value = sc.opening || "";
    els.scenarioAiInstructions.value = sc.ai_instructions || "";
    els.scenarioStorySummary.value = sc.story_summary || "";
    els.scenarioPlotEssentials.value = sc.plot_essentials || "";
    els.scenarioAuthorsNote.value = sc.authors_note || "";
    els.scenarioThirdPerson.checked = Boolean(sc.third_person);
    els.scenarioCharacterName.value = sc.character_name || "";
    updateScenarioTypeUI();
    updateScenarioOpeningCounter();
    updateScenarioThirdPersonUI();
    renderScenarioChoicesList();
    renderScenarioCardsList();
    renderScenarioScriptsPanel();
    els.btnCancelEditScenario.classList.remove("hidden");
    showScenarioError("");
  }

  function buildScenarioCardElement(sc, { isHome = false } = {}) {
    const typeLabel = sc.scenario_type === "multiple_choice"
      ? "Multiple Choice"
      : sc.scenario_type === "character_creator"
      ? "Character Creator"
      : "Story";
    const summaryText = sc.scenario_type === "multiple_choice"
      ? (sc.choices || []).map((c) => `• ${c.label}`).join("  ") || "Multiple choices"
      : sc.scenario_type === "character_creator"
      ? `Character Creator (${(sc.story_cards || []).length} Story Cards)`
      : sc.opening || "(No opening message)";

    const card = document.createElement("div");
    card.className = isHome ? "home-card clickable" : "scenario-card";
    if (isHome) {
      card.onclick = () => initiatePlayScenario(sc);
    }

    if (isHome) {
      const head = document.createElement("div");
      head.className = "home-card-head";
      const title = document.createElement("div");
      title.className = "home-card-title";
      title.textContent = sc.name;
      const badge = document.createElement("span");
      badge.className = "home-card-badge";
      badge.textContent = typeLabel;
      head.append(title, badge);
      card.appendChild(head);
    } else {
      const title = document.createElement("div");
      title.className = "scenario-card-title";
      title.textContent = sc.scenario_type && sc.scenario_type !== "story" ? `${sc.name} · ${typeLabel}` : sc.name;
      card.appendChild(title);
    }

    const opening = document.createElement("div");
    opening.className = isHome ? "home-card-desc" : "scenario-card-opening";
    opening.textContent = sc.description || summaryText;

    const actions = document.createElement("div");
    actions.className = isHome ? "home-card-actions" : "scenario-card-actions";

    const rightBtns = document.createElement("div");
    rightBtns.className = isHome ? "home-card-btns" : "";
    if (!isHome) rightBtns.style.display = "contents";

    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "ghost-btn";
    editBtn.textContent = "Edit";
    editBtn.onclick = (e) => {
      e.stopPropagation();
      loadScenarioIntoEditor(sc);
      if (isHome) openScenarioModal();
      els.scenarioNameInput.focus();
    };

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "ghost-btn del";
    delBtn.textContent = "Delete";
    delBtn.onclick = async (e) => {
      e.stopPropagation();
      await api(`/api/scenarios/${encodeURIComponent(sc.id)}`, { method: "DELETE" });
      if (state.editingScenarioId === sc.id) {
        resetScenarioForm();
      }
      await refreshScenariosList();
    };

    rightBtns.append(editBtn, delBtn);
    if (!isHome) {
      const playBtn = document.createElement("button");
      playBtn.type = "button";
      playBtn.className = "primary-btn";
      playBtn.textContent = "Play";
      playBtn.onclick = () => initiatePlayScenario(sc);
      actions.append(playBtn, rightBtns);
    } else {
      actions.append(rightBtns);
    }
    card.append(opening, actions);
    return card;
  }

  function renderScenariosGrid() {
    els.scenariosGrid.innerHTML = "";
    els.homeScenariosGrid.innerHTML = "";
    if (state.scenarios.length === 0) {
      const e1 = document.createElement("div");
      e1.className = "empty-state";
      e1.textContent = "No scenarios yet. Create one on the right!";
      els.scenariosGrid.appendChild(e1);

      const e2 = document.createElement("div");
      e2.className = "empty-state";
      e2.textContent = "No scenarios yet. Click + Create Scenario or Import!";
      els.homeScenariosGrid.appendChild(e2);
      return;
    }

    for (const sc of state.scenarios) {
      els.scenariosGrid.appendChild(buildScenarioCardElement(sc, { isHome: false }));
      els.homeScenariosGrid.appendChild(buildScenarioCardElement(sc, { isHome: true }));
    }
  }

  async function refreshScenariosList() {
    const data = await api("/api/scenarios");
    state.scenarios = data.scenarios || [];
    if (data.default_ai_instructions) {
      state.defaultAiInstructions = data.default_ai_instructions;
    }
    renderScenariosGrid();
  }

  async function refreshScriptsList() {
    const data = await api("/api/scripts");
    state.scripts = data.scripts || [];
    renderStoryScriptsPanel();
    renderScenarioScriptsPanel();
  }

  async function saveScenarioForm() {
    const name = els.scenarioNameInput.value.trim();
    const scenarioType = els.scenarioTypeSelect.value;
    const opening = els.scenarioOpeningInput.value.trim();
    if (!name) {
      showScenarioError("Please enter a scenario name.");
      return null;
    }
    if (scenarioType === "multiple_choice" && state.editingScenarioChoices.length === 0) {
      showScenarioError("Add at least one choice for Multiple Choice scenarios.");
      return null;
    }
    showScenarioError("");

    const payload = {
      name,
      scenario_type: scenarioType,
      opening,
      choices: state.editingScenarioChoices,
      ai_instructions: els.scenarioAiInstructions.value.trim(),
      story_summary: els.scenarioStorySummary.value.trim(),
      plot_essentials: els.scenarioPlotEssentials.value.trim(),
      authors_note: els.scenarioAuthorsNote.value.trim(),
      third_person: els.scenarioThirdPerson.checked,
      character_name: els.scenarioCharacterName.value.trim(),
      story_cards: state.editingScenarioCards,
      builtin_script: state.editingScenarioBuiltinScript,
      attached_scripts: state.editingScenarioAttachedScripts,
    };

    let data;
    if (state.editingScenarioId) {
      data = await api(
        `/api/scenarios/${encodeURIComponent(state.editingScenarioId)}`,
        {
          method: "PATCH",
          body: JSON.stringify(payload),
        }
      );
    } else {
      data = await api("/api/scenarios", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    }
    resetScenarioForm();
    await refreshScenariosList();
    return data.scenario;
  }

  function resolveChoiceChain(sc, choicePath = [], selectedLeafId = null) {
    const chain = [];
    let level = sc.choices || [];
    for (const cid of choicePath || []) {
      const found = level.find((c) => c.id === cid);
      if (!found) break;
      chain.push(found);
      level = found.choices || [];
    }
    let activeChoice = null;
    if (selectedLeafId) {
      const leaf = level.find((c) => c.id === selectedLeafId);
      if (leaf && !(leaf.choices && leaf.choices.length)) {
        activeChoice = leaf;
      }
    }
    if (!activeChoice && level.length > 0) {
      const firstLeaf = level.find((c) => !(c.choices && c.choices.length));
      if (firstLeaf) activeChoice = firstLeaf;
    }
    const effectiveChain = activeChoice ? [...chain, activeChoice] : [...chain];
    return { chain, currentOptions: level, activeChoice, effectiveChain };
  }

  function extractScenarioPlaceholderKeys(sc, choiceInput = null) {
    const chain = Array.isArray(choiceInput)
      ? choiceInput
      : choiceInput
      ? [choiceInput]
      : [];
    const texts = [
      sc.opening,
      sc.ai_instructions,
      sc.story_summary,
      sc.plot_essentials,
      sc.authors_note,
      sc.character_name,
    ];
    for (const ch of chain) {
      texts.push(
        ch.opening,
        ch.description,
        ch.plot_essentials,
        ch.ai_instructions,
        ch.story_summary,
        ch.authors_note,
        ch.character_name
      );
      for (const c of ch.story_cards || []) {
        texts.push(c.title, c.keys, c.entry);
      }
    }
    for (const c of sc.story_cards || []) {
      texts.push(c.title, c.keys, c.entry);
    }
    const seen = new Set();
    const keys = [];
    const re = /\$\{([^{}]+)\}/g;
    for (const t of texts) {
      if (!t) continue;
      let m;
      while ((m = re.exec(t)) !== null) {
        if (!seen.has(m[1])) {
          seen.add(m[1]);
          keys.push(m[1]);
        }
      }
    }
    return keys;
  }

  function getCharacterCreatorSteps(sc, ps) {
    const allCards = sc.story_cards || [];
    const ccFlagged = allCards.filter((c) => c.use_for_character_creation);
    const selectableCards = ccFlagged.length > 0 ? ccFlagged : allCards;

    const catMap = new Map();
    for (const c of selectableCards) {
      const rawCat = (c.card_type || "Custom").trim();
      const catLabel = rawCat ? rawCat.charAt(0).toUpperCase() + rawCat.slice(1) : "Custom";
      if (!catMap.has(catLabel)) catMap.set(catLabel, []);
      catMap.get(catLabel).push(c);
    }

    const steps = [{ kind: "name" }, { kind: "gender" }];
    for (const [category, cards] of catMap.entries()) {
      steps.push({ kind: "category", category, cards });
    }
    const extraKeys = extractScenarioPlaceholderKeys(sc, null).filter(
      (k) => k !== "character.name" && k !== "character.gender"
    );
    if (extraKeys.length > 0) {
      steps.push({ kind: "placeholders", keys: extraKeys });
    }
    return steps;
  }

  function syncPlaySetupScriptPills(ps) {
    if (!ps) return;
    const isOn = Boolean(ps.enableInnerSelf);
    const acOn = Boolean(ps.enableAutoCards);
    if (els.btnSetupInnerSelf) {
      els.btnSetupInnerSelf.classList.toggle("active", isOn);
      els.btnSetupInnerSelf.setAttribute("aria-pressed", String(isOn));
    }
    if (els.btnSetupAutoCards) {
      els.btnSetupAutoCards.classList.toggle("active", acOn);
      els.btnSetupAutoCards.setAttribute("aria-pressed", String(acOn));
      els.btnSetupAutoCards.title =
        isOn && acOn
          ? "Auto-Cards enabled via Inner Self's integrated mode (no conflicts)"
          : "Enable Auto-Cards (auto-create & update Story Cards)";
    }
  }

  function renderPlaySetupModal() {
    const ps = state.playSetup;
    if (!ps) return;
    const sc = ps.scenario;
    els.playSetupTitle.textContent = sc.name;
    els.playSetupBody.innerHTML = "";
    syncPlaySetupScriptPills(ps);

    const mcState =
      sc.scenario_type === "multiple_choice"
        ? resolveChoiceChain(sc, ps.choicePath || [], ps.choiceId)
        : null;
    const activeChoice = mcState ? mcState.activeChoice : null;
    if (mcState) {
      ps.choiceId = activeChoice ? activeChoice.id : null;
    }

    if (sc.scenario_type === "character_creator") {
      if (ps.ccPhase === "gate") {
        els.playSetupSubtitle.textContent = "Choose One...";
        els.btnBackPlaySetup.classList.add("hidden");
        els.btnNextPlaySetup.classList.add("hidden");
        els.btnConfirmPlaySetup.classList.add("hidden");

        const gate = document.createElement("div");
        gate.className = "cc-gate-choices";

        const qsBtn = document.createElement("button");
        qsBtn.type = "button";
        qsBtn.className = "cc-gate-btn";
        qsBtn.innerHTML =
          "<strong>⚡ Quickstart</strong><span>Jump right in with a randomly generated Name, Gender, and Story Card combination.</span>";
        qsBtn.onclick = async () => {
          qsBtn.disabled = true;
          try {
            await startStoryFromScenario(sc.id, {
              quickstart: true,
              autoGenerate: true,
              enableInnerSelf: Boolean(ps.enableInnerSelf),
              enableAutoCards: Boolean(ps.enableAutoCards),
            });
          } finally {
            qsBtn.disabled = false;
          }
        };

        const ccBtn = document.createElement("button");
        ccBtn.type = "button";
        ccBtn.className = "cc-gate-btn";
        ccBtn.innerHTML =
          "<strong>🧬 Create a Character</strong><span>Walk step-by-step through Name, Gender, and each character category.</span>";
        ccBtn.onclick = () => {
          ps.ccPhase = "wizard";
          ps.ccStep = 0;
          renderPlaySetupModal();
        };

        gate.append(qsBtn, ccBtn);
        els.playSetupBody.appendChild(gate);
        return;
      }

      const steps = getCharacterCreatorSteps(sc, ps);
      ps.ccStep = Math.max(0, Math.min(steps.length - 1, ps.ccStep || 0));
      const step = steps[ps.ccStep];
      const isLast = ps.ccStep === steps.length - 1;

      els.playSetupSubtitle.textContent = `Step ${ps.ccStep + 1} of ${steps.length}`;
      els.btnBackPlaySetup.classList.remove("hidden");
      els.btnNextPlaySetup.classList.toggle("hidden", isLast);
      els.btnConfirmPlaySetup.classList.toggle("hidden", !isLast);

      if (step.kind === "name") {
        const field = document.createElement("div");
        field.className = "form-field";
        const lbl = document.createElement("label");
        lbl.className = "field-label";
        lbl.textContent = "What is your character's name?";
        const inp = document.createElement("input");
        inp.type = "text";
        inp.value = ps.answers["character.name"] || "";
        inp.placeholder = "Enter character name...";
        inp.oninput = () => {
          ps.answers["character.name"] = inp.value;
        };
        inp.onkeydown = (e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            ps.ccStep += 1;
            renderPlaySetupModal();
          }
        };
        field.append(lbl, inp);
        els.playSetupBody.appendChild(field);
        setTimeout(() => inp.focus(), 0);
      } else if (step.kind === "gender") {
        const who = (ps.answers["character.name"] || "").trim();
        const field = document.createElement("div");
        field.className = "form-field";
        const lbl = document.createElement("label");
        lbl.className = "field-label";
        lbl.textContent = who ? `${who}, what is your gender?` : "What is your gender?";
        const row = document.createElement("div");
        row.className = "cc-gender-row";

        const currentGender = ps.answers["character.gender"] || "";
        for (const preset of ["Male", "Female"]) {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "chip-btn" + (currentGender === preset ? " active" : "");
          btn.textContent = preset;
          btn.onclick = () => {
            ps.answers["character.gender"] = preset;
            renderPlaySetupModal();
          };
          row.appendChild(btn);
        }
        const customInp = document.createElement("input");
        customInp.type = "text";
        customInp.style.flex = "1";
        customInp.placeholder = "Custom...";
        customInp.value = currentGender !== "Male" && currentGender !== "Female" ? currentGender : "";
        customInp.oninput = () => {
          ps.answers["character.gender"] = customInp.value;
        };
        row.appendChild(customInp);
        field.append(lbl, row);
        els.playSetupBody.appendChild(field);
      } else if (step.kind === "category") {
        const hdr = document.createElement("label");
        hdr.className = "field-label";
        hdr.textContent = `Choose ${step.category} (${step.cards.length} options)`;
        els.playSetupBody.appendChild(hdr);

        const searchInp = document.createElement("input");
        searchInp.type = "text";
        searchInp.placeholder = `Search ${step.category}...`;
        searchInp.value = ps.ccSearch || "";
        els.playSetupBody.appendChild(searchInp);

        const grid = document.createElement("div");
        grid.className = "cc-cards-grid";

        const selectedInCat = ps.ccByCategory[step.category] || null;
        const renderGrid = () => {
          grid.innerHTML = "";
          const q = (ps.ccSearch || "").trim().toLowerCase();
          const list = step.cards.filter((c) => {
            if (!q) return true;
            return (
              (c.title || "").toLowerCase().includes(q) ||
              (c.description || "").toLowerCase().includes(q) ||
              (c.entry || "").toLowerCase().includes(q)
            );
          });
          for (const card of list) {
            const picked = selectedInCat === card.id;
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "cc-option-card" + (picked ? " selected" : "");

            const head = document.createElement("div");
            head.className = "cc-option-head";
            const t = document.createElement("span");
            t.textContent = card.title || "Option";
            const check = document.createElement("span");
            check.textContent = picked ? "✓" : "";
            head.append(t, check);

            const body = document.createElement("div");
            body.className = "cc-card-entry";
            body.textContent = (card.description || card.entry || "").trim();

            btn.append(head, body);
            btn.onclick = () => {
              if (picked) {
                delete ps.ccByCategory[step.category];
              } else {
                ps.ccByCategory[step.category] = card.id;
              }
              ps.selectedCardIds = new Set(Object.values(ps.ccByCategory).filter(Boolean));
              renderPlaySetupModal();
            };
            grid.appendChild(btn);
          }
          if (list.length === 0) {
            const noMatch = document.createElement("div");
            noMatch.className = "cards-help";
            noMatch.textContent = "No matching options in this category.";
            grid.appendChild(noMatch);
          }
        };

        searchInp.oninput = () => {
          ps.ccSearch = searchInp.value;
          renderGrid();
        };
        renderGrid();
        els.playSetupBody.appendChild(grid);
      } else if (step.kind === "placeholders") {
        for (const key of step.keys) {
          const field = document.createElement("div");
          field.className = "form-field";
          const label = document.createElement("label");
          label.className = "field-label";
          label.textContent = key;
          const inp = document.createElement("input");
          inp.type = "text";
          inp.value = ps.answers[key] || "";
          inp.placeholder = key;
          inp.oninput = () => {
            ps.answers[key] = inp.value;
          };
          field.append(label, inp);
          els.playSetupBody.appendChild(field);
        }
      }
      return;
    }

    // Non-Character-Creator scenarios ("story" and "multiple_choice"): no Quickstart or CC wizard
    const hasMcBack = sc.scenario_type === "multiple_choice" && (ps.choicePath || []).length > 0;
    els.btnBackPlaySetup.classList.toggle("hidden", !hasMcBack);
    els.btnNextPlaySetup.classList.add("hidden");

    if (sc.scenario_type === "multiple_choice") {
      const chain = mcState?.chain || [];
      const currentOptions = mcState?.currentOptions || [];
      const canStartLeaf = Boolean(activeChoice);
      els.btnConfirmPlaySetup.classList.toggle("hidden", !canStartLeaf);
      els.playSetupSubtitle.textContent = canStartLeaf
        ? "Choose an option (or fill placeholders) to start your adventure."
        : "Select a branch to continue.";

      if (chain.length > 0) {
        const crumb = document.createElement("div");
        crumb.className = "choice-breadcrumb";
        crumb.textContent = [sc.name, ...chain.map((c) => c.label || "Option")].join(" › ");
        els.playSetupBody.appendChild(crumb);
      }

      const lbl = document.createElement("label");
      lbl.className = "field-label";
      lbl.textContent =
        chain.length > 0 ? chain[chain.length - 1].label || "Choose Sub-Option" : "Choose Path";
      els.playSetupBody.appendChild(lbl);

      const list = document.createElement("div");
      list.className = "choice-pick-list";
      for (const ch of currentOptions) {
        const hasKids = Array.isArray(ch.choices) && ch.choices.length > 0;
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className =
          "choice-pick-btn" + (!hasKids && ps.choiceId === ch.id ? " selected" : "");
        const headRow = document.createElement("div");
        headRow.className = "choice-pick-head";
        const title = document.createElement("strong");
        title.textContent = ch.label || "Option";
        headRow.appendChild(title);
        if (hasKids) {
          const arrow = document.createElement("span");
          arrow.className = "choice-branch-pill";
          arrow.textContent = `${ch.choices.length} options ›`;
          headRow.appendChild(arrow);
        }
        const preview = document.createElement("span");
        preview.className = "cc-card-entry";
        preview.textContent = (ch.description || ch.opening || "").slice(0, 140);
        btn.append(headRow, preview);
        btn.onclick = () => {
          if (hasKids) {
            ps.choicePath = [...(ps.choicePath || []), ch.id];
            ps.choiceId = null;
          } else {
            ps.choiceId = ch.id;
          }
          renderPlaySetupModal();
        };
        list.appendChild(btn);
      }
      els.playSetupBody.appendChild(list);
    } else {
      els.btnConfirmPlaySetup.classList.remove("hidden");
      els.playSetupSubtitle.textContent = "Fill in these placeholders before the adventure begins.";
    }

    const placeholderChain = mcState ? mcState.effectiveChain : [];
    const keys = extractScenarioPlaceholderKeys(sc, placeholderChain);
    for (const key of keys) {
      const field = document.createElement("div");
      field.className = "form-field";
      const label = document.createElement("label");
      label.className = "field-label";
      label.textContent = key === "character.name" ? "Enter your character's name..." : key;
      const inp = document.createElement("input");
      inp.type = "text";
      inp.value = ps.answers[key] || "";
      inp.placeholder = label.textContent;
      inp.oninput = () => {
        ps.answers[key] = inp.value;
      };
      field.append(label, inp);
      els.playSetupBody.appendChild(field);
    }

    if (sc.third_person && !sc.character_name && !keys.includes("character.name")) {
      const field = document.createElement("div");
      field.className = "form-field";
      const label = document.createElement("label");
      label.className = "field-label";
      label.textContent = "Third Person Character Name";
      const inp = document.createElement("input");
      inp.type = "text";
      inp.value = ps.answers["character.name"] || "";
      inp.placeholder = "Enter your character's name...";
      inp.oninput = () => {
        ps.answers["character.name"] = inp.value;
      };
      field.append(label, inp);
      els.playSetupBody.appendChild(field);
    }
  }

  async function initiatePlayScenario(sc) {
    const keys = extractScenarioPlaceholderKeys(sc);
    const needsSetup =
      sc.scenario_type === "multiple_choice" ||
      sc.scenario_type === "character_creator" ||
      keys.length > 0 ||
      (sc.third_person && !sc.character_name);

    if (!needsSetup) {
      await startStoryFromScenario(sc.id);
      return;
    }

    const scAttached = sc.attached_scripts || [];
    const preInnerSelf = scAttached.some(
      (x) => (x.script_id === "community-inner-self" || x.script_id === "community-inner-self-ac") && x.enabled !== false
    );
    const preAutoCards = scAttached.some(
      (x) => (x.script_id === "community-auto-cards" || x.script_id === "community-inner-self-ac") && x.enabled !== false
    );

    state.playSetup = {
      scenario: sc,
      choicePath: [],
      choiceId: null,
      selectedCardIds: new Set(),
      answers: {},
      ccPhase: "gate",
      ccStep: 0,
      ccByCategory: {},
      ccSearch: "",
      enableInnerSelf: preInnerSelf,
      enableAutoCards: preAutoCards,
    };
    renderPlaySetupModal();
    els.playSetupModal.classList.remove("hidden");
  }

  async function startStoryFromScenario(
    scenarioId,
    {
      choiceId = null,
      choicePath = null,
      placeholderAnswers = null,
      selectedCardIds = null,
      quickstart = false,
      autoGenerate = false,
      enableInnerSelf = false,
      enableAutoCards = false,
    } = {}
  ) {
    const data = await api("/api/stories", {
      method: "POST",
      body: JSON.stringify({
        scenario_id: scenarioId,
        choice_id: choiceId,
        choice_path: choicePath,
        placeholder_answers: placeholderAnswers,
        selected_card_ids: selectedCardIds,
        quickstart,
        enable_inner_self: Boolean(enableInnerSelf),
        enable_auto_cards: Boolean(enableAutoCards),
      }),
    });
    if (enableInnerSelf || enableAutoCards) {
      await refreshScriptsList();
    }
    state.currentStory = data.story;
    state.editingSegmentId = null;

    populateSettingsPanel();
    renderStoryFeed();
    updateModeUI();
    await refreshStoriesList();
    setActiveView("play");
    closeScenarioModal();
    els.playSetupModal.classList.add("hidden");
    scrollFeedToBottom();
    els.playerInput.focus();

    if (autoGenerate && state.llmReady) {
      await streamGenerate({});
    }
  }

  function getSectionCategoryColor(label) {
    const lower = String(label || "").toLowerCase();
    if (lower.includes("system") || lower.includes("instructions")) return "#7aa2f7";
    if (lower.includes("memory")) return "#66c284";
    if (lower.includes("card")) return "#a992e2";
    if (lower.includes("plot") || lower.includes("summary") || lower.includes("note")) return "#d99b52";
    if (lower.includes("history") || lower.includes("story") || lower.includes("recent")) return "#5bc0be";
    return "#9aa2b1";
  }

  function renderContextBreakdown(data, modeLabel) {
    els.contextSectionsList.innerHTML = "";
    const limit = Math.max(1, Number(data.context_limit || 16384));
    const reserved = Number(data.reserved_response_tokens || 0);
    const sections = data.sections || [];
    const sectionTokens = sections.map((sec) =>
      sec.tokens !== undefined
        ? Number(sec.tokens)
        : Math.ceil((sec.text || "").length / 4)
    );
    const computedTotal = sectionTokens.reduce((a, b) => a + b, 0);
    const totalToks = data.total_tokens !== undefined ? Number(data.total_tokens) : computedTotal;
    els.contextTotalSummary.textContent = `${totalToks.toLocaleString()} / ${limit.toLocaleString()} tokens (${modeLabel})`;

    if (Array.isArray(data.warnings) && data.warnings.length > 0) {
      const warnBox = document.createElement("div");
      warnBox.className = "context-warning-banner";
      const wHead = document.createElement("strong");
      wHead.textContent = "⚠ Context Warning";
      warnBox.appendChild(wHead);
      const wList = document.createElement("ul");
      for (const w of data.warnings) {
        const li = document.createElement("li");
        li.textContent = w;
        wList.appendChild(li);
      }
      warnBox.appendChild(wList);
      els.contextSectionsList.appendChild(warnBox);
    }

    const barWrap = document.createElement("div");
    barWrap.className = "context-usage-card";
    const barTrack = document.createElement("div");
    barTrack.className = "context-usage-bar";
    sections.forEach((sec, idx) => {
      const tok = sectionTokens[idx];
      if (!tok) return;
      const pct = Math.max(0.6, (tok / limit) * 100);
      const segDiv = document.createElement("div");
      segDiv.className = "context-usage-seg";
      segDiv.style.width = `${pct.toFixed(2)}%`;
      segDiv.style.background = getSectionCategoryColor(sec.label);
      segDiv.title = `${sec.label}: ${tok.toLocaleString()} tokens`;
      barTrack.appendChild(segDiv);
    });
    if (reserved > 0) {
      const resSeg = document.createElement("div");
      resSeg.className = "context-usage-seg reserved";
      resSeg.style.width = `${Math.max(0.6, (reserved / limit) * 100).toFixed(2)}%`;
      resSeg.title = `Reserved AI Response: ${reserved.toLocaleString()} tokens`;
      barTrack.appendChild(resSeg);
    }

    const legend = document.createElement("div");
    legend.className = "context-usage-legend";
    sections.forEach((sec, idx) => {
      const item = document.createElement("span");
      item.className = "context-legend-item";
      const dot = document.createElement("i");
      dot.style.background = getSectionCategoryColor(sec.label);
      item.append(dot, document.createTextNode(`${sec.label}: ${sectionTokens[idx].toLocaleString()}`));
      legend.appendChild(item);
    });
    if (reserved > 0) {
      const rItem = document.createElement("span");
      rItem.className = "context-legend-item";
      const rDot = document.createElement("i");
      rDot.className = "reserved";
      rItem.append(rDot, document.createTextNode(`Response Buffer: ${reserved.toLocaleString()}`));
      legend.appendChild(rItem);
    }
    barWrap.append(barTrack, legend);
    els.contextSectionsList.appendChild(barWrap);

    if (data.guide_text) {
      const gCard = document.createElement("div");
      gCard.className = "context-section-card";
      gCard.innerHTML = `<div class="context-section-head"><span class="context-section-title">Guide Steering</span></div><div class="context-section-body"></div>`;
      gCard.querySelector(".context-section-body").textContent = data.guide_text;
      els.contextSectionsList.appendChild(gCard);
    }
    if (data.retry_instructions) {
      const rCard = document.createElement("div");
      rCard.className = "context-section-card";
      rCard.innerHTML = `<div class="context-section-head"><span class="context-section-title">Retry Instructions</span></div><div class="context-section-body"></div>`;
      rCard.querySelector(".context-section-body").textContent = data.retry_instructions;
      els.contextSectionsList.appendChild(rCard);
    }
    if (Array.isArray(data.removed_context) && data.removed_context.length > 0) {
      const remCard = document.createElement("div");
      remCard.className = "context-section-card";
      remCard.innerHTML = `<div class="context-section-head"><span class="context-section-title">Removed Context (Repeated Sentences)</span><span class="context-token-badge">${data.removed_context.length}</span></div>`;
      const remBody = document.createElement("div");
      remBody.className = "context-section-body";
      remBody.textContent = data.removed_context.join("\n");
      remCard.appendChild(remBody);
      els.contextSectionsList.appendChild(remCard);
    }

    for (const sec of data.sections || []) {
      const card = document.createElement("div");
      card.className = "context-section-card";

      const head = document.createElement("div");
      head.className = "context-section-head";

      const title = document.createElement("span");
      title.className = "context-section-title";
      title.textContent = sec.label;

      const badge = document.createElement("span");
      badge.className = "context-token-badge";
      badge.textContent =
        sec.tokens !== undefined
          ? `${sec.tokens.toLocaleString()} tok`
          : `~${Math.ceil((sec.text || "").length / 4).toLocaleString()} tok`;

      head.append(title, badge);
      card.appendChild(head);

      const body = document.createElement("div");
      body.className = "context-section-body";
      body.textContent = sec.text || "(Empty)";
      card.appendChild(body);
      els.contextSectionsList.appendChild(card);
    }

    if ((data.stored_memories || []).length > 0) {
      const memCard = document.createElement("div");
      memCard.className = "context-section-card";
      const mHead = document.createElement("div");
      mHead.className = "context-section-head";
      const mTitle = document.createElement("span");
      mTitle.className = "context-section-title";
      mTitle.textContent = `Memory Bank Explorer (${data.stored_memories.length} memories)`;
      mHead.appendChild(mTitle);
      memCard.appendChild(mHead);

      for (const m of data.stored_memories) {
        const row = document.createElement("div");
        row.className = "context-section-body";
        row.style.borderTop = "1px solid var(--border)";
        row.style.paddingTop = "6px";
        row.textContent = `[${m.used ? "USED" : "STORED"} · score ${m.score ?? 0} · uses ${m.uses ?? 0}] ${m.text}`;
        memCard.appendChild(row);
      }
      els.contextSectionsList.appendChild(memCard);
    }
  }

  async function openContextViewer(view = "next") {
    if (!state.currentStory) return;
    els.contextModal.classList.remove("hidden");
    const lastSnap = state.currentStory.last_generation_context;
    const useLast = view === "last" && Boolean(lastSnap);
    els.btnContextNext.classList.toggle("active", !useLast);
    els.btnContextLast.classList.toggle("active", useLast);
    els.btnContextLast.disabled = !lastSnap;

    if (useLast) {
      renderContextBreakdown(lastSnap, "last generation snapshot");
      return;
    }

    els.contextTotalSummary.textContent = "Inspecting prompt tokens...";
    els.contextSectionsList.innerHTML = "";
    try {
      const data = await api(
        `/api/stories/${encodeURIComponent(state.currentStory.id)}/context`
      );
      const modeLabel = data.exact_tokens ? "exact Gemma tokens" : "estimated tokens";
      renderContextBreakdown(data, modeLabel);
    } catch (err) {
      els.contextTotalSummary.textContent = err.message;
    }
  }

  async function refreshStoriesList() {
    const data = await api("/api/stories");
    state.stories = data.stories || [];
    renderStoriesList();
  }

  async function loadStoryById(id) {
    showError("");
    const data = await api(`/api/stories/${encodeURIComponent(id)}`);
    state.currentStory = data.story;
    state.editingSegmentId = null;
    populateSettingsPanel();
    renderStoryFeed();
    renderStoriesList();
    setActiveView("play");
    scrollFeedToBottom();
  }

  async function deleteStoryById(id) {
    await api(`/api/stories/${encodeURIComponent(id)}`, { method: "DELETE" });
    await refreshStoriesList();
    if (state.currentStory?.id === id) {
      state.currentStory = null;
      els.storyTitle.value = "Select a Scenario";
      setActiveView("home");
      setHomeTab(state.stories.length > 0 ? "adventures" : "scenarios");
    }
  }

  async function saveEditedSegment(segId, newText) {
    const trimmed = newText.trim();
    if (!trimmed) {
      await deleteSegment(segId);
      return;
    }
    const data = await api(
      `/api/stories/${encodeURIComponent(state.currentStory.id)}/segments/${encodeURIComponent(segId)}`,
      {
        method: "PATCH",
        body: JSON.stringify({ text: trimmed }),
      }
    );
    state.currentStory = data.story;
    state.editingSegmentId = null;
    renderStoryFeed();
    refreshStoriesList();
  }

  async function deleteSegment(segId) {
    const data = await api(
      `/api/stories/${encodeURIComponent(state.currentStory.id)}/segments/${encodeURIComponent(segId)}`,
      { method: "DELETE" }
    );
    state.currentStory = data.story;
    state.editingSegmentId = null;
    renderStoryFeed();
    refreshStoriesList();
  }

  async function appendOnly() {
    const text = els.playerInput.value.trim();
    if (!text || !state.currentStory || state.isGenerating) return;
    showError("");
    try {
      const data = await api(
        `/api/stories/${encodeURIComponent(state.currentStory.id)}/append`,
        {
          method: "POST",
          body: JSON.stringify({ mode: state.mode, text }),
        }
      );
      state.currentStory = data.story;
      els.playerInput.value = "";
      updateModeUI();
      populateSettingsPanel();
      renderStoryFeed();
      scrollFeedToBottom();
      refreshStoriesList();
    } catch (err) {
      showError(err.message);
    }
  }

  async function streamGenerate({ mode = null, text = "", retry = false, retryInstructions = "" } = {}) {
    if (!state.currentStory || state.isGenerating) return;
    showError("");
    if (state.currentStory.script_state?.message) {
      state.currentStory.dismissed_script_message = String(
        state.currentStory.script_state.message
      );
      renderScriptMessageBanner();
    }

    state.isGenerating = true;
    state.abortController = new AbortController();
    updateControlsState();

    let reasoningDetails = null;
    let reasoningPre = null;
    let streamProseRun = null;
    let streamPrevSeg = null;
    let sepNode = null;
    let sepApplied = false;
    let isContinuingInline = false;

    const streamEl = document.createElement("span");
    streamEl.className = "segment segment-inline kind-ai";
    const contentSpan = document.createElement("span");
    contentSpan.className = "segment-text streaming-cursor stream-continuation";
    streamEl.appendChild(contentSpan);

    let streamAttached = false;
    const ensureStreamAttached = () => {
      if (!streamAttached) {
        const empty = els.storyFeed.querySelector(".empty-state");
        if (empty) empty.remove();
        const segsNow = state.currentStory?.segments || [];
        const prevSegNow = segsNow[segsNow.length - 1];
        const lastProseRun = els.storyFeed.lastElementChild;
        if (prevSegNow && lastProseRun && lastProseRun.classList.contains("prose-run")) {
          streamProseRun = lastProseRun;
          streamPrevSeg = prevSegNow;
          isContinuingInline = true;
          sepNode = document.createTextNode("");
          streamProseRun.append(sepNode, streamEl);
        } else {
          streamProseRun = document.createElement("div");
          streamProseRun.className = "prose-run";
          streamProseRun.appendChild(streamEl);
          els.storyFeed.appendChild(streamProseRun);
        }
        streamAttached = true;
      }
    };

    let userScrolledAway = false;
    let lastAutoScrollTop = els.storyFeed.scrollTop;
    const onFeedScroll = () => {
      if (Math.abs(els.storyFeed.scrollTop - lastAutoScrollTop) > 4) {
        userScrolledAway = true;
      }
    };
    els.storyFeed.addEventListener("scroll", onFeedScroll, { passive: true });

    const scrollStreamingFeed = (anchorEl) => {
      if (userScrolledAway || state.currentStory?.settings?.follow_latest_text === false) return;
      els.storyFeed.scrollTop = getStreamingScrollTop(anchorEl);
      lastAutoScrollTop = els.storyFeed.scrollTop;
    };

    try {
      const resp = await fetch(
        `/api/stories/${encodeURIComponent(state.currentStory.id)}/generate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode, text, retry, retry_instructions: retryInstructions }),
          signal: state.abortController.signal,
        }
      );

      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.error || `Generation failed (${resp.status})`);
      }

      if (mode && text.trim()) {
        els.playerInput.value = "";
        updateModeUI();
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let currentEvent = "message";

      const handleEvent = (eventName, payloadStr) => {
        if (!payloadStr) return;
        let data;
        try {
          data = JSON.parse(payloadStr);
        } catch {
          return;
        }

        if (eventName === "user_segment" && data.segment) {
          state.currentStory.segments.push(data.segment);
          renderStoryFeed();
          ensureStreamAttached();
          scrollStreamingFeed(contentSpan);
        } else if (eventName === "story_sync" && data.story) {
          state.currentStory = data.story;
          renderStoryFeed();
          ensureStreamAttached();
          scrollStreamingFeed(contentSpan);
        } else if (eventName === "reasoning" && data.token) {
          ensureStreamAttached();
          if (!reasoningDetails) {
            reasoningDetails = document.createElement("details");
            reasoningDetails.className = "reasoning-box";
            const summary = document.createElement("summary");
            summary.textContent = "GM Thinking...";
            reasoningPre = document.createElement("div");
            reasoningPre.style.whiteSpace = "pre-wrap";
            reasoningPre.style.marginTop = "6px";
            reasoningDetails.append(summary, reasoningPre);
            if (streamProseRun && streamProseRun.parentNode) {
              streamProseRun.parentNode.insertBefore(reasoningDetails, streamProseRun);
            } else {
              streamEl.insertBefore(reasoningDetails, contentSpan);
            }
          }
          reasoningPre.textContent += data.token;
          scrollStreamingFeed(contentSpan);
        } else if (eventName === "token" && data.token) {
          ensureStreamAttached();
          if (isContinuingInline && !sepApplied && data.token.trim()) {
            sepNode.textContent = segmentJoinSeparator(streamPrevSeg, {
              kind: "ai",
              text: data.token,
            });
            contentSpan.textContent += data.token.trimStart();
            sepApplied = true;
          } else if (isContinuingInline && !sepApplied) {
            // Skip leading whitespace tokens before separator is decided.
          } else {
            contentSpan.textContent += data.token;
          }
          scrollStreamingFeed(contentSpan);
        } else if (eventName === "error") {
          showError(data.message || "LLM generation error");
        } else if (eventName === "done" && data.story) {
          state.currentStory = data.story;
          populateSettingsPanel();
        }
      };

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let newlineIdx;
        while ((newlineIdx = buffer.indexOf("\n")) !== -1) {
          const line = buffer.slice(0, newlineIdx).replace(/\r$/, "");
          buffer = buffer.slice(newlineIdx + 1);

          if (line === "") {
            currentEvent = "message";
          } else if (line.startsWith("event:")) {
            currentEvent = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            handleEvent(currentEvent, line.slice(5).trim());
          }
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") {
        showError(err.message);
      }
      // Reload latest persisted state (includes partial tokens if aborted mid-stream)
      if (state.currentStory) {
        try {
          const fresh = await api(`/api/stories/${encodeURIComponent(state.currentStory.id)}`);
          state.currentStory = fresh.story;
        } catch {
          // ignore
        }
      }
    } finally {
      els.storyFeed.removeEventListener("scroll", onFeedScroll);
      state.isGenerating = false;
      state.abortController = null;
      renderScriptMessageBanner();
      renderStoryFeed();
      if (isContinuingInline) {
        if (!userScrolledAway && state.currentStory?.settings?.follow_latest_text !== false) {
          const maxFeedScroll = Math.max(
            0,
            els.storyFeed.scrollHeight - els.storyFeed.clientHeight
          );
          els.storyFeed.scrollTop = Math.min(maxFeedScroll, lastAutoScrollTop);
        }
      } else {
        const segs = state.currentStory?.segments || [];
        const lastSeg = segs[segs.length - 1];
        if (lastSeg?.kind === "ai") {
          scrollStreamingFeed(els.storyFeed.lastElementChild);
        } else if (!userScrolledAway) {
          scrollFeedToBottom();
        }
      }
      refreshStoriesList();
    }
  }

  async function handleSend() {
    if (state.isGenerating) {
      state.abortController?.abort();
      return;
    }
    const text = els.playerInput.value.trim();
    if (!text) {
      await streamGenerate({});
      return;
    }
    await streamGenerate({ mode: state.mode, text });
  }

  let epClearKeyFlag = false;

  const REASONING_EFFORTS = [
    {
      key: "off",
      desc: "No reasoning tokens; fastest response and natural prose",
    },
    {
      key: "low",
      desc: "Light reasoning for quick consistency checks",
    },
    {
      key: "medium",
      desc: "Balanced speed and reasoning quality for most tasks",
    },
    {
      key: "high",
      desc: "Deeper reasoning for complex scenes and strict rules",
    },
    {
      key: "xhigh",
      desc: "Maximum reasoning depth; slower turns",
    },
  ];

  function normalizeReasoningEffort(effort, enableThinking = false) {
    if (typeof effort === "string") {
      const norm = effort.trim().toLowerCase();
      if (REASONING_EFFORTS.some((e) => e.key === norm)) return norm;
    }
    return enableThinking ? "medium" : "off";
  }

  function syncReasoningEffortUI(effortKey) {
    const idx = Math.max(
      0,
      REASONING_EFFORTS.findIndex((e) => e.key === effortKey)
    );
    const item = REASONING_EFFORTS[idx];
    if (els.settingThinking) {
      els.settingThinking.checked = idx > 0;
    }
    if (els.settingReasoningEffort) {
      els.settingReasoningEffort.value = String(idx);
    }
    if (els.settingEffortBadge) {
      els.settingEffortBadge.textContent = item.key;
    }
    if (els.settingEffortFill) {
      const pct = (idx / (REASONING_EFFORTS.length - 1)) * 100;
      els.settingEffortFill.style.width = `${pct}%`;
    }
    if (els.settingEffortDesc) {
      els.settingEffortDesc.textContent = item.desc;
    }
    els.effortStops.forEach((btn, i) => {
      btn.classList.toggle("active", i === idx);
      btn.classList.toggle("passed", i < idx);
    });
  }

  function renderThinkingControlVisibility() {
    const mode = state.llmThinkingMode || "none";
    if (els.settingThinkingToggleRow) {
      els.settingThinkingToggleRow.classList.toggle("hidden", mode !== "toggle");
    }
    if (els.settingEffortControl) {
      els.settingEffortControl.classList.toggle("hidden", mode !== "effort");
    }
  }

  const DEFAULT_MAX_CONTEXT_LENGTH = 131072;

  function getContextMaxLimit() {
    if (
      typeof state.llmMaxContext === "number" &&
      Number.isFinite(state.llmMaxContext) &&
      state.llmMaxContext >= 1024
    ) {
      return Math.floor(state.llmMaxContext);
    }
    return DEFAULT_MAX_CONTEXT_LENGTH;
  }

  function clampContextLength(rawVal) {
    const maxCtx = getContextMaxLimit();
    const parsed = Number(rawVal);
    const val = Number.isFinite(parsed) && parsed > 0 ? Math.round(parsed) : 16384;
    return Math.max(1024, Math.min(maxCtx, val));
  }

  function syncContextLengthControls(rawVal = null) {
    const maxCtx = getContextMaxLimit();
    const sliderStep = maxCtx >= 262144 ? 4096 : maxCtx >= 65536 ? 1024 : 512;
    if (els.settingContextLengthSlider) {
      els.settingContextLengthSlider.max = String(maxCtx);
      els.settingContextLengthSlider.step = String(sliderStep);
    }
    if (els.settingContextLength) {
      els.settingContextLength.max = String(maxCtx);
    }
    if (els.settingContextMaxLabel) {
      const sourceTag = state.llmMaxContextSource ? ` (${state.llmMaxContextSource})` : "";
      els.settingContextMaxLabel.textContent = state.llmMaxContext
        ? `Max: ${maxCtx.toLocaleString()}${sourceTag}`
        : `Max: ${maxCtx.toLocaleString()}`;
    }
    const baseVal =
      rawVal !== null
        ? rawVal
        : els.settingContextLength?.value ||
          state.currentStory?.settings?.context_length ||
          16384;
    const clamped = clampContextLength(baseVal);
    if (els.settingContextLengthSlider) {
      els.settingContextLengthSlider.value = String(clamped);
    }
    if (els.settingContextLength && document.activeElement !== els.settingContextLength) {
      els.settingContextLength.value = String(clamped);
    }
    return clamped;
  }

  function applyLlmStatusUI(info) {
    const statusTargets = [els.llmPill, els.btnEndpoint];
    statusTargets.forEach((el) => el.classList.remove("ready", "loading", "offline"));
    state.llmReady = info.state === "ready";
    const reportedMaxCtx =
      typeof info.max_context === "number" && info.max_context >= 1024
        ? Math.floor(info.max_context)
        : null;
    const reportedSource = info.max_context_source || null;
    const maxCtxChanged =
      state.llmMaxContext !== reportedMaxCtx ||
      state.llmMaxContextSource !== reportedSource;
    state.llmMaxContext = reportedMaxCtx;
    state.llmMaxContextSource = reportedSource;
    const reportedThinkingMode = ["toggle", "effort", "none"].includes(info.thinking_mode)
      ? info.thinking_mode
      : "none";
    if (state.llmThinkingMode !== reportedThinkingMode) {
      state.llmThinkingMode = reportedThinkingMode;
      renderThinkingControlVisibility();
    }
    let statusClass = "offline";
    let statusTitle = info.detail ? `LLM Offline (${info.detail})` : "LLM Offline";
    if (info.state === "ready") {
      statusClass = "ready";
      statusTitle = info.model ? `LLM Ready (${info.model})` : "LLM Ready";
      els.btnStartLlm.classList.add("hidden");
    } else if (info.state === "loading") {
      statusClass = "loading";
      statusTitle = "Loading LLM...";
      els.btnStartLlm.classList.add("hidden");
    } else {
      els.btnStartLlm.classList.remove("hidden");
    }
    statusTargets.forEach((el) => {
      el.classList.add(statusClass);
      el.title = statusTitle;
    });
    const shortModel = info.model ? String(info.model).split("/").pop() : "Model";
    els.endpointBtnLabel.textContent =
      shortModel.length > 22 ? shortModel.slice(0, 20) + "…" : shortModel;
    if (maxCtxChanged) {
      const targetVal =
        state.currentStory?.settings?.context_length ??
        (els.settingContextLength?.value ? Number(els.settingContextLength.value) : 16384);
      syncContextLengthControls(targetVal);
    }
  }

  function populateEndpointModels(models = []) {
    const list = Array.isArray(models) ? models.filter(Boolean) : [];
    els.epModelsDatalist.innerHTML = "";
    els.epModelSelect.innerHTML = "";
    for (const m of list) {
      const opt = document.createElement("option");
      opt.value = m;
      els.epModelsDatalist.appendChild(opt);
    }
    if (list.length === 1) {
      els.epModelInput.value = list[0];
      els.epModelSelect.classList.add("hidden");
    } else if (list.length > 1) {
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = `Choose from ${list.length} offered models...`;
      els.epModelSelect.appendChild(placeholder);
      for (const m of list) {
        const opt = document.createElement("option");
        opt.value = m;
        opt.textContent = m;
        if (els.epModelInput.value === m) opt.selected = true;
        els.epModelSelect.appendChild(opt);
      }
      els.epModelSelect.classList.remove("hidden");
    } else {
      els.epModelSelect.classList.add("hidden");
    }
  }

  function showEndpointMsg(msg, isOk = false) {
    if (!msg) {
      els.epStatusMsg.classList.add("hidden");
      els.epStatusMsg.textContent = "";
      els.epStatusMsg.classList.remove("ep-status-ok");
      return;
    }
    els.epStatusMsg.textContent = msg;
    els.epStatusMsg.classList.toggle("ep-status-ok", Boolean(isOk));
    els.epStatusMsg.classList.remove("hidden");
  }

  async function openEndpointModal() {
    epClearKeyFlag = false;
    showEndpointMsg("");
    els.endpointModal.classList.remove("hidden");
    try {
      const [cfgRes, statusRes] = await Promise.all([
        api("/api/llm/config"),
        api("/api/llm/status"),
      ]);
      const cfg = cfgRes.config || {};
      els.epUrlInput.value = cfg.llm_url || "http://127.0.0.1:8080";
      els.epKeyInput.value = "";
      els.epKeyInput.placeholder = cfg.has_api_key
        ? `Saved (${cfg.api_key_preview}) — type to replace`
        : "Optional (leave blank for local servers)";
      els.btnEpClearKey.classList.toggle("hidden", !cfg.has_api_key);
      els.epModelInput.value = cfg.model || "";
      populateEndpointModels(statusRes.available_models || []);
      applyLlmStatusUI(statusRes);
    } catch (err) {
      showEndpointMsg(err.message);
    }
  }

  async function pollLlmStatus() {
    try {
      const info = await api("/api/llm/status");
      applyLlmStatusUI(info);
    } catch {
      [els.llmPill, els.btnEndpoint].forEach((el) => {
        el.classList.remove("ready", "loading");
        el.classList.add("offline");
        el.title = "Server Offline";
      });
    }
  }

  function wireEvents() {
    let composerTapHadInputFocus = false;
    const isComposerTextInput = (el) => el === els.playerInput || el === els.retryChangesInput;
    const restoreComposerFocus = () => {
      if (composerTapHadInputFocus && !isComposerTextInput(document.activeElement)) {
        els.playerInput.focus({ preventScroll: true });
      }
      composerTapHadInputFocus = false;
    };

    if (els.composer) {
      els.composer.addEventListener("pointerdown", (e) => {
        if (isComposerTextInput(e.target)) return;
        composerTapHadInputFocus = document.activeElement === els.playerInput;
      });

      // Keep the active textarea focused when tapping anywhere on the composer bar
      // (mode switcher, quick actions, send buttons, or bar gaps) so mobile keyboards stay open.
      els.composer.addEventListener("mousedown", (e) => {
        if (isComposerTextInput(e.target)) return;
        if (document.activeElement === els.playerInput) {
          composerTapHadInputFocus = true;
        }
        e.preventDefault();
      });

      els.composer.addEventListener("click", restoreComposerFocus);
    }

    els.btnModeCollapse.addEventListener("click", (e) => {
      e.stopPropagation();
      setModeExpanded(false);
      restoreComposerFocus();
    });

    els.modeBtns.forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (!els.modeSwitcher.classList.contains("expanded")) {
          setModeExpanded(true);
          restoreComposerFocus();
          return;
        }
        composerTapHadInputFocus = false;
        setMode(btn.dataset.mode);
      });
    });

    document.addEventListener("click", (e) => {
      if (els.modeSwitcher.classList.contains("expanded") && !els.modeSwitcher.contains(e.target)) {
        setModeExpanded(false);
      }
      if (state.activeToolbarSegmentId && !e.target.closest(".segment") && !e.target.closest("#segment-action-bar")) {
        state.activeToolbarSegmentId = null;
        els.storyFeed.querySelectorAll(".segment.toolbar-open").forEach((node) => {
          node.classList.remove("toolbar-open");
        });
        renderSegmentActionBar();
      }
    });

    els.playerInput.addEventListener("input", () => {
      updateModeUI();
      els.playerInput.style.height = "auto";
      els.playerInput.style.height = Math.min(180, Math.max(56, els.playerInput.scrollHeight)) + "px";
    });

    els.playerInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    });

    document.addEventListener("keydown", (e) => {
      if (e.altKey && e.key === "1") {
        e.preventDefault();
        setMode("do");
      } else if (e.altKey && e.key === "2") {
        e.preventDefault();
        setMode("say");
      } else if (e.altKey && e.key === "3") {
        e.preventDefault();
        setMode("story");
      } else if (e.altKey && e.key === "4") {
        e.preventDefault();
        setMode("guide");
      }
    });

    els.btnSend.addEventListener("click", handleSend);
    els.btnAddOnly.addEventListener("click", appendOnly);
    els.btnContinue.addEventListener("click", () => streamGenerate({}));
    els.btnErase.addEventListener("click", async () => {
      if (!state.currentStory || state.isGenerating) return;
      const data = await api(
        `/api/stories/${encodeURIComponent(state.currentStory.id)}/erase`,
        { method: "POST", body: "{}" }
      );
      state.currentStory = data.story;
      renderStoryFeed();
      refreshStoriesList();
    });
    els.btnRetry.addEventListener("click", () => streamGenerate({ retry: true }));
    els.btnRetryChanges.addEventListener("click", () => {
      els.retryChangesBar.classList.toggle("hidden");
      if (!els.retryChangesBar.classList.contains("hidden")) {
        els.retryChangesInput.focus();
      }
    });
    els.btnCancelRetryChanges.addEventListener("click", () => {
      const hadRetryFocus = document.activeElement === els.retryChangesInput;
      els.retryChangesBar.classList.add("hidden");
      if (hadRetryFocus) {
        els.playerInput.focus({ preventScroll: true });
      }
    });
    const submitRetryChanges = async () => {
      const inst = els.retryChangesInput.value.trim();
      els.retryChangesBar.classList.add("hidden");
      els.retryChangesInput.value = "";
      await streamGenerate({ retry: true, retryInstructions: inst });
    };
    els.btnSubmitRetryChanges.addEventListener("click", submitRetryChanges);
    els.retryChangesInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        submitRetryChanges();
      }
    });

    els.btnContextNext.addEventListener("click", () => openContextViewer("next"));
    els.btnContextLast.addEventListener("click", () => openContextViewer("last"));

    els.btnUndo.addEventListener("click", async () => {
      if (!state.currentStory || state.isGenerating) return;
      const data = await api(
        `/api/stories/${encodeURIComponent(state.currentStory.id)}/undo`,
        { method: "POST", body: "{}" }
      );
      state.currentStory = data.story;
      renderStoryFeed();
      refreshStoriesList();
    });

    els.btnRedo.addEventListener("click", async () => {
      if (!state.currentStory || state.isGenerating) return;
      const data = await api(
        `/api/stories/${encodeURIComponent(state.currentStory.id)}/redo`,
        { method: "POST", body: "{}" }
      );
      state.currentStory = data.story;
      renderStoryFeed();
      refreshStoriesList();
    });

    els.storyTitle.addEventListener("change", async () => {
      if (!state.currentStory) return;
      const data = await api(
        `/api/stories/${encodeURIComponent(state.currentStory.id)}`,
        {
          method: "PATCH",
          body: JSON.stringify({ title: els.storyTitle.value }),
        }
      );
      state.currentStory = data.story;
      refreshStoriesList();
    });

    els.btnHome.addEventListener("click", () => {
      setActiveView("home");
    });
    els.homeTabs.forEach((tab) => {
      tab.addEventListener("click", () => setHomeTab(tab.dataset.homeTab));
    });
    els.btnHomeCreateScenario.addEventListener("click", () => {
      resetScenarioForm();
      openScenarioModal();
    });
    els.btnHomeImportScenario.addEventListener("click", () => {
      els.importError.classList.add("hidden");
      els.importUrlInput.value = "";
      els.importJsonInput.value = "";
      els.importFileInput.value = "";
      els.importModal.classList.remove("hidden");
    });

    els.btnCloseScenarios.addEventListener("click", closeScenarioModal);
    els.scenarioModal.addEventListener("click", (e) => {
      if (e.target === els.scenarioModal) closeScenarioModal();
    });

    els.btnCancelEditScenario.addEventListener("click", resetScenarioForm);
    els.btnSaveScenario.addEventListener("click", async () => {
      try {
        await saveScenarioForm();
      } catch (err) {
        showScenarioError(err.message);
      }
    });
    els.btnSavePlayScenario.addEventListener("click", async () => {
      try {
        const sc = await saveScenarioForm();
        if (sc) {
          await initiatePlayScenario(sc);
        }
      } catch (err) {
        showScenarioError(err.message);
      }
    });

    els.scenarioTypeSelect.addEventListener("change", updateScenarioTypeUI);
    els.btnAddScenarioChoice.addEventListener("click", () => {
      state.editingScenarioChoices.push(makeBlankChoice());
      renderScenarioChoicesList();
    });
    els.btnAddScenarioCard.addEventListener("click", () => {
      state.editingScenarioCards.push({
        id: Math.random().toString(16).slice(2, 10),
        title: "",
        card_type: "Custom",
        keys: "",
        entry: "",
      });
      renderScenarioCardsList();
    });

    els.storyCardsSearch.addEventListener("input", renderStoryCardsList);
    els.storyCardsTypeFilter.addEventListener("change", renderStoryCardsList);

    els.btnClosePlaySetup.addEventListener("click", () => els.playSetupModal.classList.add("hidden"));
    els.btnSetupInnerSelf?.addEventListener("click", () => {
      if (!state.playSetup) return;
      state.playSetup.enableInnerSelf = !state.playSetup.enableInnerSelf;
      syncPlaySetupScriptPills(state.playSetup);
    });
    els.btnSetupAutoCards?.addEventListener("click", () => {
      if (!state.playSetup) return;
      state.playSetup.enableAutoCards = !state.playSetup.enableAutoCards;
      syncPlaySetupScriptPills(state.playSetup);
    });
    els.btnCancelPlaySetup.addEventListener("click", () => els.playSetupModal.classList.add("hidden"));
    els.btnBackPlaySetup.addEventListener("click", () => {
      const ps = state.playSetup;
      if (!ps) return;
      if (ps.scenario?.scenario_type === "multiple_choice") {
        if ((ps.choicePath || []).length > 0) {
          ps.choicePath.pop();
          ps.choiceId = null;
          renderPlaySetupModal();
        }
        return;
      }
      if (ps.ccStep > 0) {
        ps.ccStep -= 1;
      } else {
        ps.ccPhase = "gate";
      }
      ps.ccSearch = "";
      renderPlaySetupModal();
    });
    els.btnNextPlaySetup.addEventListener("click", () => {
      const ps = state.playSetup;
      if (!ps) return;
      ps.ccStep = (ps.ccStep || 0) + 1;
      ps.ccSearch = "";
      renderPlaySetupModal();
    });
    els.btnConfirmPlaySetup.addEventListener("click", async () => {
      const ps = state.playSetup;
      if (!ps) return;
      const sc = ps.scenario;
      const fullPath =
        sc.scenario_type === "multiple_choice"
          ? [...(ps.choicePath || []), ...(ps.choiceId ? [ps.choiceId] : [])]
          : null;
      const origLabel = els.btnConfirmPlaySetup.textContent;
      els.btnConfirmPlaySetup.disabled = true;
      if (ps.enableInnerSelf || ps.enableAutoCards) {
        els.btnConfirmPlaySetup.textContent = "Preparing Scripts...";
      }
      try {
        await startStoryFromScenario(sc.id, {
          choiceId: ps.choiceId,
          choicePath: fullPath,
          placeholderAnswers: ps.answers,
          selectedCardIds: Array.from(ps.selectedCardIds),
          autoGenerate: sc.scenario_type === "character_creator",
          enableInnerSelf: Boolean(ps.enableInnerSelf),
          enableAutoCards: Boolean(ps.enableAutoCards),
        });
      } catch (err) {
        showError(err.message);
      } finally {
        els.btnConfirmPlaySetup.disabled = false;
        els.btnConfirmPlaySetup.textContent = origLabel;
      }
    });

    els.btnSettings.addEventListener("click", () => {
      els.drawerSettings.classList.toggle("hidden");
    });
    els.btnCloseSettings.addEventListener("click", () => {
      els.drawerSettings.classList.add("hidden");
    });

    els.settingsMainTabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const target = tab.dataset.settingsTab;
        els.settingsMainTabs.forEach((t) => t.classList.toggle("active", t === tab));
        els.settingsPaneAdventure.classList.toggle("hidden", target !== "adventure");
        els.settingsPaneAi.classList.toggle("hidden", target !== "ai");
      });
    });

    els.drawerTabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const target = tab.dataset.drawerTab;
        els.drawerTabs.forEach((t) => t.classList.toggle("active", t === tab));
        els.tabPanePlot.classList.toggle("hidden", target !== "plot");
        els.tabPaneCards.classList.toggle("hidden", target !== "cards");
        els.tabPaneScripts.classList.toggle("hidden", target !== "scripts");
        els.tabPaneDetails.classList.toggle("hidden", target !== "details");
      });
    });

    els.btnExportCards.addEventListener("click", async () => {
      if (!state.currentStory) return;
      const data = await api(`/api/stories/${encodeURIComponent(state.currentStory.id)}/cards/export`);
      const blob = new Blob([JSON.stringify(data.cards, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${(state.currentStory.title || "story_cards").replace(/[^a-z0-9_-]/gi, "_")}_cards.json`;
      a.click();
      URL.revokeObjectURL(url);
    });

    els.btnImportCards.addEventListener("click", () => {
      if (!state.currentStory) return;
      els.importCardsFileInput.value = "";
      els.importCardsFileInput.click();
    });

    els.importCardsFileInput.addEventListener("change", async (e) => {
      const file = e.target.files?.[0];
      if (!file || !state.currentStory) return;
      try {
        const parsed = JSON.parse(await file.text());
        if (!Array.isArray(parsed)) {
          showError("Story Cards import expects a JSON array.");
          return;
        }
        const res = await api(
          `/api/stories/${encodeURIComponent(state.currentStory.id)}/cards/import`,
          { method: "POST", body: JSON.stringify({ cards: parsed }) }
        );
        state.currentStory = res.story;
        renderStoryCardsList();
      } catch (err) {
        showError(`Could not import Story Cards: ${err.message}`);
      }
    });

    els.btnDownloadAdventure.addEventListener("click", () => {
      if (!state.currentStory) return;
      window.location.href = `/api/stories/${encodeURIComponent(state.currentStory.id)}/export`;
    });

    els.storyBuiltinEnabled.addEventListener("change", () => {
      if (!state.currentStory) return;
      if (!state.currentStory.builtin_script) state.currentStory.builtin_script = {};
      state.currentStory.builtin_script.enabled = els.storyBuiltinEnabled.checked;
    });
    els.btnEditStoryBuiltinScript.addEventListener("click", () => openScriptEditor("story_builtin"));
    els.btnEditScenarioScript.addEventListener("click", () => openScriptEditor("scenario_builtin"));
    els.btnNewReusableScript.addEventListener("click", () => openScriptEditor("new_reusable"));

    const installCommunityScriptForStory = async (btn, kind, labelText) => {
      if (!state.currentStory) return;
      btn.disabled = true;
      btn.textContent = "Installing...";
      try {
        const res = await api("/api/scripts/install-community", {
          method: "POST",
          body: JSON.stringify({ kind }),
        });
        await refreshScriptsList();
        const sid = res.script?.id;
        if (sid) {
          if (!Array.isArray(state.currentStory.attached_scripts)) {
            state.currentStory.attached_scripts = [];
          }
          if (!state.currentStory.attached_scripts.some((x) => x.script_id === sid)) {
            state.currentStory.attached_scripts.push({ script_id: sid, enabled: true });
          }
          renderStoryScriptsPanel();
        }
      } catch (err) {
        showError(err.message);
      } finally {
        btn.disabled = false;
        btn.textContent = labelText;
      }
    };
    els.btnInstallInnerSelf.addEventListener("click", () =>
      installCommunityScriptForStory(els.btnInstallInnerSelf, "inner_self", "+ Inner Self (🎭)")
    );
    els.btnInstallAutoCards.addEventListener("click", () =>
      installCommunityScriptForStory(els.btnInstallAutoCards, "auto_cards", "+ Auto-Cards")
    );

    els.btnAttachStoryScript.addEventListener("click", () => {
      if (!state.currentStory) return;
      const scriptId = els.storyAttachScriptSelect.value;
      if (!scriptId) return;
      if (!Array.isArray(state.currentStory.attached_scripts)) state.currentStory.attached_scripts = [];
      if (state.currentStory.attached_scripts.length >= 10) return;
      state.currentStory.attached_scripts.push({ script_id: scriptId, enabled: true });
      renderStoryScriptsPanel();
    });

    els.btnAttachScenarioScript.addEventListener("click", () => {
      const scriptId = els.scenarioAttachScriptSelect.value;
      if (!scriptId) return;
      if (state.editingScenarioAttachedScripts.length >= 10) return;
      state.editingScenarioAttachedScripts.push({ script_id: scriptId, enabled: true });
      renderScenarioScriptsPanel();
    });

    els.btnClearStoryLogs.addEventListener("click", async () => {
      if (!state.currentStory) return;
      const data = await api(`/api/stories/${encodeURIComponent(state.currentStory.id)}`, {
        method: "PATCH",
        body: JSON.stringify({ clear_logs: true }),
      });
      state.currentStory = data.story;
      renderStoryScriptsPanel();
    });

    els.scriptHookTabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        if (!state.scriptEditor) return;
        state.scriptEditor.draft[state.scriptEditor.hook] = els.scriptCodeEditor.value;
        const nextHook = tab.dataset.hookTab;
        state.scriptEditor.hook = nextHook;
        els.scriptHookTabs.forEach((t) => t.classList.toggle("active", t === tab));
        els.scriptCodeEditor.value = state.scriptEditor.draft[nextHook] || "";
      });
    });

    els.btnCloseScriptEditor.addEventListener("click", () => els.scriptEditorModal.classList.add("hidden"));
    els.btnCancelScriptEditor.addEventListener("click", () => els.scriptEditorModal.classList.add("hidden"));

    els.btnRunScriptTest.addEventListener("click", async () => {
      if (!state.scriptEditor) return;
      state.scriptEditor.draft[state.scriptEditor.hook] = els.scriptCodeEditor.value;
      const hook = els.scriptTestHook.value;
      const res = await api("/api/scripts/test", {
        method: "POST",
        body: JSON.stringify({
          hook,
          code: state.scriptEditor.draft[hook] || "",
          library: state.scriptEditor.draft.library || "",
          text: els.scriptTestInput.value,
          state: state.currentStory?.script_state || {},
          story_cards: state.currentStory?.story_cards || [],
          quests: state.currentStory?.quests || [],
        }),
      });
      els.scriptTestOutput.textContent = JSON.stringify(res, null, 2);
      els.scriptTestOutput.classList.remove("hidden");
    });

    els.btnSaveScriptEditor.addEventListener("click", async () => {
      const se = state.scriptEditor;
      if (!se) return;
      se.draft[se.hook] = els.scriptCodeEditor.value;
      if (se.target === "scenario_builtin") {
        state.editingScenarioBuiltinScript = { ...se.draft };
        renderScenarioScriptsPanel();
        els.scriptEditorModal.classList.add("hidden");
        return;
      }
      if (se.target === "story_builtin" && state.currentStory) {
        state.currentStory.builtin_script = { ...se.draft };
        const data = await api(`/api/stories/${encodeURIComponent(state.currentStory.id)}`, {
          method: "PATCH",
          body: JSON.stringify({ builtin_script: state.currentStory.builtin_script }),
        });
        state.currentStory = data.story;
        renderStoryScriptsPanel();
        els.scriptEditorModal.classList.add("hidden");
        return;
      }
      const payload = {
        name: els.scriptMetaName.value.trim() || "Untitled Script",
        version: els.scriptMetaVersion.value.trim() || "1.0",
        description: els.scriptMetaDesc.value.trim(),
        library: se.draft.library || "",
        input: se.draft.input || "",
        context: se.draft.context || "",
        output: se.draft.output || "",
      };
      if (se.target === "new_reusable") {
        const res = await api("/api/scripts", { method: "POST", body: JSON.stringify(payload) });
        const scriptsRes = await api("/api/scripts");
        state.scripts = scriptsRes.scripts || [];
        if (state.currentStory) {
          if (!Array.isArray(state.currentStory.attached_scripts)) state.currentStory.attached_scripts = [];
          if (state.currentStory.attached_scripts.length < 10) {
            state.currentStory.attached_scripts.push({ script_id: res.script.id, enabled: true });
          }
        }
      } else if (se.target === "reusable" && se.draft.id) {
        await api(`/api/scripts/${encodeURIComponent(se.draft.id)}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
        const scriptsRes = await api("/api/scripts");
        state.scripts = scriptsRes.scripts || [];
      }
      renderStoryScriptsPanel();
      renderScenarioScriptsPanel();
      els.scriptEditorModal.classList.add("hidden");
    });

    async function applyImportedScenarioToEditor(sc) {
      await refreshScenariosList();
      els.importModal.classList.add("hidden");
      if (!sc) return;
      state.editingScenarioId = sc.id;
      state.editingScenarioChoices = (sc.choices || []).map((c) => ({ ...c }));
      state.editingScenarioCards = (sc.story_cards || []).map((c) => ({ ...c }));
      state.editingScenarioBuiltinScript = { ...(sc.builtin_script || { enabled: true, library: "", input: "", context: "", output: "" }) };
      state.editingScenarioAttachedScripts = (sc.attached_scripts || []).map((x) => ({ ...x }));
      els.scenarioFormHeading.textContent = `Edit Imported Scenario (${sc.story_cards.length} Cards)`;
      els.scenarioNameInput.value = sc.name;
      els.scenarioTypeSelect.value = sc.scenario_type || "story";
      els.scenarioOpeningInput.value = sc.opening || "";
      els.scenarioAiInstructions.value = sc.ai_instructions || "";
      els.scenarioStorySummary.value = sc.story_summary || "";
      els.scenarioPlotEssentials.value = sc.plot_essentials || "";
      els.scenarioAuthorsNote.value = sc.authors_note || "";
      els.scenarioThirdPerson.checked = Boolean(sc.third_person);
      els.scenarioCharacterName.value = sc.character_name || "";
      updateScenarioTypeUI();
      updateScenarioOpeningCounter();
      updateScenarioThirdPersonUI();
      renderScenarioChoicesList();
      renderScenarioCardsList();
      renderScenarioScriptsPanel();
      els.btnCancelEditScenario.classList.remove("hidden");
    }

    els.btnOpenImport.addEventListener("click", () => {
      els.importError.classList.add("hidden");
      els.importUrlInput.value = "";
      els.importJsonInput.value = "";
      els.importFileInput.value = "";
      els.importModal.classList.remove("hidden");
    });
    els.btnCloseImport.addEventListener("click", () => els.importModal.classList.add("hidden"));
    els.btnCancelImport.addEventListener("click", () => els.importModal.classList.add("hidden"));
    els.importFileInput.addEventListener("change", async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      els.importJsonInput.value = await file.text();
    });
    els.btnImportUrl.addEventListener("click", async () => {
      els.importError.classList.add("hidden");
      const url = els.importUrlInput.value.trim();
      if (!url) {
        els.importError.textContent = "Paste an AI Dungeon scenario URL (e.g., https://play.aidungeon.com/scenario/...).";
        els.importError.classList.remove("hidden");
        return;
      }
      const prevText = els.btnImportUrl.textContent;
      els.btnImportUrl.disabled = true;
      els.btnConfirmImport.disabled = true;
      els.btnImportUrl.textContent = "Fetching...";
      try {
        const res = await api("/api/scenarios/import-url", {
          method: "POST",
          body: JSON.stringify({ url }),
        });
        await applyImportedScenarioToEditor(res.scenario);
      } catch (err) {
        els.importError.textContent = err.message;
        els.importError.classList.remove("hidden");
      } finally {
        els.btnImportUrl.disabled = false;
        els.btnConfirmImport.disabled = false;
        els.btnImportUrl.textContent = prevText;
      }
    });
    els.btnConfirmImport.addEventListener("click", async () => {
      els.importError.classList.add("hidden");
      let parsed;
      try {
        parsed = JSON.parse(els.importJsonInput.value);
      } catch (err) {
        els.importError.textContent = `Invalid JSON: ${err.message}`;
        els.importError.classList.remove("hidden");
        return;
      }
      try {
        const res = await api("/api/scenarios/import", {
          method: "POST",
          body: JSON.stringify({ data: parsed }),
        });
        await applyImportedScenarioToEditor(res.scenario);
      } catch (err) {
        els.importError.textContent = err.message;
        els.importError.classList.remove("hidden");
      }
    });

    els.btnAddStoryCard.addEventListener("click", () => {
      if (!state.currentStory) return;
      if (!Array.isArray(state.currentStory.story_cards)) {
        state.currentStory.story_cards = [];
      }
      state.currentStory.story_cards.push({
        id: Math.random().toString(16).slice(2, 10),
        title: "",
        card_type: "Custom",
        keys: "",
        entry: "",
      });
      renderStoryCardsList();
    });

    els.btnContext.addEventListener("click", () => openContextViewer("next"));
    els.btnCloseContext.addEventListener("click", () => {
      els.contextModal.classList.add("hidden");
    });
    els.contextModal.addEventListener("click", (e) => {
      if (e.target === els.contextModal) {
        els.contextModal.classList.add("hidden");
      }
    });

    els.btnAutoSummarize.addEventListener("click", async () => {
      if (!state.currentStory) return;
      els.btnAutoSummarize.disabled = true;
      const oldText = els.btnAutoSummarize.textContent;
      els.btnAutoSummarize.textContent = "Summarizing...";
      showError("");
      try {
        const data = await api(
          `/api/stories/${encodeURIComponent(state.currentStory.id)}/summarize`,
          { method: "POST", body: "{}" }
        );
        state.currentStory = data.story;
        els.storySummaryInput.value = data.story_summary || "";
      } catch (err) {
        showError(err.message);
      } finally {
        els.btnAutoSummarize.disabled = false;
        els.btnAutoSummarize.textContent = oldText;
      }
    });

    els.scenarioOpeningInput.addEventListener("input", updateScenarioOpeningCounter);
    els.scenarioThirdPerson.addEventListener("change", updateScenarioThirdPersonUI);
    els.storyThirdPerson.addEventListener("change", () => {
      updateStoryThirdPersonUI();
      if (els.storyThirdPerson.checked && !els.storyCharacterName.value.trim()) {
        els.storyCharacterName.focus();
      }
    });

    els.btnInsertDefaultScenarioInstructions.addEventListener("click", () => {
      els.scenarioAiInstructions.value = state.defaultAiInstructions;
    });
    els.btnInsertDefaultStoryInstructions.addEventListener("click", () => {
      els.storyAiInstructions.value = state.defaultAiInstructions;
      persistAdventureSettings().catch((err) => showError(err.message));
    });

    document.querySelectorAll(".clear-card-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const target = document.getElementById(btn.dataset.clearTarget);
        if (target) target.value = "";
      });
    });

    function numInputVal(el, fallback) {
      if (!el || el.value === "") return fallback;
      const n = Number(el.value);
      return Number.isNaN(n) ? fallback : n;
    }

    function readAiSettingsFromForm() {
      return {
        temperature: numInputVal(els.settingTemp, 0.85),
        max_tokens: numInputVal(els.settingMaxTokens, 320),
        top_p: numInputVal(els.settingTopP, 0.95),
        top_k: numInputVal(els.settingTopK, 64),
        repeat_penalty: numInputVal(els.settingRepeatPenalty, 1.05),
        presence_penalty: numInputVal(els.settingPresencePenalty, 0),
        frequency_penalty: numInputVal(els.settingFrequencyPenalty, 0),
        context_length: clampContextLength(numInputVal(els.settingContextLength, 16384)),
        auto_summarize: els.settingAutoSummarize.checked,
        memory_bank_enabled: els.settingMemoryBank.checked,
        raw_model_output: els.settingRawOutput.checked,
        follow_latest_text: els.settingFollowLatest.checked,
        reasoning_effort:
          REASONING_EFFORTS[Number(els.settingReasoningEffort?.value || 0)]?.key || "off",
        enable_thinking: Number(els.settingReasoningEffort?.value || 0) > 0,
      };
    }

    let saveFeedbackTimer = null;
    function flashSavedStatus() {
      if (!els.settingsSaveStatus) return;
      if (saveFeedbackTimer) clearTimeout(saveFeedbackTimer);
      els.settingsSaveStatus.textContent = "Saved ✓";
      els.settingsSaveStatus.classList.add("saved");
      saveFeedbackTimer = setTimeout(() => {
        els.settingsSaveStatus.textContent = "All changes auto-save";
        els.settingsSaveStatus.classList.remove("saved");
      }, 1400);
    }

    async function persistAiSettingsOnly() {
      const settingsPayload = readAiSettingsFromForm();
      if (state.currentStory) {
        const data = await api(
          `/api/stories/${encodeURIComponent(state.currentStory.id)}`,
          {
            method: "PATCH",
            body: JSON.stringify({ settings: settingsPayload, save_as_default: true }),
          }
        );
        state.currentStory = data.story;
      } else {
        await api("/api/settings", {
          method: "PATCH",
          body: JSON.stringify({ settings: settingsPayload }),
        });
      }
      flashSavedStatus();
    }

    let adventureSaveTimer = null;
    async function persistAdventureSettings() {
      if (adventureSaveTimer) {
        clearTimeout(adventureSaveTimer);
        adventureSaveTimer = null;
      }
      if (!state.currentStory) {
        await persistAiSettingsOnly();
        return;
      }
      const tagsList = (els.storyDetailsTags.value || "")
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      const nextTitle = els.storyDetailsTitle.value.trim() || state.currentStory.title;
      const payload = {
        title: nextTitle,
        description: els.storyDetailsDesc.value,
        tags: tagsList,
        ai_instructions: els.storyAiInstructions.value,
        story_summary: els.storySummaryInput.value,
        plot_essentials: els.plotEssentialsInput.value,
        authors_note: els.authorsNoteInput.value,
        third_person: els.storyThirdPerson.checked,
        character_name: els.storyCharacterName.value.trim(),
        story_cards: state.currentStory.story_cards || [],
        builtin_script: state.currentStory.builtin_script || { enabled: true, library: "", input: "", context: "", output: "" },
        attached_scripts: state.currentStory.attached_scripts || [],
        settings: readAiSettingsFromForm(),
        save_as_default: true,
      };
      const data = await api(
        `/api/stories/${encodeURIComponent(state.currentStory.id)}`,
        {
          method: "PATCH",
          body: JSON.stringify(payload),
        }
      );
      state.currentStory = data.story;
      els.storyTitle.value = data.story.title || nextTitle;
      updateModeUI();
      flashSavedStatus();
    }

    function scheduleAdventureSave() {
      if (!state.currentStory) return;
      if (adventureSaveTimer) clearTimeout(adventureSaveTimer);
      adventureSaveTimer = setTimeout(() => {
        persistAdventureSettings().catch((err) => showError(err.message));
      }, 400);
    }

    if (els.settingContextLengthSlider) {
      els.settingContextLengthSlider.addEventListener("input", () => {
        const clamped = clampContextLength(els.settingContextLengthSlider.value);
        els.settingContextLengthSlider.value = String(clamped);
        els.settingContextLength.value = String(clamped);
      });
    }

    if (els.settingContextLength) {
      els.settingContextLength.addEventListener("input", () => {
        const parsed = Number(els.settingContextLength.value);
        if (Number.isFinite(parsed) && parsed > 0 && els.settingContextLengthSlider) {
          els.settingContextLengthSlider.value = String(clampContextLength(parsed));
        }
      });
      const clampInputField = () => {
        const clamped = clampContextLength(els.settingContextLength.value);
        els.settingContextLength.value = String(clamped);
        if (els.settingContextLengthSlider) {
          els.settingContextLengthSlider.value = String(clamped);
        }
      };
      els.settingContextLength.addEventListener("change", clampInputField);
      els.settingContextLength.addEventListener("blur", clampInputField);
    }

    if (els.settingThinking) {
      els.settingThinking.addEventListener("change", () => {
        syncReasoningEffortUI(els.settingThinking.checked ? "medium" : "off");
      });
    }

    if (els.settingReasoningEffort) {
      els.settingReasoningEffort.addEventListener("input", () => {
        const idx = Number(els.settingReasoningEffort.value);
        const item = REASONING_EFFORTS[idx] || REASONING_EFFORTS[0];
        syncReasoningEffortUI(item.key);
      });
    }

    els.effortStops.forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.dataset.effort || "off";
        syncReasoningEffortUI(key);
        persistAiSettingsOnly().catch((err) => showError(err.message));
      });
    });

    els.settingsPaneAi.querySelectorAll("input").forEach((inp) => {
      inp.addEventListener("change", () => {
        persistAiSettingsOnly().catch((err) => showError(err.message));
      });
    });

    [
      els.storyDetailsTitle,
      els.storyDetailsDesc,
      els.storyDetailsTags,
      els.storyAiInstructions,
      els.storySummaryInput,
      els.plotEssentialsInput,
      els.authorsNoteInput,
      els.storyCharacterName,
    ].forEach((el) => {
      if (!el) return;
      el.addEventListener("input", scheduleAdventureSave);
      el.addEventListener("change", () => {
        persistAdventureSettings().catch((err) => showError(err.message));
      });
    });

    els.storyThirdPerson.addEventListener("change", () => {
      persistAdventureSettings().catch((err) => showError(err.message));
    });

    els.btnEndpoint.addEventListener("click", openEndpointModal);
    els.llmPill.addEventListener("click", openEndpointModal);
    els.btnCloseEndpoint.addEventListener("click", () => els.endpointModal.classList.add("hidden"));
    els.btnCancelEndpoint.addEventListener("click", () => els.endpointModal.classList.add("hidden"));
    els.endpointModal.addEventListener("click", (e) => {
      if (e.target === els.endpointModal) els.endpointModal.classList.add("hidden");
    });
    els.btnEpClearKey.addEventListener("click", () => {
      epClearKeyFlag = true;
      els.epKeyInput.value = "";
      els.epKeyInput.placeholder = "Key will be cleared on Save";
      els.btnEpClearKey.classList.add("hidden");
    });
    els.epModelSelect.addEventListener("change", () => {
      if (els.epModelSelect.value) {
        els.epModelInput.value = els.epModelSelect.value;
      }
    });
    els.btnEpRefreshModels.addEventListener("click", async () => {
      const llm_url = els.epUrlInput.value.trim();
      if (!llm_url) {
        showEndpointMsg("Enter a Base URI first.");
        return;
      }
      showEndpointMsg("");
      const prev = els.btnEpRefreshModels.textContent;
      els.btnEpRefreshModels.disabled = true;
      els.btnEpRefreshModels.textContent = "Fetching...";
      try {
        const res = await api("/api/llm/models", {
          method: "POST",
          body: JSON.stringify({
            llm_url,
            api_key: els.epKeyInput.value.trim(),
            clear_api_key: epClearKeyFlag,
          }),
        });
        const models = res.models || [];
        populateEndpointModels(models);
        if (models.length === 1) {
          showEndpointMsg(`Found 1 model — selected "${models[0]}" automatically.`, true);
        } else if (models.length > 1) {
          showEndpointMsg(`Found ${models.length} models. Select one above.`, true);
        } else {
          showEndpointMsg("Endpoint reachable, but no models were listed.");
        }
      } catch (err) {
        showEndpointMsg(err.message);
      } finally {
        els.btnEpRefreshModels.disabled = false;
        els.btnEpRefreshModels.textContent = prev;
      }
    });
    els.btnSaveEndpoint.addEventListener("click", async () => {
      const llm_url = els.epUrlInput.value.trim();
      if (!llm_url) {
        showEndpointMsg("Please enter a Base URI.");
        return;
      }
      showEndpointMsg("");
      const prev = els.btnSaveEndpoint.textContent;
      els.btnSaveEndpoint.disabled = true;
      els.btnSaveEndpoint.textContent = "Connecting...";
      try {
        const payload = {
          llm_url,
          model: els.epModelInput.value.trim(),
          clear_api_key: epClearKeyFlag,
        };
        if (els.epKeyInput.value.trim()) {
          payload.api_key = els.epKeyInput.value.trim();
        }
        const res = await api("/api/llm/config", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        const st = res.status || {};
        const models = st.available_models || [];
        if (!payload.model && models.length === 1) {
          // Persist auto-selected single model cleanly
          await api("/api/llm/config", {
            method: "POST",
            body: JSON.stringify({ llm_url, model: models[0] }),
          });
          st.model = models[0];
        }
        applyLlmStatusUI(st);
        if (st.state === "ready" || st.state === "loading") {
          els.endpointModal.classList.add("hidden");
        } else {
          showEndpointMsg(`Saved, but could not connect: ${st.detail || st.state}`);
        }
      } catch (err) {
        showEndpointMsg(err.message);
      } finally {
        els.btnSaveEndpoint.disabled = false;
        els.btnSaveEndpoint.textContent = prev;
      }
    });

    els.btnStartLlm.addEventListener("click", async () => {
      els.btnStartLlm.disabled = true;
      els.btnStartLlm.textContent = "Starting...";
      try {
        await api("/api/llm/start", { method: "POST", body: "{}" });
        await pollLlmStatus();
      } catch (err) {
        showError(err.message);
      } finally {
        els.btnStartLlm.disabled = false;
        els.btnStartLlm.textContent = "Start LLM";
      }
    });
  }

  async function init() {
    wireEvents();
    updateModeUI();

    const [scenData, storiesData, scriptsData] = await Promise.all([
      api("/api/scenarios"),
      api("/api/stories"),
      api("/api/scripts"),
    ]);

    state.scripts = scriptsData.scripts || [];
    state.scenarios = scenData.scenarios || [];
    state.defaultAiInstructions = scenData.default_ai_instructions || "";
    renderScenariosGrid();
    renderScenarioScriptsPanel();

    state.stories = storiesData.stories || [];
    renderStoriesList();
    setActiveView("home");
    setHomeTab(state.stories.length > 0 ? "adventures" : "scenarios");

    await pollLlmStatus();
    setInterval(pollLlmStatus, 4000);
  }

  init().catch((err) => {
    showError(err.message);
  });
})();
