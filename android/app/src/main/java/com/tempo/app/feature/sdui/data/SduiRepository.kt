package com.tempo.app.feature.sdui.data

import com.tempo.app.feature.sdui.model.Widget
import com.tempo.app.feature.sdui.model.WidgetAction
import com.tempo.app.network.models.NetworkResult

interface SduiRepository {
    suspend fun getFeed(sessionId: String): NetworkResult<List<Widget>>

    /** Posts an action; the server responds with the full replacement widget list. */
    suspend fun postAction(sessionId: String, action: WidgetAction): NetworkResult<List<Widget>>
}
