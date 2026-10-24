package com.tempo.app.data.local

import androidx.room.Database
import androidx.room.RoomDatabase

@Database(entities = [SessionEntity::class, UserProfileEntity::class], version = 2, exportSchema = false)
abstract class TempoDatabase : RoomDatabase() {
    abstract fun sessionDao(): SessionDao
    abstract fun userProfileDao(): UserProfileDao
}
