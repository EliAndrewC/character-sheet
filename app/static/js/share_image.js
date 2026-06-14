// Native "Share" helper for the roll-result card PNG.
//
// Why this exists: on phones the "Copy as image" path is a dead end. Chrome
// for Android writes the PNG to the clipboard as a content:// FileProvider
// URI, and Discord's mobile composer pastes that URI as plain text instead of
// attaching the image (iOS behaves similarly). The Web Share API hands the
// PNG file straight to the OS share sheet, from which the user can post it
// directly into Discord - bypassing the clipboard entirely. Desktops keep the
// copy-paste flow, which works there.
//
// Loaded as a plain global in base.html (next to roll_math.js), so the dice
// roller, freeform roller, and read-only roll modal can all reach it on both
// the sheet and roll-history pages. Exposes:
//   window.L7RUseShareImage    - bool, computed once: prefer Share over Copy?
//   window.L7RShareImageBlob() - async, hands a PNG Blob to the share sheet.
(function () {
  "use strict";

  // Can this browser share an image FILE via the native share sheet? Probed
  // with a real File because canShare() needs one to answer. True on Android
  // Chrome / iOS Safari; false on most desktop browsers.
  function canShareImageFile() {
    try {
      var probe = new File([new Blob(["l7r"], { type: "image/png" })],
                           "roll.png", { type: "image/png" });
      return !!(navigator.canShare && navigator.canShare({ files: [probe] }));
    } catch (e) {
      return false;
    }
  }

  // Touch-primary device (phone/tablet) rather than a mouse desktop. Some
  // desktops also support file sharing, but there Copy-paste is the expected
  // gesture, so we only swap in Share on coarse-pointer devices.
  function coarsePointer() {
    try {
      return !!(window.matchMedia && window.matchMedia("(pointer: coarse)").matches);
    } catch (e) {
      return false;
    }
  }

  // Offer Share instead of Copy only when the device can actually deliver the
  // file AND is the kind of device where the clipboard path fails.
  window.L7RUseShareImage = canShareImageFile() && coarsePointer();

  // Hand a PNG Blob to the OS share sheet. Resolves to one of
  // 'shared' | 'cancelled' | 'unsupported' | 'failed' so the caller can show
  // transient feedback. A dismissed sheet (AbortError) is 'cancelled', not a
  // failure, so it must not surface an error.
  window.L7RShareImageBlob = async function (blob, filename) {
    if (!blob || typeof navigator.share !== "function") return "unsupported";
    var file = new File([blob], filename || "l7r-roll.png", { type: "image/png" });
    try {
      if (navigator.canShare && !navigator.canShare({ files: [file] })) {
        return "unsupported";
      }
      await navigator.share({ files: [file] });
      return "shared";
    } catch (e) {
      return (e && e.name === "AbortError") ? "cancelled" : "failed";
    }
  };
})();
