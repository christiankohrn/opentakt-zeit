import { useRef, useState, type ComponentProps, type FocusEvent, type MouseEvent, type PointerEvent } from "react";
import { IconEye, IconEyeOff } from "./Icons";

type Props = Omit<ComponentProps<"input">, "type">;

function isAppleTouch() {
  if (typeof navigator === "undefined") return false;
  if (/iP(ad|hone|od)/.test(navigator.userAgent)) return true;
  return navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1;
}

function applyRevealAttrs(el: HTMLInputElement, plaintext: boolean, autoComplete?: string) {
  el.setAttribute("autocorrect", "off");
  el.setAttribute("autocapitalize", "none");
  el.setAttribute("spellcheck", "false");
  el.setAttribute("writingsuggestions", "false");
  el.setAttribute("autocomplete", plaintext ? "off" : (autoComplete ?? "current-password"));
}

export default function PasswordField({ className = "", autoComplete, ...props }: Props) {
  const [show, setShow] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const pointerToggled = useRef(false);
  const margin = className.includes("mt-1") ? "mt-1" : "";
  const inputClass = className.replace(/\bmt-1\b/g, "").replace(/\s+/g, " ").trim();

  function setRevealed(next: boolean) {
    const el = inputRef.current;
    if (el) {
      const start = el.selectionStart ?? el.value.length;
      const end = el.selectionEnd ?? el.value.length;
      el.type = next ? "text" : "password";
      applyRevealAttrs(el, next, autoComplete);
      el.focus({ preventScroll: true });
      try {
        el.setSelectionRange(start, end);
      } catch {
        /* password inputs on some browsers */
      }
    }
    setShow(next);
  }

  function onPointerDown(e: PointerEvent<HTMLButtonElement>) {
    e.preventDefault();
    pointerToggled.current = true;
    setRevealed(!show);
  }

  function onClick(e: MouseEvent<HTMLButtonElement>) {
    e.preventDefault();
    if (pointerToggled.current) {
      pointerToggled.current = false;
      return;
    }
    setRevealed(!show);
  }

  function onFocus(e: FocusEvent<HTMLInputElement>) {
    if (!show || !isAppleTouch()) return;
    const el = e.currentTarget;
    el.setAttribute("readonly", "readonly");
    requestAnimationFrame(() => {
      el.removeAttribute("readonly");
    });
  }

  return (
    <span className={`relative block ${margin}`}>
      <input
        {...props}
        ref={inputRef}
        type={show ? "text" : "password"}
        className={`pr-11 ${inputClass}`}
        autoComplete={show ? "off" : autoComplete}
        autoCorrect="off"
        autoCapitalize="none"
        spellCheck={false}
        inputMode="text"
        onFocus={onFocus}
        {...(show ? { writingSuggestions: "false" as const } : {})}
      />
      <button
        type="button"
        tabIndex={-1}
        className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-muted hover:text-ink"
        onPointerDown={onPointerDown}
        onClick={onClick}
        aria-label={show ? "Passwort verbergen" : "Passwort anzeigen"}
        title={show ? "Passwort verbergen" : "Passwort anzeigen"}
      >
        {show ? <IconEyeOff className="h-5 w-5" /> : <IconEye className="h-5 w-5" />}
      </button>
    </span>
  );
}
