package com.tempo.app.feature.biometrics

import com.tempo.app.BuildConfig
import com.tempo.app.feature.ingestion.model.BiometricPointDto
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.Request
import java.time.Instant
import java.time.OffsetDateTime
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class TelemetryRepository @Inject constructor(
    private val healthConnectManager: HealthConnectManager,
    private val okHttpClient: OkHttpClient,
    private val json: Json,
) {
    /**
     * Attempts to query the active teammate watch receiver stream first.
     * If inactive, unavailable, or empty, falls back to Health Connect.
     * Strictly returns emptyList() if no real sensor reading is found.
     */
    suspend fun getTelemetry(startMs: Long, endMs: Long): List<BiometricPointDto> = withContext(Dispatchers.IO) {
        val watchPoint = queryWatchReceiver(startMs, endMs)
        if (watchPoint != null) {
            return@withContext listOf(watchPoint)
        }

        // Fallback to Health Connect
        return@withContext healthConnectManager.readBiometrics(startMs, endMs)
    }

    private fun queryWatchReceiver(startMs: Long, endMs: Long): BiometricPointDto? {
        try {
            // Check baseUrl or localhost watch receiver endpoint (port 8000 or 8001 /reading)
            val watchUrl = BuildConfig.BASE_URL.trimEnd('/') + "/reading"
            val request = Request.Builder()
                .url(watchUrl)
                .get()
                .build()

            val response = okHttpClient.newCall(request).execute()
            if (!response.isSuccessful) return null
            val body = response.body?.string() ?: return null
            val root = json.parseToJsonElement(body).jsonObject
            val reading = root["reading"]?.jsonObject ?: return null

            val hrBpm = reading["heart_rate_bpm"]?.jsonPrimitive?.doubleOrNull ?: return null
            val sampledAtStr = reading["sampled_at"]?.jsonPrimitive?.content ?: return null
            val sampleMs = try {
                OffsetDateTime.parse(sampledAtStr).toInstant().toEpochMilli()
            } catch (_: Exception) {
                Instant.parse(sampledAtStr).toEpochMilli()
            }

            // Check if within bounds
            if (sampleMs in (startMs - 30_000)..(endMs + 30_000)) {
                return BiometricPointDto(
                    timestampMs = sampleMs,
                    heartRate = hrBpm.toInt(),
                    cadence = null,
                    activeEnergyBurned = null
                )
            }
        } catch (_: Exception) {
            // Watch receiver not running or inaccessible
        }
        return null
    }
}
