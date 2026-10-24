package com.tempo.app.feature.ingestion.work

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.workDataOf
import java.util.concurrent.TimeUnit

object IngestionScheduler {

    /**
     * Enqueues a network-constrained, exponential-backoff WorkManager request to compress and upload
     * the captured practice clip. This guarantees survival across app closure and process death.
     */
    fun scheduleUpload(
        context: Context,
        sessionId: String,
        videoPath: String,
        sport: String = "badminton",
        strokeType: String = "overhead_clear",
        targetArchetype: String? = "Axelsen",
        userIntent: String? = "Working on steep angle and early high contact reach",
        userId: String,
        startMs: Long = 0L,
        endMs: Long = 0L,
        telemetryJson: String? = null
    ): androidx.work.Operation {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()

        val inputBuilder = androidx.work.Data.Builder()
            .putString(UploadWorker.KEY_SESSION_ID, sessionId)
            .putString(UploadWorker.KEY_VIDEO_PATH, videoPath)
            .putString(UploadWorker.KEY_SPORT, sport)
            .putString(UploadWorker.KEY_STROKE_TYPE, strokeType)
            .putString(UploadWorker.KEY_TARGET_ARCHETYPE, targetArchetype)
            .putString(UploadWorker.KEY_USER_INTENT, userIntent)
            .putString(UploadWorker.KEY_USER_ID, userId)
            .putLong(UploadWorker.KEY_START_MS, startMs)
            .putLong(UploadWorker.KEY_END_MS, endMs)

        if (!telemetryJson.isNullOrBlank()) {
            inputBuilder.putString(UploadWorker.KEY_TELEMETRY, telemetryJson)
        }

        val inputData = inputBuilder.build()

        val uploadRequest = OneTimeWorkRequestBuilder<UploadWorker>()
            .setConstraints(constraints)
            .setBackoffCriteria(
                BackoffPolicy.EXPONENTIAL,
                15,
                TimeUnit.SECONDS
            )
            .setInputData(inputData)
            .addTag("session_upload_$sessionId")
            .build()

        return WorkManager.getInstance(context).enqueueUniqueWork(
            "session_upload_$sessionId",
            ExistingWorkPolicy.KEEP,
            uploadRequest
        )

    }
}
