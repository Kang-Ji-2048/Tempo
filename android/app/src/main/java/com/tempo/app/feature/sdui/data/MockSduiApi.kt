package com.tempo.app.feature.sdui.data

import kotlinx.coroutines.delay
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.contentOrNull
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Offline SDUI backend. Seeds every session from [MockWidgetFeed] and applies
 * actions the way the real server would, returning the full replacement list.
 */
@Singleton
class MockSduiApi @Inject constructor() : SduiApi {

    private val mutex = Mutex()
    private val feeds = mutableMapOf<String, MutableList<JsonObject>>()

    override suspend fun getFeed(sessionId: String): WidgetFeedDto = mutex.withLock {
        delay(250)
        val seeded = seed()
        feeds[sessionId] = seeded
        WidgetFeedDto(sessionId, seeded.toList())
    }

    override suspend fun postAction(request: WidgetActionRequestDto): WidgetFeedDto = mutex.withLock {
        delay(350)
        val feed = feeds.getOrPut(request.sessionId) { seed() }
        val payload = request.payload
        when (request.actionType) {
            "QuizAnswered" -> feed.update(request.widgetId) {
                it.with("answered_index", payload["selected_index"] ?: JsonPrimitive(0))
            }
            "DrillCompleted" -> {
                feed.removeAll { it.str("id") == request.widgetId }
                feed.replaceAll { if (it.str("widget_type") == "PathProgressWidget") advancePath(it) else it }
            }
            "SlotPicked" -> feed.update(request.widgetId) {
                it.with("selected_slot_id", payload["slot_id"] ?: JsonPrimitive(""))
            }
            "ChoiceSelected" -> feed.update(request.widgetId) { widget ->
                when (widget.str("widget_type")) {
                    "QuestionWidget" -> widget.with("submitted_answer", payload["free_text"] ?: JsonPrimitive(""))
                    else -> widget.with("selected_option_ids", payload["option_ids"] ?: JsonArray(emptyList()))
                }
            }
            // CaptureRequested: navigation is handled client-side; feed unchanged.
        }
        WidgetFeedDto(request.sessionId, feed.toList())
    }

    private fun seed(): MutableList<JsonObject> =
        SduiJson.parseToJsonElement(MockWidgetFeed.JSON).jsonObject["widgets"]!!
            .jsonArray.mapNotNull { it as? JsonObject }.toMutableList()

    /** Completes the active node, unlocks the next one and bumps the streak. */
    private fun advancePath(path: JsonObject): JsonObject {
        val activeId = path.str("active_node_id")
        val nodes = path["nodes"]?.jsonArray?.map { it.jsonObject } ?: return path
        val activeIndex = nodes.indexOfFirst { it.str("node_id") == activeId }
        if (activeIndex < 0) return path
        val nextIndex = activeIndex + 1
        val updated = nodes.mapIndexed { i, node ->
            when (i) {
                activeIndex -> node.with("status", JsonPrimitive("COMPLETED"))
                nextIndex -> node.with("status", JsonPrimitive("ACTIVE"))
                else -> node
            }
        }
        val streak = path["current_streak"]?.jsonPrimitive?.intOrNull ?: 0
        val nextActive = updated.getOrNull(nextIndex)?.str("node_id") ?: ""
        return path
            .with("nodes", JsonArray(updated))
            .with("active_node_id", JsonPrimitive(nextActive))
            .with("current_streak", JsonPrimitive(streak + 1))
    }

    private fun MutableList<JsonObject>.update(widgetId: String, transform: (JsonObject) -> JsonObject) {
        replaceAll { if (it.str("id") == widgetId || it.str("question") == widgetId) transform(it) else it }
    }

    private fun JsonObject.with(key: String, value: JsonElement): JsonObject =
        JsonObject(this + (key to value))

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.contentOrNull
}
