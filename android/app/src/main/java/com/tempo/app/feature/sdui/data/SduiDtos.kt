package com.tempo.app.feature.sdui.data

import com.tempo.app.feature.sdui.model.WidgetAction
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** Raw widget feed. Widgets stay as JsonObject so each one is parsed in isolation. */
@Serializable
data class WidgetFeedDto(
    @SerialName("session_id") val sessionId: String? = null,
    val widgets: List<JsonObject> = emptyList(),
)

@Serializable
data class WidgetActionRequestDto(
    @SerialName("session_id") val sessionId: String,
    @SerialName("action_type") val actionType: String,
    @SerialName("widget_id") val widgetId: String,
    val payload: JsonObject,
)

fun WidgetAction.toRequest(sessionId: String): WidgetActionRequestDto {
    val (type, payload) = when (this) {
        is WidgetAction.QuizAnswered -> "QuizAnswered" to buildJsonObject {
            put("selected_index", selectedIndex)
            put("is_correct", isCorrect)
        }
        is WidgetAction.DrillCompleted -> "DrillCompleted" to buildJsonObject {
            put("reps_completed", repsCompleted)
        }
        is WidgetAction.SlotPicked -> "SlotPicked" to buildJsonObject {
            put("slot_id", slotId)
        }
        is WidgetAction.ChoiceSelected -> "ChoiceSelected" to buildJsonObject {
            put("option_ids", JsonArray(optionIds.map(::JsonPrimitive)))
            freeText?.let { put("free_text", it) }
        }
        is WidgetAction.CaptureRequested -> "CaptureRequested" to buildJsonObject {
            put("duration_s", durationS)
            put("camera_hint", cameraHint)
        }
    }
    return WidgetActionRequestDto(sessionId, type, widgetId, payload)
}
