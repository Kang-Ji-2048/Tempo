---
trigger: always_on
---

## Current state (read the code before changing anything)
Done: scaffold (Hilt, nav, theme, MockTempoApi, SessionRepository, NetworkResult),
SDUI engine in feature/sdui (Widget sealed hierarchy, WidgetParser, WidgetRenderer,
WidgetAction, MockSduiApi). Follow the existing conventions: sealed NetworkResult,
repository interface + Mock + Impl, one ViewModel per screen, no logic in composables.
Reuse WidgetRenderer for any widget; never create a second widget system.

## Product experience
Tempo is a coach, not a form and not a chatbot. Principles:
- One thing at a time: each session ends with ONE primary fix, never a list of eight.
- The coach talks like a person on court: warm, direct, level-calibrated, brief.
  Beginners get physical analogies, advanced players get kinetic terminology.
- Everything the coach says about the athlete's body must come from measured data
  passed to it. Never invent numbers, never claim an action happened that didn't
  (no "court booked", no fake heart-rate data).
- Every coach reply can end in an action: a drill, a path update, or a check-in.
- The UI should feel alive: animated transitions, typing indicator, haptics, no spinners
  without friendly copy.

## Architecture of the coach layer
- In-app coach chat = our own Gemini call behind POST /api/v1/coach/converse.
  It returns {reply_text, widgets[], thea_brief?, audio_url?}. Widgets use the
  existing SDUI contract and render inline in the chat via WidgetRenderer.
- Thea is a separate WhatsApp assistant with NO API. The app hands off to her
  with a wa.me deep link carrying a pre-filled "brief" message. The app never
  sees her replies. THEA_NUMBER comes from BuildConfig (local.properties).
- Widget names are fixed: PathProgressWidget, DrillCardWidget, ConceptQuizWidget,
  CheckInScheduleWidget, QuestionWidget, ChoiceWidget, CapturePromptWidget.