package com.tempo.app.feature.sdui.data

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path

/**
 * SDUI endpoints.
 * Backend must expose these (not yet implemented server-side):
 *  - GET  /api/v1/sdui/feed/{session_id}  -> WidgetFeedDto
 *  - POST /api/v1/sdui/actions            -> WidgetFeedDto (full replacement list)
 */
interface SduiApi {

    @GET("api/v1/sdui/feed/{sessionId}")
    suspend fun getFeed(@Path("sessionId") sessionId: String): WidgetFeedDto

    @POST("api/v1/sdui/actions")
    suspend fun postAction(@Body request: WidgetActionRequestDto): WidgetFeedDto
}
