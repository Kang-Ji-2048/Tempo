package com.tempo.app.feature.sdui.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

/**
 * Server-Driven UI widget contract.
 *
 * The server sends a JSON list where every element carries a `widget_type`
 * discriminator. Known types decode into the data classes below; anything else
 * (or anything malformed) decodes into [UnknownWidget] so the UI never crashes.
 *
 * NOTE: [Widget] is intentionally NOT annotated with @Serializable. That makes it
 * open-polymorphic, so the SerializersModule default deserializer applies
 * (see [com.tempo.app.feature.sdui.data.WidgetParser]).
 */
sealed interface Widget {
    /** Stable identity used for list keys and action targeting. Not serialized. */
    val key: String
}

@Serializable
@SerialName("PathProgressWidget")
data class PathProgressWidget(
    @SerialName("current_streak") val currentStreak: Int = 0,
    @SerialName("active_node_id") val activeNodeId: String = "",
    val nodes: List<PathNode> = emptyList(),
    val title: String = "Your Path",
) : Widget {
    override val key: String get() = "path"

    fun stateOf(node: PathNode): PathNodeState = when {
        node.nodeId == activeNodeId -> PathNodeState.ACTIVE
        node.status.equals("COMPLETED", ignoreCase = true) ||
            node.status.equals("DONE", ignoreCase = true) -> PathNodeState.DONE
        node.status.equals("ACTIVE", ignoreCase = true) -> PathNodeState.ACTIVE
        else -> PathNodeState.LOCKED
    }
}

@Serializable
data class PathNode(
    @SerialName("node_id") val nodeId: String,
    val title: String,
    val status: String = "LOCKED",
    @SerialName("xp_reward") val xpReward: Int = 50,
)

enum class PathNodeState { LOCKED, ACTIVE, DONE }

@Serializable
@SerialName("DrillCardWidget")
data class DrillCardWidget(
    val id: String,
    val title: String,
    val instruction: String,
    @SerialName("target_reps") val targetReps: Int,
    @SerialName("focus_cue") val focusCue: String,
) : Widget {
    override val key: String get() = "drill_$id"
}

@Serializable
@SerialName("ConceptQuizWidget")
data class ConceptQuizWidget(
    val question: String,
    val options: List<String>,
    @SerialName("correct_index") val correctIndex: Int,
    val explanation: String,
    val id: String = "",
    /** Set by the server once the athlete has answered, so state survives feed refreshes. */
    @SerialName("answered_index") val answeredIndex: Int? = null,
) : Widget {
    override val key: String get() = "quiz_" + id.ifEmpty { question.hashCode().toString() }
    val actionId: String get() = id.ifEmpty { question }
}

@Serializable
@SerialName("CheckInScheduleWidget")
data class CheckInScheduleWidget(
    val id: String,
    val title: String,
    val subtitle: String = "",
    val slots: List<ScheduleSlot> = emptyList(),
    @SerialName("selected_slot_id") val selectedSlotId: String? = null,
    @SerialName("reminder_note") val reminderNote: String? = null,
) : Widget {
    override val key: String get() = "schedule_$id"
}

@Serializable
data class ScheduleSlot(
    @SerialName("slot_id") val slotId: String,
    @SerialName("day_label") val dayLabel: String,
    @SerialName("time_label") val timeLabel: String,
    val recommended: Boolean = false,
)

@Serializable
@SerialName("QuestionWidget")
data class QuestionWidget(
    val id: String,
    val prompt: String,
    val hint: String = "Type your answer…",
    @SerialName("quick_replies") val quickReplies: List<String> = emptyList(),
    @SerialName("submitted_answer") val submittedAnswer: String? = null,
) : Widget {
    override val key: String get() = "question_$id"
}

@Serializable
@SerialName("ChoiceWidget")
data class ChoiceWidget(
    val id: String,
    val title: String,
    val subtitle: String = "",
    val options: List<ChoiceOption> = emptyList(),
    @SerialName("multi_select") val multiSelect: Boolean = false,
    @SerialName("selected_option_ids") val selectedOptionIds: List<String> = emptyList(),
) : Widget {
    override val key: String get() = "choice_$id"
}

@Serializable
data class ChoiceOption(
    val id: String,
    val label: String,
    val description: String? = null,
    val emoji: String? = null,
)

@Serializable
@SerialName("CapturePromptWidget")
data class CapturePromptWidget(
    val title: String,
    val instruction: String,
    @SerialName("camera_hint") val cameraHint: String,
    @SerialName("duration_s") val durationS: Int,
    val id: String = "capture",
) : Widget {
    override val key: String get() = "capture_$id"
}

/** Fallback for unrecognised, missing or malformed widget types. Never rendered as an error. */
data class UnknownWidget(
    val widgetType: String,
    val raw: JsonObject = JsonObject(emptyMap()),
) : Widget {
    override val key: String get() = "unknown_${widgetType}_${raw.hashCode()}"
}
