package com.tempo.app.di

import android.content.Context
import androidx.room.Room
import com.tempo.app.data.local.SessionDao
import com.tempo.app.data.local.TempoDatabase
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {

    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): TempoDatabase {
        return Room.databaseBuilder(
            context,
            TempoDatabase::class.java,
            "tempo.db"
        ).fallbackToDestructiveMigration().build()
    }

    @Provides
    fun provideSessionDao(database: TempoDatabase): SessionDao {
        return database.sessionDao()
    }

    @Provides
    fun provideUserProfileDao(database: TempoDatabase): com.tempo.app.data.local.UserProfileDao {
        return database.userProfileDao()
    }
}
