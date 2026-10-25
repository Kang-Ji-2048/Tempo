package com.tempo.app.repository

import com.tempo.app.data.PlayerIdentity
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
    private val userProfileDao: UserProfileDao,
    private val identity: PlayerIdentity
) : UserProfileRepository {

    override fun getUserProfile(): Flow<UserProfileEntity?> {
        return userProfileDao.getUserProfile(identity.userId)
    }

    override suspend fun getUserProfileOnce(): UserProfileEntity? {
        return userProfileDao.getUserProfileOnce(identity.userId)
    }

    override suspend fun saveUserProfile(profile: UserProfileEntity) {
        val unifiedProfile = if (profile.userId.isBlank() || profile.userId != identity.userId) {
            profile.copy(userId = identity.userId)
        } else {
            profile
        }
        userProfileDao.saveUserProfile(unifiedProfile)
    }
}
