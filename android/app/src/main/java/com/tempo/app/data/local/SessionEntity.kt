package com.tempo.app.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "sessions")
data class SessionEntity(
    @PrimaryKey
    val sessionId: String,
    val userId: String,
    val sport: String,
    val strokeType: String,
    val targetArchetype: String? = null,
    val userIntent: String? = null,
    val videoPath: String,
    val status: String, // UPLOADING, PENDING, ANALYZING, COMPLETED, FAILED
    val overallScore: Int? = null,
    val primaryFlaw: String? = null,
    val errorMessage: String? = null,
    val createdAt: Long = System.currentTimeMillis(),
    val updatedAt: Long = System.currentTimeMillis()
)
