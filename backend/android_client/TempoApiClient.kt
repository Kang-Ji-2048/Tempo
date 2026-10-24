/**
 * TempoApiClient.kt - Android Jetpack Compose Integration (Sumanth & Yue)
 * Drop-in Retrofit + OkHttp Server-Sent Events (SSE) client that connects the Android app to:
 * 1. One-tap Apple Watch pairing (`POST /pipeline/pair-watch`) + real-time watch telemetry stream (`GET /pipeline/live-stream`)
 * 2. Video + Apple Watch + GPS stroke analysis (`POST /pipeline/analyze-stroke`)
 *    -> MongoDB Atlas `$vectorSearch` (Roger Federer, Novak Djokovic, Carlos Alcaraz, Serena Williams)
 *    -> MongoDB `2dsphere` Geospatial London Partner Matching (`$geoNear`)
 *    -> MongoDB Time-Series (`watch_telemetry_ts`) & `$facet` + `$bucket` Longitudinal Fatigue Analytics
 * 3. Human-in-the-loop Saint AI court booking approval (`POST /pipeline/approve-saint-action`)
 */
package com.tempo.coach.network

import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONObject
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query
import java.io.BufferedReader
import java.io.File
import java.io.InputStreamReader
import java.util.concurrent.TimeUnit

// --- Data Models matching FastAPI & MongoDB Atlas Unified JSON ---

data class PairWatchRequest(
    val user_name: String = "user_1",
    val android_device_id: String = "android_compose_app"
)

data class PairWatchResponse(
    val pairing_code: String,
    val user_name: String,
    val status: String,
    val companion_url: String,
    val shortcut_webhook_url: String
)

data class AppleWatchBiometrics(
    val heart_rate_bpm: Double,
    val peak_heart_rate_bpm: Double,
    val resting_heart_rate_bpm: Double,
    val hrv_sdnn_ms: Double,
    val active_calories_kcal: Double,
    val workout_duration_min: Double,
    val wrist_acceleration_peak_mps: Double,
    val fatigue_index: Double,
    val fatigue_state: String,
    val source_format: String? = null
)

data class ProComparison(
    val matched_pro: String,
    val country: String,
    val sport: String,
    val stroke_type: String,
    val pro_right_elbow_contact_deg: Double,
    val similarity_score: Double,
    val search_method: String,
    val biomechanical_notes: String
)

data class TrainingPartnerMatch(
    val player_id: String,
    val name: String,
    val city: String,
    val preferred_venue: String,
    val distance_km: Double?,
    val compatibility_score: Double,
    val hybrid_rank_score: Double?,
    val search_method: String?,
    val availability: String
)

data class SaintAgentJob(
    val plain_english_instruction: String,
    val proactive_training_notification: String,
    val requires_human_approval: Boolean,
    val approval_action_summary: String,
    val matched_partner: String?,
    val venue: String?,
    val proposed_slot: String?
)

data class HrZoneBucket(
    val hr_zone: String,
    val sessions_count: Int,
    val avg_heart_rate_bpm: Double,
    val avg_elbow_contact_deg: Double,
    val avg_contact_height_norm: Double,
    val pass_count: Int
)

data class LongitudinalFatigueAnalytics(
    val user_name: String,
    val aggregation_pipeline: String,
    val fatigue_induced_elbow_drop_deg: Double,
    val insight: String,
    val hr_zone_buckets: List<HrZoneBucket>
)

data class StrokeAnalysisResponse(
    val session_id: String,
    val user_name: String,
    val verification_status: String, // "PASS" or "FAIL"
    val biomechanical_diagnosis: String,
    val live_drill_prescription: String,
    val saint_agent_job: SaintAgentJob,
    val apple_watch_biometrics: AppleWatchBiometrics,
    val pro_comparison: ProComparison,
    val training_partner_match: TrainingPartnerMatch,
    val longitudinal_fatigue_analytics: LongitudinalFatigueAnalytics,
    val saint_approval_status: String
)

data class ApproveSaintRequest(
    val session_id: String,
    val user_name: String = "user_1",
    val approved: Boolean = true,
    val notes: String = "Approved via Android Jetpack Compose app"
)

data class ApproveSaintResponse(
    val status: String,
    val session_id: String,
    val approved_by: String,
    val human_in_the_loop_verified: Boolean,
    val saint_approval_status: String
)

// --- Retrofit API Interface ---

interface TempoBackendService {

    @POST("/pipeline/pair-watch")
    suspend fun pairAppleWatch(@Body request: PairWatchRequest = PairWatchRequest()): PairWatchResponse

    @Multipart
    @POST("/pipeline/analyze-stroke")
    suspend fun analyzeStroke(
        @Part video: MultipartBody.Part?,
        @Part("user_name") userName: RequestBody,
        @Part("user_lon") userLon: RequestBody,
        @Part("user_lat") userLat: RequestBody
    ): StrokeAnalysisResponse

    @POST("/pipeline/approve-saint-action")
    suspend fun approveSaintAction(@Body request: ApproveSaintRequest): ApproveSaintResponse

    @GET("/pipeline/analytics/{userName}")
    suspend fun getFatigueAnalytics(@Path("userName") userName: String = "user_1"): LongitudinalFatigueAnalytics

    @GET("/pipeline/latest-apple-watch")
    suspend fun getLatestWatchMetrics(@Query("user_name") userName: String = "user_1"): Map<String, Any>
}

// --- Client Helper with Live Apple Watch SSE Stream ---

class TempoRepository(private val baseUrl: String = "http://192.168.68.106:8000") {

    private val okHttpClient = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .build()

    val api: TempoBackendService = Retrofit.Builder()
        .baseUrl(baseUrl)
        .client(okHttpClient)
        .addConverterFactory(GsonConverterFactory.create())
        .build()
        .create(TempoBackendService::class.java)

    suspend fun uploadVideoForAnalysis(
        videoFile: File?,
        userName: String = "user_1",
        lon: Double = -0.1328, // UCL Bloomsbury / Central London
        lat: Double = 51.5248
    ): StrokeAnalysisResponse {
        val videoPart = videoFile?.let {
            val reqFile = it.asRequestBody("video/mp4".toMediaTypeOrNull())
            MultipartBody.Part.createFormData("video", it.name, reqFile)
        }
        val textMedia = "text/plain".toMediaTypeOrNull()
        return api.analyzeStroke(
            video = videoPart,
            userName = userName.toRequestBody(textMedia),
            userLon = lon.toString().toRequestBody(textMedia),
            userLat = lat.toString().toRequestBody(textMedia)
        )
    }

    /**
     * Subscribes to `/pipeline/live-stream` so the Android Jetpack Compose UI updates
     * Sumanth's Apple Watch BPM & Fatigue ring in real time whenever a watch beat arrives in MongoDB.
     */
    fun observeLiveWatchAndSaintEvents(): Flow<JSONObject> = callbackFlow {
        val request = Request.Builder()
            .url("$baseUrl/pipeline/live-stream")
            .header("Accept", "text/event-stream")
            .build()

        val call = okHttpClient.newCall(request)
        Thread {
            try {
                val response: Response = call.execute()
                val reader = BufferedReader(InputStreamReader(response.body?.byteStream()))
                var line: String?
                while (reader.readLine().also { line = it } != null) {
                    val trimmed = line?.trim() ?: continue
                    if (trimmed.startsWith("data:")) {
                        val jsonStr = trimmed.removePrefix("data:").trim()
                        trySend(JSONObject(jsonStr))
                    }
                }
            } catch (_: Exception) {
            }
        }.start()

        awaitClose { call.cancel() }
    }
}
