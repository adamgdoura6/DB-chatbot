"use client";

import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type RefObject } from "react";

type Details = { sql: string | null; tables: string[]; note: string | null };

type Exchange = {
  id: number;
  question: string;
  words: string[];
  details?: Details;
  done: boolean;
  open: boolean;
};

// One JSON object per line from POST /api/chat (see web-app/backend/app/routers/chat.py).
type Part =
  | { type: "conversation"; id: string }
  | { type: "text"; text: string }
  | ({ type: "details" } & Details)
  | { type: "error"; text: string };

// The /connect conversation: which answer the input is waiting for.
type Step = "url" | "password" | "confirm";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const note = (text: string): Details => ({ sql: null, tables: [], note: text });

// Show a connection string without its password.
const maskUrl = (url: string) => url.replace(/(:\/\/[^:/@]*:)([^@]+)(@)/, (_, a, p, b) =>
  a + (p === "[YOUR-PASSWORD]" ? p : "••••") + b);

export default function Page() {
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState<Step | null>(null);
  const conversation = useRef<string | null>(null);
  const connectUrl = useRef("");
  const connectPassword = useRef<string | null>(null);
  const nextId = useRef(0);
  const follow = useRef(true);
  const say = useRef<HTMLTextAreaElement | HTMLInputElement>(null);
  const log = useRef<HTMLDivElement>(null);

  // Grow with the text up to three lines (max-height); past that it scrolls.
  useLayoutEffect(() => {
    const el = say.current;
    if (!(el instanceof HTMLTextAreaElement)) return;
    el.style.height = "auto";
    el.style.height = el.scrollHeight - 28 + "px";
  }, [draft, step]);

  // Stay at the newest message unless the reader has scrolled up.
  useLayoutEffect(() => {
    const el = log.current!;
    if (follow.current) el.scrollTop = el.scrollHeight;
  }, [exchanges]);

  // The input is swapped for a password field and back; keep the focus.
  useEffect(() => { say.current?.focus(); }, [step]);

  // Keep the input focused, but let text in the conversation be selected and copied.
  useEffect(() => {
    const focus = () => { if (!getSelection()?.toString()) say.current?.focus(); };
    const key = (e: globalThis.KeyboardEvent) => { if (!e.ctrlKey && !e.metaKey) say.current?.focus(); };
    document.addEventListener("mouseup", focus);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mouseup", focus);
      document.removeEventListener("keydown", key);
    };
  }, []);

  function update(id: number, change: (x: Exchange) => Partial<Exchange>) {
    setExchanges((xs) => xs.map((x) => (x.id === id ? { ...x, ...change(x) } : x)));
  }

  function add(question: string): number {
    const id = nextId.current++;
    follow.current = true;
    setExchanges((xs) => [...xs, { id, question, words: [], done: false, open: false }]);
    return id;
  }

  // A reply written by the page itself, shown the same way as the agent's.
  async function speak(id: number, text: string, details?: Details) {
    await wait(500);
    const words = text.split(" ");
    for (const [i, w] of words.entries()) {
      update(id, (x) => ({ words: [...x.words, w + (i < words.length - 1 ? " " : "")] }));
      await wait(40);
    }
    update(id, () => ({ details, done: true }));
  }

  // Enter sends, Shift+Enter starts a new line, Esc leaves /connect.
  function onKeyDown(e: KeyboardEvent<HTMLElement>) {
    if (e.key === "Escape" && step && !busy) {
      endConnect();
      return;
    }
    if (e.key !== "Enter" || e.shiftKey || e.nativeEvent.isComposing) return;
    e.preventDefault();
    const text = step === "password" ? draft : draft.trim();
    if (!text || busy) return;
    setDraft("");
    setBusy(true);
    const done = step ? answerConnect(text) : text.startsWith("/") ? command(text) : ask(text);
    done.finally(() => setBusy(false));
  }

  async function command(text: string) {
    const [name, arg] = text.slice(1).toLowerCase().split(/\s+/);
    const id = add(text);
    if (name !== "connect") return speak(id, "I only know /connect for now.");
    if (arg && arg !== "supabase") return speak(id, "Only Supabase for now. Type /connect.");
    setStep("url");
    await speak(id,
      "Paste your Supabase connection string. In the Supabase dashboard: Connect, then Session pooler. " +
      "Use a read-only login, not postgres.",
      note("It looks like postgresql://ai_reader.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres. " +
        "To create the read-only login: audit-your-database/providers/supabase.md. Esc to stop."));
  }

  function endConnect() {
    setStep(null);
    connectUrl.current = "";
    connectPassword.current = null;
  }

  async function answerConnect(text: string) {
    if (step === "url") {
      connectUrl.current = text;
      connectPassword.current = null;
      return tryConnect(add(maskUrl(text)), false);
    }
    if (step === "password") {
      connectPassword.current = text;
      return tryConnect(add("••••••••"), false);
    }
    const id = add(text);
    if (/^y(es)?$/i.test(text)) return tryConnect(id, true);
    endConnect();
    return speak(id, "Not connected.");
  }

  // The backend checks the connection with the same checks as connect.py and says what it needs next.
  async function tryConnect(id: number, force: boolean) {
    let r;
    try {
      const res = await fetch("/api/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: "supabase", url: connectUrl.current, password: connectPassword.current, force,
        }),
      });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      r = await res.json();
    } catch (err) {
      endConnect();
      return speak(id, "…", note(String(err)));
    }

    if (r.status === "need_password") {
      setStep("password");
      return speak(id, "And the password.");
    }
    if (r.status === "invalid") {
      setStep("url");
      return speak(id, "That isn't a connection string. It starts with postgresql://");
    }
    if (r.status === "risky") {
      setStep("confirm");
      return speak(id,
        "That is an owner login: it can change your data, and on Supabase it skips row level security. " +
        "Connect anyway? yes or no",
        note("A read-only login is safer: audit-your-database/providers/readonly-role.sql"));
    }
    if (r.status === "failed") {
      endConnect();
      setStep("url");
      return speak(id, `Couldn't connect. ${r.hint ?? "Check the connection string."} Paste it again, or Esc.`,
        note(r.error));
    }
    if (r.status === "connected") {
      endConnect();
      conversation.current = null; // a new database starts a new conversation with the agent
      const login = r.login.split(".")[0];
      const access = r.problems.length
        ? `Careful: this login ${r.problems.join(", ")}.`
        : "The login is read-only.";
      const tables = r.readable_tables === 0
        ? "It can't read any tables yet; grant it SELECT first."
        : `It can read ${r.readable_tables} tables. Say "audit my database" when you're ready.`;
      return speak(id, `Connected to ${r.provider} as ${login}. ${access} ${tables}`,
        note(`database ${r.db} · ${r.version}`));
    }
    endConnect();
    return speak(id, "…", note(JSON.stringify(r)));
  }

  async function ask(text: string) {
    const id = add(text);
    const apply = (part: Part) => {
      if (part.type === "conversation") conversation.current = part.id;
      else if (part.type === "text") update(id, (x) => ({ words: [...x.words, part.text] }));
      else if (part.type === "details") update(id, () => ({ details: part }));
      // Errors stay as quiet as the rest: "…" as the reply, the reason in the hidden details.
      else if (part.type === "error") update(id, () => ({ details: note(part.text) }));
    };

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, conversation: conversation.current }),
      });
      if (!res.ok || !res.body) throw new Error(`${res.status} ${res.statusText}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop()!;
        for (const line of lines) if (line) apply(JSON.parse(line));
      }
    } catch (err) {
      apply({ type: "error", text: String(err) });
    }
    update(id, () => ({ done: true }));
  }

  function onScroll() {
    const el = log.current!;
    follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
  }

  const inputProps = {
    className: "say",
    placeholder: " ",
    autoComplete: "off",
    spellCheck: false,
    value: draft,
    onChange: (e: { target: { value: string } }) => setDraft(e.target.value),
    onKeyDown,
  };

  return (
    <>
      <div className="log" ref={log} onScroll={onScroll} aria-live="polite">
        {exchanges.map((x) => (
          <div key={x.id}>
            <div className="msg you">{x.question}</div>
            <div
              className={"msg reply" + (x.open ? " open" : "")}
              // Tapping a reply reveals its details (hover does it with a mouse).
              onClick={() => { if (!getSelection()?.toString()) update(x.id, (e) => ({ open: !e.open })); }}
            >
              <div>
                {x.words.map((w, i) => <span className="w" key={i}>{w}</span>)}
                {!x.done && x.words.length === 0 && <span className="dot" />}
                {x.done && x.words.length === 0 && "…"}
              </div>
              {x.details && (x.details.note || x.details.sql || x.details.tables.length > 0) && (
                <div className="details">
                  {x.details.note}
                  {x.details.sql && <code>{x.details.sql}</code>}
                  {x.details.tables.join(" · ")}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
      {step === "password" ? (
        <input {...inputProps} ref={say as RefObject<HTMLInputElement>} type="password" aria-label="Password" />
      ) : (
        <textarea {...inputProps} ref={say as RefObject<HTMLTextAreaElement>} rows={1} aria-label="Ask" />
      )}
    </>
  );
}
