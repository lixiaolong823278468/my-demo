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

const run = () => {
  closeSelectOnRepeatClick();
  tuneSelectPopover();
};

run();
const observer = new MutationObserver(run);
observer.observe(window.parent.document.body, { subtree: true, childList: true, attributes: true });
