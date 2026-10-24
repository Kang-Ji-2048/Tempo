package com.tempo.app.feature.sdui.model

/** User intents emitted by SDUI widgets. Consumed by the screen's ViewModel. */
sealed interface WidgetAction {
    val widgetId: String

    data class QuizAnswered(
        override val widgetId: String,
        val selectedIndex: Int,
        val isCorrect: Boolean,
    ) : WidgetAction

    data class DrillCompleted(
        override val widgetId: String,
        val repsCompleted: Int,
    ) : WidgetAction

    data class SlotPicked(
        override val widgetId: String,
        val slotId: String,
    ) : WidgetAction

    data class ChoiceSelected(
        override val widgetId: String,
        val optionIds: List<String> = emptyList(),
        val freeText: String? = null,
    ) : WidgetAction

    data class CaptureRequested(
        override val widgetId: String,
        val durationS: Int,
        val cameraHint: String,
    ) : WidgetAction
}
