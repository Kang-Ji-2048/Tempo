package com.tempo.app.feature.sdui.data

/**
 * Hard-coded SDUI feed covering every widget type, plus deliberately hostile
 * entries (unknown type, missing discriminator, malformed known type) to prove
 * the renderer never crashes.
 */
object MockWidgetFeed {

    const val JSON: String = """
{
  "session_id": "debug",
  "widgets": [
    {
      "widget_type": "PathProgressWidget",
      "title": "Overhead Clear Mastery",
      "current_streak": 5,
      "active_node_id": "node_pronation_03",
      "nodes": [
        { "node_id": "node_grip_01", "title": "Panhandle Grip", "status": "COMPLETED", "xp_reward": 40 },
        { "node_id": "node_turn_02", "title": "Side-On Turn", "status": "COMPLETED", "xp_reward": 50 },
        { "node_id": "node_pronation_03", "title": "Forearm Pronation", "status": "ACTIVE", "xp_reward": 60 },
        { "node_id": "node_reach_04", "title": "Full Elbow Reach", "status": "LOCKED", "xp_reward": 60 },
        { "node_id": "node_jump_05", "title": "Jump Smash Load", "status": "LOCKED", "xp_reward": 80 },
        { "node_id": "node_recover_06", "title": "Split-Step Recovery", "status": "LOCKED", "xp_reward": 100 }
      ]
    },
    {
      "widget_type": "CapturePromptWidget",
      "id": "capture_clear_set",
      "title": "Record 10 overhead clears",
      "instruction": "Film one set from the side so we can measure elbow extension at contact.",
      "camera_hint": "Side-on, 3 m back, full body in frame",
      "duration_s": 45
    },
    {
      "widget_type": "DrillCardWidget",
      "id": "drill_pronation_wall_30s",
      "title": "Rapid Pronation Wall Drill",
      "instruction": "Stand 1 m from a wall. Snap the forearm through contact against a taped target while keeping the elbow high.",
      "target_reps": 15,
      "focus_cue": "Elbow high, snap late."
    },
    {
      "widget_type": "ConceptQuizWidget",
      "id": "quiz_hip_rotation",
      "question": "Why does early hip rotation matter before racket acceleration?",
      "options": [
        "It transfers ground force through the core into the shoulder.",
        "It lowers the shuttle trajectory.",
        "It reduces cardiovascular demand.",
        "It prevents knee flexion."
      ],
      "correct_index": 0,
      "explanation": "Hip rotation starts the kinetic chain, letting ground reaction force multiply through the trunk into the arm."
    },
    {
      "widget_type": "CheckInScheduleWidget",
      "id": "checkin_next",
      "title": "Lock in your next session",
      "subtitle": "Consistency beats intensity. Pick a slot and we'll prime you beforehand.",
      "reminder_note": "We'll nudge you on WhatsApp 30 min before.",
      "slots": [
        { "slot_id": "mon_18", "day_label": "MON", "time_label": "18:00" },
        { "slot_id": "wed_07", "day_label": "WED", "time_label": "07:30", "recommended": true },
        { "slot_id": "thu_19", "day_label": "THU", "time_label": "19:00" },
        { "slot_id": "sat_10", "day_label": "SAT", "time_label": "10:00" }
      ]
    },
    {
      "widget_type": "QuestionWidget",
      "id": "q_shoulder_feel",
      "prompt": "How did your shoulder feel on the last few clears?",
      "hint": "Tell your coach…",
      "quick_replies": ["Loose & fast", "A bit tight", "Sore — easing off"]
    },
    {
      "widget_type": "ChoiceWidget",
      "id": "choice_focus",
      "title": "What should we focus on next week?",
      "subtitle": "Pick up to two.",
      "multi_select": true,
      "options": [
        { "id": "power", "label": "Power", "description": "Jump smash load & snap", "emoji": "⚡" },
        { "id": "footwork", "label": "Footwork", "description": "Rear-court recovery speed", "emoji": "👟" },
        { "id": "consistency", "label": "Consistency", "description": "Clear depth under fatigue", "emoji": "🎯" }
      ]
    },
    { "widget_type": "Foo", "anything": "goes" },
    { "no_discriminator": true },
    { "widget_type": "DrillCardWidget", "id": "broken_drill_missing_fields" }
  ]
}
"""
}
