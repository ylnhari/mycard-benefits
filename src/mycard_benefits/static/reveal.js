const REVEAL_HIDE_SECONDS = 30;
const REVEAL_CLIPBOARD_SECONDS = 28;

export function createRevealController({ protectedJson }) {
  let revealContext = null;
  let revealCardId = null;
  let revealOffering = null;
  let revealHideTimer = null;
  let revealClipboardTimer = null;
  let revealClipboardButton = null;

  function revealSetMode(mode) {
    const pin = mode === "pin";
    const code = document.querySelector("#revealCode");
    const confirm = document.querySelector("#revealCodeConfirm");
    const label = code.closest(".reveal-field")?.querySelector("label");
    document.querySelector("#revealPinMode").setAttribute("aria-pressed", String(pin));
    document.querySelector("#revealPassphraseMode").setAttribute("aria-pressed", String(!pin));
    if (label) label.textContent = pin ? "Your PIN" : "Your passphrase";
    for (const field of [code, confirm]) {
      field.value = "";
      field.minLength = pin ? 6 : 12;
      field.inputMode = pin ? "numeric" : "text";
    }
    document.querySelector("#revealCreateError").hidden = true;
    document.querySelector("#revealCreateForm").dataset.credentialType = pin ? "pin" : "passphrase";
  }

  function revealClearClipboard(clearClipboard = true) {
    if (revealClipboardTimer) clearInterval(revealClipboardTimer);
    revealClipboardTimer = null;
    if (revealClipboardButton) revealClipboardButton.textContent = "Copy";
    revealClipboardButton = null;
    if (clearClipboard && globalThis.navigator?.clipboard?.writeText) {
      // This call is intentionally made at the expiry boundary as well as on
      // hide, so a visible countdown always has a real clearing action behind it.
      globalThis.navigator.clipboard.writeText("").catch(() => {});
    }
  }

  function revealHideFields() {
    if (revealHideTimer) clearInterval(revealHideTimer);
    revealHideTimer = null;
    revealClearClipboard();
    revealContext = null;
    document.querySelector("#revealCardNumber").textContent = "•••• •••• ••••";
    document.querySelector("#revealExpiry").textContent = "•• / ••";
    document.querySelector("#revealCvv").textContent = "•••";
    document.querySelector("#revealCvvButton").textContent = "Show";
    document.querySelector("#revealHideIn").textContent = "Hidden.";
  }

  function revealStartTimer() {
    if (revealHideTimer) clearInterval(revealHideTimer);
    let remaining = REVEAL_HIDE_SECONDS;
    const timer = document.querySelector("#revealHideIn");
    timer.textContent = `Hidden again in ${remaining} seconds.`;
    revealHideTimer = setInterval(() => {
      remaining -= 1;
      timer.textContent = remaining > 0
        ? `Hidden again in ${remaining} seconds.`
        : "Hidden.";
      if (remaining <= 0) revealHideFields();
    }, 1000);
  }

  function revealRenderValues(result, offering) {
    revealContext = {
      cardNumber: result.card_number,
      expiry: result.expiry,
      cvv: result.cvv,
    };
    document.querySelector("#cardRevealPrompt").hidden = false;
    document.querySelector("#revealCreateState").hidden = true;
    document.querySelector("#revealShownState").hidden = false;
    document.querySelector("#revealProductName").textContent = offering?.display_name || "Card details";
    document.querySelector("#revealCardNumber").textContent = result.card_number;
    document.querySelector("#revealExpiry").textContent = result.expiry;
    document.querySelector("#revealCvv").textContent = "•••";
    const cvvButton = document.querySelector("#revealCvvButton");
    cvvButton.disabled = !result.cvv;
    cvvButton.textContent = result.cvv ? "Show" : "Not stored";
    revealStartTimer();
    document.querySelector("#revealHideNow").focus({ preventScroll: true });
  }

  function revealShowCreate(offering, message = "") {
    revealHideFields();
    document.querySelector("#cardRevealPrompt").hidden = false;
    document.querySelector("#revealCreateState").hidden = false;
    document.querySelector("#revealShownState").hidden = true;
    document.querySelector("#revealProductName").textContent = offering?.display_name || "";
    const error = document.querySelector("#revealCreateError");
    error.textContent = message;
    error.hidden = !message;
    revealSetMode("pin");
    document.querySelector("#revealCode").focus({ preventScroll: true });
  }

  function revealErrorText(error) {
    const messages = {
      credential_invalid: "That code could not be accepted.",
      credential_exists: "A card-details code already exists in this vault.",
      credential_locked: "Card details are temporarily unavailable. Try again later.",
      detail_session_required: "Card details are unavailable in this browser session. The rest of MyCard keeps working.",
      card_details_unavailable: "Full card details are not stored for this card.",
    };
    if (messages[error?.code]) return messages[error.code];
    // No message here blames the connection. Reveal is not refused for reaching
    // MyCard through the gateway: the server answers a proxied request exactly
    // as a direct one, so telling someone on their phone that their card
    // details are locked to another computer states something untrue about a
    // request that would have succeeded.
    return "Card details are unavailable right now. The rest of MyCard keeps working.";
  }

  async function openCardReveal(card, offering) {
    revealCardId = card.card_id;
    revealOffering = offering;
    revealContext = null;
    document.querySelector("#cardRevealPrompt").hidden = false;
    document.querySelector("#revealCreateState").hidden = true;
    document.querySelector("#revealShownState").hidden = true;
    try {
      const result = await protectedJson(
        `/api/v1/private/cards/${encodeURIComponent(card.card_id)}/reveal-authorize`,
        { mode: "reuse" },
      );
      revealRenderValues(result, offering);
    } catch (error) {
      if (error?.code === "credential_required") {
        revealShowCreate(offering);
        return;
      }
      revealShowCreate(offering, revealErrorText(error));
    }
  }

  async function submitRevealCreate(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const code = document.querySelector("#revealCode");
    const confirm = document.querySelector("#revealCodeConfirm");
    const error = document.querySelector("#revealCreateError");
    const button = document.querySelector("#revealCreateButton");
    const credentialType = form.dataset.credentialType || "pin";
    const minimum = credentialType === "pin" ? 6 : 12;
    error.hidden = true;
    if (code.value.length < minimum) {
      error.textContent = credentialType === "pin"
        ? "A PIN needs at least 6 digits."
        : "A passphrase needs at least 12 characters.";
      error.hidden = false;
      return;
    }
    if (credentialType === "pin" && !/^[0-9]+$/.test(code.value)) {
      error.textContent = "A PIN is digits only. Choose Passphrase for letters.";
      error.hidden = false;
      return;
    }
    if (code.value !== confirm.value) {
      error.textContent = "Those two do not match.";
      error.hidden = false;
      return;
    }
    const credential = code.value;
    const confirmation = confirm.value;
    code.value = "";
    confirm.value = "";
    button.disabled = true;
    try {
      const result = await protectedJson(
        `/api/v1/private/cards/${encodeURIComponent(revealCardId || "")}/reveal-authorize`,
        { mode: "create", credential_type: credentialType, credential, confirm: confirmation },
      );
      revealRenderValues(result, revealOffering);
    } catch (requestError) {
      error.textContent = revealErrorText(requestError);
      error.hidden = false;
    } finally {
      button.disabled = false;
    }
  }

  async function copyRevealValue(value, button) {
    if (!value || !globalThis.navigator?.clipboard?.writeText) return;
    try {
      revealClearClipboard(false);
      await globalThis.navigator.clipboard.writeText(value);
    } catch {
      button.textContent = "Copy";
      return;
    }
    let remaining = REVEAL_CLIPBOARD_SECONDS;
    revealClipboardButton = button;
    button.textContent = `Copy · 0:${String(remaining).padStart(2, "0")}`;
    revealClipboardTimer = setInterval(() => {
      remaining -= 1;
      if (remaining <= 0) {
        clearInterval(revealClipboardTimer);
        revealClipboardTimer = null;
        // The countdown reaches zero here, where the clipboard is actually
        // overwritten rather than merely making the button look reset.
        globalThis.navigator.clipboard.writeText("").catch(() => {});
        button.textContent = "Copy";
        revealClipboardButton = null;
        return;
      }
      button.textContent = `Copy · 0:${String(remaining).padStart(2, "0")}`;
    }, 1000);
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden && revealContext) revealHideFields();
  });
  window.addEventListener("blur", () => {
    if (revealContext) revealHideFields();
  });
  window.addEventListener("pagehide", revealHideFields);
  document.querySelector("#revealPinMode")?.addEventListener("click", () => revealSetMode("pin"));
  document.querySelector("#revealPassphraseMode")?.addEventListener("click", () => revealSetMode("passphrase"));
  document.querySelector("#revealCreateForm")?.addEventListener("submit", submitRevealCreate);
  document.querySelector("#revealCopyNumber")?.addEventListener("click", () => copyRevealValue(revealContext?.cardNumber, document.querySelector("#revealCopyNumber")));
  document.querySelector("#revealCopyExpiry")?.addEventListener("click", () => copyRevealValue(revealContext?.expiry, document.querySelector("#revealCopyExpiry")));
  document.querySelector("#revealCvvButton")?.addEventListener("click", () => {
    if (!revealContext?.cvv) return;
    const value = document.querySelector("#revealCvv");
    const button = document.querySelector("#revealCvvButton");
    const visible = value.textContent === revealContext.cvv;
    value.textContent = visible ? "•••" : revealContext.cvv;
    button.textContent = visible ? "Show" : "Hide";
    if (!visible) revealStartTimer();
  });
  document.querySelector("#revealHideNow")?.addEventListener("click", revealHideFields);

  return { open: openCardReveal };
}
