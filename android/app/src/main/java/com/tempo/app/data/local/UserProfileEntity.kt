package com.tempo.app.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "user_profile")
data class UserProfileEntity(
    @PrimaryKey
    val userId: String = "user_1",
    val sport: String,
    val level: String,
    val goal: String,
    val playstyle: String,
    val injuries: String,
    val targetArchetype: String,
    val permissionsGranted: Boolean = true,
    val updatedAt: Long = System.currentTimeMillis()
)
