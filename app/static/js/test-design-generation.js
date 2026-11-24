"use strict";

(() => {
  const form = document.getElementById("generation-form");
  const button = document.getElementById("generate-button");
  const status = document.getElementById("generation-status");
  if (!form || !button || !status) return;

  const configurationBlocked = button.disabled;
  const idleLabel = button.textContent;
  let submitting = false;

  const reset = () => {
    submitting = false;
    button.disabled = configurationBlocked;
    button.textContent = idleLabel;
    form.removeAttribute("aria-busy");
    status.hidden = true;
    status.textContent = "";
  };

  form.addEventListener("submit", (event) => {
    if (configurationBlocked || submitting) {
      event.preventDefault();
      return;
    }
    if (event.defaultPrevented || !form.checkValidity()) return;
    // Keep the native POST: the server owns the request key and result.
    // Disable only the button, so all input fields remain in the POST body.
    submitting = true;
    button.disabled = true;
    button.textContent = "正在生成…";
    form.setAttribute("aria-busy", "true");
    status.hidden = false;
    status.textContent = "请求已提交，正在等待生成结果。请勿重复提交；可在新窗口查看生成记录。";
  });

  window.addEventListener("offline", () => {
    if (!submitting) return;
    status.hidden = false;
    status.textContent = "连接已中断，服务端可能仍在处理。请恢复连接后查看生成记录确认结果，不要直接重新提交。";
  });

  // A cached page restored with Back must not retain a disabled submit button.
  // Its original request key is preserved; replay is checked by the server.
  window.addEventListener("pageshow", reset);
  reset();
})();
