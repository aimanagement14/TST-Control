(function () {
    "use strict";

    var COPY_LABEL = "Copiar";
    var COPIED_LABEL = "✓ Copiado";
    var FAIL_LABEL = "✗ Error";
    var VERIFY_LABEL = "⚠ Distinto";

    function isTextField(el) {
        if (!el) return false;
        var tag = el.tagName ? el.tagName.toLowerCase() : "";
        if (tag === "textarea") return true;
        if (tag === "input") {
            var t = (el.type || "text").toLowerCase();
            return t === "text" || t === "number" || t === "search" || t === "url" || t === "email";
        }
        return false;
    }

    function isVisible(el) {
        if (!el) return false;
        if (el.disabled || el.readOnly === false && el.offsetParent === null && el.type === "hidden") {
            return false;
        }
        var rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }

    function findFields(root) {
        var scope = root || document;
        var all = scope.querySelectorAll("textarea, input");
        var out = [];
        for (var i = 0; i < all.length; i++) {
            if (isTextField(all[i]) && isVisible(all[i])) out.push(all[i]);
        }
        return out;
    }

    function alreadyWrapped(field) {
        return field.parentElement && field.parentElement.classList &&
            field.parentElement.classList.contains("copy-field");
    }

    function makeWrapper(field) {
        var wrap = document.createElement("div");
        wrap.className = "copy-field";
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "copy-btn";
        btn.textContent = COPY_LABEL;
        btn.setAttribute("aria-label", "Copiar texto al portapapeles");
        btn.setAttribute("data-copy-btn", "");
        return { wrap: wrap, btn: btn };
    }

    function writeClipboard(text) {
        if (navigator.clipboard && navigator.clipboard.writeText && window.isSecureContext) {
            return navigator.clipboard.writeText(text).then(
                function () { return true; },
                function () { return legacyCopy(text); }
            );
        }
        return Promise.resolve(legacyCopy(text));
    }

    function readClipboard() {
        if (navigator.clipboard && navigator.clipboard.readText && window.isSecureContext) {
            return navigator.clipboard.readText().catch(function () { return null; });
        }
        return Promise.resolve(null);
    }

    function legacyCopy(text) {
        var helper = document.createElement("textarea");
        helper.value = text;
        helper.setAttribute("readonly", "");
        helper.style.position = "fixed";
        helper.style.top = "-9999px";
        helper.style.opacity = "0";
        document.body.appendChild(helper);
        helper.select();
        var ok = false;
        try { ok = document.execCommand("copy"); }
        catch (e) { ok = false; }
        document.body.removeChild(helper);
        return ok;
    }

    function feedback(btn, label, cls) {
        if (btn.dataset.copyBusy === "1") return;
        btn.dataset.copyBusy = "1";
        var original = btn.dataset.copyOriginal || btn.textContent;
        btn.dataset.copyOriginal = original;
        btn.textContent = label;
        btn.classList.remove("is-ok", "is-fail", "is-warn");
        if (cls) btn.classList.add(cls);
        window.setTimeout(function () {
            btn.textContent = original;
            btn.classList.remove("is-ok", "is-fail", "is-warn");
            delete btn.dataset.copyBusy;
        }, 1800);
    }

    function attach(field) {
        if (alreadyWrapped(field)) return;
        var parts = makeWrapper(field);
        var parent = field.parentNode;
        parent.insertBefore(parts.wrap, field);
        parts.wrap.appendChild(field);
        parts.wrap.appendChild(parts.btn);

        parts.btn.addEventListener("click", function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var text = field.value != null ? field.value : field.textContent;
            Promise.resolve(writeClipboard(text)).then(function (ok) {
                if (!ok) { feedback(parts.btn, FAIL_LABEL, "is-fail"); return; }
                return readClipboard().then(function (back) {
                    if (back === null) {
                        feedback(parts.btn, COPIED_LABEL, "is-ok");
                        return;
                    }
                    var backNorm = back.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
                    var textNorm = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
                    if (back === text || backNorm === textNorm) {
                        feedback(parts.btn, COPIED_LABEL, "is-ok");
                    } else {
                        feedback(parts.btn, VERIFY_LABEL, "is-warn");
                        console.warn("[copy-fields] round-trip mismatch", {
                            expected_length: text.length,
                            actual_length: back.length,
                            expected_first: text.slice(0, 40),
                            actual_first: back.slice(0, 40)
                        });
                    }
                });
            });
        });
    }

    function attachAll(root) {
        var fields = findFields(root);
        for (var i = 0; i < fields.length; i++) attach(fields[i]);
    }

    function boot() {
        attachAll(document);
        var observer = new MutationObserver(function (muts) {
            for (var i = 0; i < muts.length; i++) {
                var m = muts[i];
                if (m.addedNodes && m.addedNodes.length) {
                    for (var j = 0; j < m.addedNodes.length; j++) {
                        var n = m.addedNodes[j];
                        if (n.nodeType !== 1) continue;
                        if (isTextField(n)) attach(n);
                        else if (n.querySelectorAll) attachAll(n);
                    }
                }
            }
        });
        observer.observe(document.body, { childList: true, subtree: true });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
