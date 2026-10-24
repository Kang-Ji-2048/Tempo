package com.tempo.app.repository

import com.tempo.app.data.local.UserProfileDao
import com.tempo.app.data.local.UserProfileEntity
import kotlinx.coroutines.flow.Flow
import javax.inject.Inject
import javax.inject.Singleton

interface UserProfileRepository {
    fun getUserProfile(): Flow<UserProfileEntity?>
    suspend fun getUserProfileOnce(): UserProfileEntity?
    suspend fun saveUserProfile(profile: UserProfileEntity)
}

@Singleton
class UserProfileRepositoryImpl @Inject constructor(
    private val userProfileDao: UserProfileDao
) : UserProfileRepository {

    override fun getUserProfile(): Flow<UserProfileEntity?> {
        return userProfileDao.getUserProfile()
    }

    override suspend fun getUserProfileOnce(): UserProfileEntity? {
        return userProfileDao.getUserProfileOnce()
    }

    override suspend fun saveUserProfile(profile: UserProfileEntity) {
        userProfileDao.saveUserProfile(profile)
    }
}
