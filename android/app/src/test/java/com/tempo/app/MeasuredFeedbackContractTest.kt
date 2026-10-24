package com.tempo.app

import com.tempo.app.feature.correction.model.KineticPhaseUiModel
import com.tempo.app.feature.sdui.data.WidgetParser
import com.tempo.app.feature.sdui.model.DrillCardWidget
import kotlinx.serialization.json.Json
import org.junit.Assert.*
import org.junit.Test

class MeasuredFeedbackContractTest {
    @Test fun canonicalDrillDecodesAsADrill() {
        val widget = WidgetParser().parseOne(Json.parseToJsonElement(
            """{"widget_type":"DrillCardWidget","id":"session-drill","title":"Practice focus","instruction":"Comfortable reach","target_reps":10,"focus_cue":"PASS"}"""))
        assertTrue(widget is DrillCardWidget)
        assertEquals(10, (widget as DrillCardWidget).targetReps)
    }

    @Test fun measuredTimestampDoesNotRequireAnInventedScore() {
        val phase = Json.decodeFromString<KineticPhaseUiModel>(
            """{"phase_name":"Peak reach (contact proxy)","timestamp_ms":1234,"observation":"Measured highest reach"}""")
        assertNull(phase.formAccuracyScore)
        assertEquals(1234L, phase.timestampMs)
    }
}
