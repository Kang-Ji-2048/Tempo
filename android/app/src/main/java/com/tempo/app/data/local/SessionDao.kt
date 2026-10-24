package com.tempo.app.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

@Dao
interface SessionDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertSession(session: SessionEntity)

    @Update
    suspend fun updateSession(session: SessionEntity)

    @Query("SELECT * FROM sessions WHERE sessionId = :sessionId")
    suspend fun getSessionById(sessionId: String): SessionEntity?

    @Query("SELECT * FROM sessions WHERE sessionId = :sessionId")
    fun observeSessionById(sessionId: String): Flow<SessionEntity?>

    @Query("SELECT * FROM sessions ORDER BY createdAt DESC")
    fun observeAllSessions(): Flow<List<SessionEntity>>

    @Query("UPDATE sessions SET status = :status, updatedAt = :updatedAt WHERE sessionId = :sessionId")
    suspend fun updateStatus(sessionId: String, status: String, updatedAt: Long = System.currentTimeMillis())
    @Query("UPDATE sessions SET status = 'UPLOAD_FAILED', errorMessage = :message, updatedAt = :updatedAt WHERE sessionId = :sessionId")
    suspend fun markFailed(sessionId: String, message: String, updatedAt: Long = System.currentTimeMillis())

    @Query("SELECT * FROM sessions ORDER BY createdAt DESC LIMIT 1")
    fun observeLatestSession(): Flow<SessionEntity?>

    @Query("DELETE FROM sessions")
    suspend fun clearAll()
}
