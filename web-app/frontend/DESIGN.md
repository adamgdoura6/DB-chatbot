# Frontend design note

This note records the idea behind the web-app page, the decisions made so far, and the direction it is
taking. Update it every time a design preference is stated or changed.

## The idea

One page from which you operate the whole DB-chatbot: choose the database to connect to, run the audit,
and talk to the database. The page itself stays **extremely minimal, even secretive**: on load it is just
blank. Nothing announces that it is a chatbot. It only reveals itself when you start typing.

## Principles

- **Blank by default.** No title, logo, borders, boxes, placeholder text, buttons or visible cursor until
  the user acts.
- **Reveal on use.** Things appear only when they are needed (the text when typing, the cursor once there
  is text).
- **Familiar placement, invisible chrome.** Elements sit where people expect them in a chatbot, without
  the visual container that normally marks them.
- **Warm and quiet.** Everything in soft beige and warm grey-brown tones; nothing in the browser's default
  colours (no blue).

## Current decisions

| element | decision |
|---|---|
| background | beige leaning to white, `#fbf9f4` |
| text | warm grey-brown `#5f5a50`, Georgia (serif), 16px, weight 300, line height 1.6 |
| input position | where chatbots put their message box: bottom centre, 40px above the bottom edge; no box, no border, no placeholder |
| line length | short: 380px column (about 55 characters per line); on phones, full width minus 16px each side |
| wrapping | text wraps to a new line, never scrolls sideways; long words break |
| height | grows upward with the text up to 3 lines, then scrolls inside; scrollbar hidden |
| cursor | hidden while empty; appears once there is text, in soft tan `#b3a58c` |
| selection | sand highlight `#ebe3d3` with the normal text colour, instead of browser blue |
| focus | the input always has focus; clicks or keys anywhere bring it back (text in the conversation can still be selected and copied) |
| sending | Enter sends, Shift+Enter is a new line; no send button; one message at a time |
| your message | appears above the input, rising and fading into place, in the lighter tan `#b3a58c` |
| messages | no bubbles, avatars or names; same 380px column as the input, left-aligned; 28px between exchanges, 10px between question and reply |
| thinking | a single small tan dot breathing where the reply will appear; no "thinking…" text |
| reply | in the main text colour, appears word by word, each word fading in |
| history | the whole conversation stays; it fades out toward the top (mask over the top 45%); scrollable, scrollbar hidden |
| SQL, tables, caveats | under the reply in 12px at 18% opacity, readable on hover or tap; SQL in monospace |
| connecting a database | hidden command: type `/connect` (Supabase only for now). The page asks in the same chat style: connection string, then the password if it is missing, then "yes or no" for an owner login. Esc stops |
| secrets | the connection string is shown with `••••` in place of its password; the password is typed into a masked field in the same place and style, and shown as `••••••••` |
| page's own replies | replies written by the page (e.g. during `/connect`) look exactly like the agent's: dot, words fading in, details on hover |

## Direction

- **Stack:** Next.js (this folder: `app/page.tsx`, `app/globals.css`) and FastAPI (`../backend/`). The
  look was first prototyped as a single HTML page, then carried over unchanged.
- **Chat:** with a database connected, each message runs the real agent (Claude Code headless at the
  repository root, so the same chat answers questions and runs the audit). Without one, `/api/chat`
  streams three canned replies in rotation (a confirmed answer, one resting on a guess, a schema answer).
  The agent is told to answer in plain prose and to put SQL, tables and caveats in the hidden details.
- **Errors** look like everything else: the reply is "…", and the reason is in the hidden details.
- **Postponed:** history of past conversations (suggested: hidden at the left edge, appearing on hover;
  Esc twice or `/new` for a new conversation).
- **Connecting:** `/connect` for Supabase is in place; other providers (AWS RDS, any Postgres) can use the
  same conversation later. The password goes to the backend's own code, never to the agent.

## Preference log

- Fully blank page, beige leaning to white; text appears only when typing.
- Text goes where chatbots have their textbox, but with no box at all.
- Wrap to new lines instead of scrolling left; after 3 lines the user scrolls; text a bit smaller (18px → 16px).
- Line length shortened three times (680px → 600px → 480px → 380px): the user prefers a short line.
- Cursor shown only after the user starts writing, coloured to match the page.
- No blue selection highlight; use the page's own tones.
- Conversation: accepted the suggested design as a whole (Enter to send, no bubbles, lighter tone for
  your message, breathing dot, word-by-word reply, history fading at the top, details on hover).
- Past-conversation history: postponed. Moved to Next.js + FastAPI with the look unchanged.
- Connecting to Supabase from the app: done as the hidden `/connect` conversation.
