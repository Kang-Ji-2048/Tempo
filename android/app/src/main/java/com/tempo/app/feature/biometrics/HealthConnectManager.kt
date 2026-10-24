package com.tempo.app.feature.biometrics

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.ActiveCaloriesBurnedRecord
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import com.tempo.app.feature.ingestion.model.BiometricPointDto
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton

typealias BiometricDataPoint = BiometricPointDto

/**
 * Manages Health Connect integration for querying heart rate and active calories.
 * Strictly adheres to returning an empty list when no hardware/permission/sensor records are present.
 */
@Singleton
class HealthConnectManager @Inject constructor(
    @ApplicationContext private val context: Context
) {
    private val client: HealthConnectClient? by lazy {
        if (isAvailable()) {
            try {
                HealthConnectClient.getOrCreate(context)
            } catch (_: Exception) {
                null
            }
        } else {
            null
        }
    }

    val permissions: Set<String> = setOf(
        HealthPermission.getReadPermission(HeartRateRecord::class),
        HealthPermission.getReadPermission(ActiveCaloriesBurnedRecord::class)
    )

    fun isAvailable(): Boolean {
        return try {
            HealthConnectClient.getSdkStatus(context) == HealthConnectClient.SDK_AVAILABLE
        } catch (_: Exception) {
            false
        }
    }

    suspend fun hasPermissions(): Boolean = withContext(Dispatchers.IO) {
        val hc = client ?: return@withContext false
        try {
            val granted = hc.permissionController.getGrantedPermissions()
            granted.containsAll(permissions)
        } catch (_: Exception) {
            false
        }
    }

    /**
     * Reads heart rate and active calories records strictly within [startMs, endMs].
     * Never fabricates mock telemetry. Returns empty list if no data exists.
     */
    suspend fun readBiometrics(startMs: Long, endMs: Long): List<BiometricPointDto> = withContext(Dispatchers.IO) {
        val hc = client ?: return@withContext emptyList()
        if (startMs <= 0 || endMs <= startMs) return@withContext emptyList()

        try {
            if (!hasPermissions()) {
                return@withContext emptyList()
            }

            val startInstant = Instant.ofEpochMilli(startMs)
            val endInstant = Instant.ofEpochMilli(endMs)

            val hrRequest = ReadRecordsRequest(
                recordType = HeartRateRecord::class,
                timeRangeFilter = TimeRangeFilter.between(startInstant, endInstant)
            )
            val hrResponse = hc.readRecords(hrRequest)

            val caloriesRequest = ReadRecordsRequest(
                recordType = ActiveCaloriesBurnedRecord::class,
                timeRangeFilter = TimeRangeFilter.between(startInstant, endInstant)
            )
            val caloriesResponse = hc.readRecords(caloriesRequest)
            val totalActiveCalories = caloriesResponse.records.sumOf { it.energy.inKilocalories }

            val points = mutableListOf<BiometricPointDto>()
            for (record in hrResponse.records) {
                for (sample in record.samples) {
                    val sampleTimeMs = sample.time.toEpochMilli()
                    points.add(
                        BiometricPointDto(
                            timestampMs = sampleTimeMs,
                            heartRate = sample.beatsPerMinute.toInt(),
                            cadence = null,
                            activeEnergyBurned = if (totalActiveCalories > 0.0) totalActiveCalories else null
                        )
                    )
                }
            }

            points.sortBy { it.timestampMs }
            points
        } catch (_: Exception) {
            emptyList()
        }
    }
}
