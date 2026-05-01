const closeSelectOnRepeatClick = () => {
  const selects = window.parent.document.querySelectorAll('div[data-baseweb="select"]');
  selects.forEach((root) => {
    if (root.dataset.codexBound === "1") return;
    root.dataset.codexBound = "1";
    root.addEventListener(
      "mousedown",
      (event) => {
        const expandedNode = root.querySelector('[aria-expanded="true"]');
        const clickedOption = event.target.closest('[role="option"]');
        if (expandedNode && !clickedOption) {
          event.preventDefault();
          event.stopPropagation();
          const focusNode = root.querySelector("input,[role='combobox'],button,div");
          if (focusNode) {
            focusNode.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
            if (typeof focusNode.blur === "function") focusNode.blur();
          }
        }
      },
      true,
    );
  });
};

const tuneSelectPopover = () => {
  const popovers = window.parent.document.querySelectorAll('div[data-baseweb="popover"]');
  popovers.forEach((node) => {
    node.style.background = "#ffffff";
    node.style.color = "#1d2129";
  });
};

/* ── Inject copy buttons into Streamlit dataframes ── */
const injectCopyButtons = () => {
  const parent = window.parent.document;
  const editors = parent.querySelectorAll('[data-testid="stDataFrame"], [data-testid="stDataEditor"]');
  editors.forEach((editor, index) => {
    if (editor.dataset.copyInjected === "1") return;
    editor.dataset.copyInjected = "1";

    const btn = parent.createElement("button");
    btn.textContent = "📋 复制";
    btn.style.cssText = [
      "position:absolute;top:6px;right:10px;z-index:10",
      "padding:4px 10px;border-radius:8px;border:1px solid #d9d9d9",
      "background:#fff;color:#4e5969;font-size:12px;cursor:pointer",
      "transition:all .2s ease;font-family:inherit",
    ].join(";");

    btn.addEventListener("mouseenter", () => {
      btn.style.borderColor = "#4096ff";
      btn.style.color = "#1677ff";
    });
    btn.addEventListener("mouseleave", () => {
      btn.style.borderColor = "#d9d9d9";
      btn.style.color = "#4e5969";
    });

    btn.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const grid = editor.querySelector('[role="grid"]');
      if (!grid) return;
      const rows = Array.from(grid.querySelectorAll('[role="row"]'));
      const csv = rows
        .map((row) =>
          Array.from(row.querySelectorAll('[role="columnheader"], [role="gridcell"]'))
            .map((cell) => {
              let text = (cell.textContent || "").replace(/"/g, '""').trim();
              if (text.includes(",") || text.includes('"') || text.includes("\n")) {
                text = '"' + text + '"';
              }
              return text;
            })
            .join(","),
        )
        .join("\n");

      try {
        await navigator.clipboard.writeText(csv);
        btn.textContent = "✓ 已复制";
        btn.style.background = "#f6ffed";
        btn.style.borderColor = "#52c41a";
        btn.style.color = "#52c41a";
      } catch {
        const ta = parent.createElement("textarea");
        ta.value = csv;
        ta.style.cssText = "position:fixed;left:-9999px";
        parent.body.appendChild(ta);
        ta.select();
        parent.execCommand("copy");
        parent.body.removeChild(ta);
        btn.textContent = "✓ 已复制";
        btn.style.background = "#f6ffed";
        btn.style.borderColor = "#52c41a";
        btn.style.color = "#52c41a";
      }
      setTimeout(() => {
        btn.textContent = "📋 复制";
        btn.style.background = "#fff";
        btn.style.borderColor = "#d9d9d9";
        btn.style.color = "#4e5969";
      }, 1600);
    });

    editor.style.position = editor.style.position || "relative";
    editor.appendChild(btn);
  });
};

/* ── Keyboard navigation between Streamlit tabs ── */
const bindTabKeyboardNav = () => {
  const parent = window.parent.document;
  const tabs = parent.querySelectorAll('[data-testid="stTabs"] button[role="tab"]');
  if (!tabs.length || parent.dataset.tabKeysBound === "1") return;
  parent.dataset.tabKeysBound = "1";

  parent.addEventListener("keydown", (event) => {
    if (event.target.matches("input, textarea, [contenteditable]")) return;
    if (event.ctrlKey || event.metaKey || event.altKey) return;

    const key = event.key.toLowerCase();
    const tabMap = { "1": 0, "2": 1, "3": 2, "4": 3 };
    const index = tabMap[key];
    if (index !== undefined) {
      const currentTabs = parent.querySelectorAll('[data-testid="stTabs"] button[role="tab"]');
      if (currentTabs[index]) {
        event.preventDefault();
        currentTabs[index].click();
      }
    }
    if (key === "r" && !event.shiftKey) {
      const refreshBtn = parent.querySelector('[data-testid="stApp"] button[kind="secondary"]');
      if (refreshBtn) {
        event.preventDefault();
        refreshBtn.click();
      }
    }
  });
};

/* ── Dark mode sync with system preference ── */
const syncDarkMode = () => {
  const parent = window.parent.document;
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  parent.documentElement.classList.toggle("dark-enabled", prefersDark);
};

/* ── Resize observer for chart containers ── */
const observeChartResize = () => {
  const parent = window.parent.document;
  const charts = parent.querySelectorAll('[data-testid="stArrowVegaLiteChart"]');
  charts.forEach((chart) => {
    if (chart.dataset.resizeObserved === "1") return;
    chart.dataset.resizeObserved = "1";

    const observer = new ResizeObserver(() => {
      const canvas = chart.querySelector("canvas");
      if (canvas) {
        canvas.style.maxWidth = "100%";
        canvas.style.height = "auto";
      }
    });
    observer.observe(chart);
  });
};

const run = () => {
  closeSelectOnRepeatClick();
  tuneSelectPopover();
  injectCopyButtons();
  bindTabKeyboardNav();
  syncDarkMode();
  observeChartResize();
};

run();
const observer = new MutationObserver(run);
observer.observe(window.parent.document.body, { subtree: true, childList: true, attributes: true });
