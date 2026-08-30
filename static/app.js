/* Todo Sobre Todo — comportamientos de interfaz.
   Sin dependencias: copiar prompts, contadores en vivo y cierre de avisos. */

(function () {
    "use strict";

    var WORD = /[\p{L}\p{N}_]+/gu;

    function countWords(text) {
        var matches = (text || "").match(WORD);
        return matches ? matches.length : 0;
    }

    function timecode(seconds) {
        var total = Math.max(0, Math.round(seconds));
        var mm = String(Math.floor(total / 60)).padStart(2, "0");
        var ss = String(total % 60).padStart(2, "0");
        return mm + ":" + ss;
    }

    /* --- Copiar al portapapeles ------------------------------------------ */

    function textToCopy(button) {
        var selector = button.getAttribute("data-copy");
        if (selector) {
            var node = document.querySelector(selector);
            if (!node) return "";
            return "value" in node ? node.value : node.textContent;
        }
        var scriptNode = button.closest(".panel-inset");
        if (scriptNode) {
            return scriptTextToCopy(scriptNode);
        }
        var scope = button.closest("[data-prompt]") || button.closest("form");
        if (!scope) return "";
        var sys = scope.querySelector('[name="sys_prompt"]');
        var user = scope.querySelector('[name="user_prompt"]');
        var parts = [];
        if (sys && sys.value.trim()) parts.push("SYSTEM:\n" + sys.value.trim());
        if (user && user.value.trim()) parts.push("USER:\n" + user.value.trim());
        return parts.join("\n\n");
    }

    function scriptTextToCopy(scope) {
        var out = [];
        var title = scope.querySelector(".script-title");
        if (title) out.push("# " + title.textContent.trim());
        var blocks = scope.querySelectorAll(".script-block");
        blocks.forEach(function (block) {
            var tag = block.querySelector(".script-tag");
            var body = block.querySelector(".script-body");
            if (tag && body) {
                out.push("## " + tag.textContent.trim());
                out.push(body.textContent.replace(/\s+/g, " ").trim());
                out.push("");
            }
        });
        if (!out.length) {
            var fallback = scope.querySelector("pre.code");
            if (fallback) return fallback.textContent;
        }
        return out.join("\n").trim();
    }

    function feedback(button, message) {
        if (button.dataset.copied) return;
        var original = button.textContent;
        button.dataset.copied = "1";
        button.textContent = message;
        window.setTimeout(function () {
            button.textContent = original;
            delete button.dataset.copied;
        }, 1800);
    }

    function copyText(text) {
        if (navigator.clipboard && window.isSecureContext) {
            return navigator.clipboard.writeText(text);
        }
        return new Promise(function (resolve, reject) {
            var helper = document.createElement("textarea");
            helper.value = text;
            helper.setAttribute("readonly", "");
            helper.style.position = "fixed";
            helper.style.opacity = "0";
            document.body.appendChild(helper);
            helper.select();
            var done = document.execCommand("copy");
            document.body.removeChild(helper);
            done ? resolve() : reject(new Error("copy failed"));
        });
    }

    document.addEventListener("click", function (event) {
        var button = event.target.closest("[data-copy-button], [data-copy-script]");
        if (!button) return;
        event.preventDefault();
        var text = textToCopy(button);
        if (!text) {
            feedback(button, "Nada que copiar");
            return;
        }
        copyText(text).then(function () {
            feedback(button, "Copiado");
        }).catch(function () {
            feedback(button, "Selecciona y copia a mano");
        });
    });

    /* --- Contadores en vivo (palabras y duración estimada) --------------- */

    function updateSpec(spec) {
        var scope = spec.closest("form") || document;
        var field = scope.querySelector('[name="' + spec.dataset.for + '"]');
        if (!field) return;

        var words = countWords(field.value);
        var wpm = parseInt(spec.dataset.wpm, 10) || 150;
        var min = parseInt(spec.dataset.min, 10) || 0;
        var max = parseInt(spec.dataset.max, 10) || 0;

        var wordsOut = spec.querySelector("[data-words]");
        var timeOut = spec.querySelector("[data-runtime]");
        if (wordsOut) wordsOut.textContent = words;
        if (timeOut) timeOut.textContent = timecode(words / wpm * 60);

        spec.classList.remove("is-ok", "is-warn", "is-over");
        if (!words || !max) return;
        if (words > max) spec.classList.add("is-over");
        else if (words < min) spec.classList.add("is-warn");
        else spec.classList.add("is-ok");
    }

    document.querySelectorAll("[data-spec]").forEach(function (spec) {
        var scope = spec.closest("form") || document;
        var field = scope.querySelector('[name="' + spec.dataset.for + '"]');
        if (!field) return;
        field.addEventListener("input", function () { updateSpec(spec); });
        updateSpec(spec);
    });

    /* --- Deslizadores con lectura numérica ------------------------------- */

    document.querySelectorAll(".slider input[type=range]").forEach(function (range) {
        var output = range.parentElement.querySelector("output");
        if (!output) return;
        var render = function () { output.textContent = range.value; };
        range.addEventListener("input", render);
        render();
    });

    /* --- Cerrar avisos --------------------------------------------------- */

    document.addEventListener("click", function (event) {
        var close = event.target.closest(".flash-close");
        if (!close) return;
        var flash = close.closest(".flash");
        if (flash) flash.remove();
    });

    /* --- Mantener visible la etapa activa de la tira -------------------- */

    var current = document.querySelector(".rail-cell.is-current");
    if (current && current.scrollIntoView) {
        current.scrollIntoView({ block: "nearest", inline: "center" });
    }
})();
