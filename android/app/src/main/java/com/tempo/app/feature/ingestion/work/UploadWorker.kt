package com.tempo.app.feature.ingestion.work

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import com.tempo.app.data.local.SessionDao
import com.tempo.app.data.local.SessionEntity
import com.tempo.app.feature.ingestion.Media3VideoCompressor
import com.tempo.app.feature.ingestion.model.SessionIngestMetadata
import com.tempo.app.network.TempoApi
import dagger.hilt.EntryPoint
import dagger.hilt.InstallIn
import dagger.hilt.android.EntryPointAccessors
import dagger.hilt.components.SingletonComponent
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
import kotlinx.coroutines.CancellationException
import retrofit2.HttpException
import java.io.IOException
import java.util.UUID

@EntryPoint
@InstallIn(SingletonComponent::class)
interface UploadWorkerEntryPoint {
    fun tempoApi(): TempoApi
    fun sessionDao(): SessionDao
    fun json(): Json
}

/**
 * Robust background worker responsible for:
 * 1. Persisting the local session record in Room.
 * 2. Compressing recorded video to 720p using Media3 Transformer.
 * 3. Asynchronously uploading multipart metadata JSON & 720p video to FastAPI.
 * 4. Updating Room with the final backend session status.
 *
 * Configured with network constraints and exponential backoff so that it survives app kills/process death.
 */
class UploadWorker(
    appContext: Context,
    workerParams: WorkerParameters
) : CoroutineWorker(appContext, workerParams) {

    override suspend fun doWork(): Result {
        val sessionId = inputData.getString(KEY_SESSION_ID) ?: UUID.randomUUID().toString()
        val videoPath = inputData.getString(KEY_VIDEO_PATH)
            ?: return Result.failure(workDataOf("error" to "Missing video_path input"))
        val userId = inputData.getString(KEY_USER_ID)?.trim()?.takeIf { it.isNotBlank() }
            ?: return Result.failure(workDataOf("error" to "Missing player ID"))
        val sport = inputData.getString(KEY_SPORT) ?: "badminton"
        val strokeType = inputData.getString(KEY_STROKE_TYPE) ?: "overhead_clear"
        val targetArchetype = inputData.getString(KEY_TARGET_ARCHETYPE) ?: "Axelsen"
        val userIntent = inputData.getString(KEY_USER_INTENT)
            ?: "Working on steep angle and early high contact reach"

        val entryPoint = EntryPointAccessors.fromApplication(
            applicationContext,
            UploadWorkerEntryPoint::class.java
        )
        val tempoApi = entryPoint.tempoApi()
        val sessionDao = entryPoint.sessionDao()
        val json = entryPoint.json()

        // 1. Initial Room persistence
        val initialEntity = SessionEntity(
            sessionId = sessionId,
            userId = userId,
            sport = sport,
            strokeType = strokeType,
            targetArchetype = targetArchetype,
            userIntent = userIntent,
            videoPath = videoPath,
            status = "UPLOADING",
            createdAt = System.currentTimeMillis(),
            updatedAt = System.currentTimeMillis()
        )
        val existing = sessionDao.getSessionById(sessionId)
        if (existing?.status in listOf("PENDING", "ANALYZING", "COMPLETED")) {
            return Result.success(workDataOf(KEY_SESSION_ID to sessionId))
        }
        sessionDao.insertSession(initialEntity)

        val inputFile = File(videoPath)
        if (!inputFile.exists() || inputFile.length() == 0L) {
            sessionDao.markFailed(sessionId, "Input video file does not exist or is empty")
            return Result.failure(workDataOf("error" to "Input video file does not exist or is empty"))
        }

        // 2. Compress to 720p using Media3 Transformer
        val compressedFile = File(applicationContext.cacheDir, "compressed_${sessionId}.mp4")
        val selection = File(applicationContext.cacheDir, "upload_source_${sessionId}.txt")
        val selected = selection.takeIf { it.exists() }?.readText()?.let(::File)?.takeIf { it.exists() && it.length() > 0L }
        val fileToUpload = selected ?: try {
            if (compressedFile.exists() && compressedFile.length() > 0L) compressedFile else Media3VideoCompressor.compressTo720p(
                context = applicationContext,
                inputFile = inputFile,
                outputFile = compressedFile
            )
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            // Graceful fallback to original file if compression fails
            inputFile
        }

        selection.writeText(fileToUpload.absolutePath)

        // No Health Connect collector is connected yet. Empty telemetry explicitly
        // asks the server for this player's paired Watch reading; never invent samples.
        // 4. Construct multipart metadata
        val metadata = SessionIngestMetadata(
            sessionId = sessionId,
            userId = userId,
            sport = sport,
            strokeType = strokeType,
            targetArchetype = targetArchetype,
            userIntent = userIntent,
            telemetry = emptyList()
        )

        val metadataJson = json.encodeToString(SessionIngestMetadata.serializer(), metadata)
        val metadataBody = metadataJson.toRequestBody("application/json".toMediaTypeOrNull())

        val videoRequestBody = fileToUpload.asRequestBody("video/mp4".toMediaTypeOrNull())
        val videoPart = MultipartBody.Part.createFormData(
            "video",
            fileToUpload.name,
            videoRequestBody
        )

        // 5. POST to FastAPI backend
        return try {
            val response = tempoApi.ingestSession(
                metadata = metadataBody,
                video = videoPart
            )

            val backendSessionId = response.sessionId.ifBlank { sessionId }
            if (backendSessionId != sessionId) {
                sessionDao.markFailed(sessionId, "Server returned a different session ID. Update the backend.")
                return Result.failure(workDataOf("error" to "Session ID mismatch"))
            }
            sessionDao.updateStatus(sessionId, response.status)

            Result.success(workDataOf(KEY_SESSION_ID to backendSessionId))
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            val retryable = e is IOException || (e is HttpException && (e.code() >= 500 || e.code() == 429))
            if (retryable && runAttemptCount < 3) {
                Result.retry()
            } else {
                sessionDao.markFailed(sessionId, e.message ?: "Upload failed")
                Result.failure(workDataOf("error" to (e.message ?: "Upload failed")))
            }
        }
    }

    companion object {
        const val KEY_SESSION_ID = "session_id"
        const val KEY_VIDEO_PATH = "video_path"
        const val KEY_USER_ID = "user_id"
        const val KEY_SPORT = "sport"
        const val KEY_STROKE_TYPE = "stroke_type"
        const val KEY_TARGET_ARCHETYPE = "target_archetype"
        const val KEY_USER_INTENT = "user_intent"
    }
}
