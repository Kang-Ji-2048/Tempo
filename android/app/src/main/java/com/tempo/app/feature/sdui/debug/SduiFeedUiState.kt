package com.tempo.app.feature.sdui.debug

import com.tempo.app.feature.sdui.model.UnknownWidget
import com.tempo.app.feature.sdui.model.Widget

/** A widget paired with a list key that is guaranteed unique within the feed. */
data class SduiItem(val key: String, val widget: Widget)

data class SduiFeedUiState(
    val items: List<SduiItem> = emptyList(),
    val isLoading: Boolean = false,
    val isPosting: Boolean = false,
    val error: String? = null,
) {
    val knownCount: Int get() = items.count { it.widget !is UnknownWidget }
    val unknownCount: Int get() = items.size - knownCount
}

sealed interface SduiEvent {
    data class Message(val text: String) : SduiEvent
    data object NavigateToCapture : SduiEvent
}

/** Lazy lists crash on duplicate keys, so de-duplicate defensively. */
fun List<Widget>.toSduiItems(): List<SduiItem> {
    val seen = mutableMapOf<String, Int>()
    return map { widget ->
        val count = seen.merge(widget.key, 1, Int::plus)!!
        SduiItem(if (count == 1) widget.key else "${widget.key}#$count", widget)
    }
}
