package com.tempo.app.feature.sdui.ui

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.tempo.app.feature.sdui.model.CapturePromptWidget
import com.tempo.app.feature.sdui.model.CheckInScheduleWidget
import com.tempo.app.feature.sdui.model.ChoiceWidget
import com.tempo.app.feature.sdui.model.ConceptQuizWidget
import com.tempo.app.feature.sdui.model.DrillCardWidget
import com.tempo.app.feature.sdui.model.PathProgressWidget
import com.tempo.app.feature.sdui.model.QuestionWidget
import com.tempo.app.feature.sdui.model.UnknownWidget
import com.tempo.app.feature.sdui.model.Widget
import com.tempo.app.feature.sdui.model.WidgetAction
import com.tempo.app.feature.sdui.ui.widgets.CapturePromptCard
import com.tempo.app.feature.sdui.ui.widgets.CheckInScheduleCard
import com.tempo.app.feature.sdui.ui.widgets.ChoiceCard
import com.tempo.app.feature.sdui.ui.widgets.ConceptQuizCard
import com.tempo.app.feature.sdui.ui.widgets.DrillCard
import com.tempo.app.feature.sdui.ui.widgets.PathProgressCard
import com.tempo.app.feature.sdui.ui.widgets.QuestionCard
import com.tempo.app.feature.sdui.ui.widgets.UnknownWidgetCard

/** Single entry point for rendering any SDUI widget. Exhaustive over the sealed type. */
@Composable
fun WidgetRenderer(
    widget: Widget,
    onAction: (WidgetAction) -> Unit,
    modifier: Modifier = Modifier,
    onPathNodeClick: ((String) -> Unit)? = null,
    /** Drill card actions: open Live mode or Capture bound to this drill (buttons hidden when null). */
    onDrillLive: ((DrillCardWidget) -> Unit)? = null,
    onDrillUpload: ((DrillCardWidget) -> Unit)? = null,
    /** Only the SDUI debug screen shows unknown widgets; athletes never see error cards for them. */
    showUnknown: Boolean = false,
) {
    when (widget) {
        is PathProgressWidget -> PathProgressCard(widget, modifier, onPathNodeClick?.let { open -> { node -> open(node.nodeId) } })
        is DrillCardWidget -> DrillCard(widget, onAction, modifier,
            onStartLive = onDrillLive?.let { open -> { open(widget) } },
            onUploadClip = onDrillUpload?.let { open -> { open(widget) } })
        is ConceptQuizWidget -> ConceptQuizCard(widget, onAction, modifier)
        is CheckInScheduleWidget -> CheckInScheduleCard(widget, onAction, modifier)
        is QuestionWidget -> QuestionCard(widget, onAction, modifier)
        is ChoiceWidget -> ChoiceCard(widget, onAction, modifier)
        is CapturePromptWidget -> CapturePromptCard(widget, onAction, modifier)
        is UnknownWidget -> if (showUnknown) UnknownWidgetCard(widget, modifier)
    }
}
