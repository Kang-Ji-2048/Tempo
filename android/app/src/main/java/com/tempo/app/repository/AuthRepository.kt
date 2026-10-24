package com.tempo.app.repository

import com.tempo.app.data.PlayerIdentity
import com.tempo.app.data.local.SessionDao
import com.tempo.app.data.local.UserProfileDao
import com.tempo.app.network.TempoApi
import com.tempo.app.network.models.AuthResponseDto
import com.tempo.app.network.models.LoginRequestDto
import com.tempo.app.network.models.NetworkResult
import com.tempo.app.network.models.RegisterRequestDto
import com.tempo.app.network.models.UserProfileDto
import retrofit2.HttpException
import javax.inject.Inject
import javax.inject.Singleton

interface AuthRepository {
    suspend fun register(email: String, password: String, displayName: String): NetworkResult<AuthResponseDto>
    suspend fun login(email: String, password: String): NetworkResult<AuthResponseDto>
    suspend fun getMe(): NetworkResult<UserProfileDto>
    suspend fun logout(): NetworkResult<Unit>
    fun isLoggedIn(): Boolean
}

@Singleton
class AuthRepositoryImpl @Inject constructor(
    private val tempoApi: TempoApi,
    private val identity: PlayerIdentity,
    private val userProfileDao: UserProfileDao,
    private val sessionDao: SessionDao
) : AuthRepository {

    override fun isLoggedIn(): Boolean {
        return identity.accessToken.isNotBlank() && identity.userId.isNotBlank()
    }

    override suspend fun register(
        email: String,
        password: String,
        displayName: String
    ): NetworkResult<AuthResponseDto> {
        return try {
            val response = tempoApi.register(RegisterRequestDto(email, password, displayName))
            identity.userId = response.userId
            identity.accessToken = response.accessToken
            identity.email = email
            identity.displayName = response.displayName
            NetworkResult.Success(response)
        } catch (e: Exception) {
            val code = (e as? HttpException)?.code()
            val msg = when (code) {
                409 -> "An account with this email already exists."
                else -> e.localizedMessage ?: e.message ?: "Registration failed."
            }
            NetworkResult.Error(exception = e, code = code, message = msg)
        }
    }

    override suspend fun login(email: String, password: String): NetworkResult<AuthResponseDto> {
        return try {
            val response = tempoApi.login(LoginRequestDto(email, password))
            identity.userId = response.userId
            identity.accessToken = response.accessToken
            identity.email = email
            identity.displayName = response.displayName
            NetworkResult.Success(response)
        } catch (e: Exception) {
            val code = (e as? HttpException)?.code()
            val msg = when (code) {
                401 -> "Invalid email or password."
                429 -> "Too many failed login attempts. Please wait 10 minutes before retrying."
                else -> e.localizedMessage ?: e.message ?: "Sign in failed."
            }
            NetworkResult.Error(exception = e, code = code, message = msg)
        }
    }

    override suspend fun getMe(): NetworkResult<UserProfileDto> {
        return try {
            val profile = tempoApi.getMe()
            identity.sport = profile.sport
            NetworkResult.Success(profile)
        } catch (e: Exception) {
            val code = (e as? HttpException)?.code()
            NetworkResult.Error(exception = e, code = code, message = e.message)
        }
    }

    override suspend fun logout(): NetworkResult<Unit> {
        return try {
            try {
                tempoApi.logout()
            } catch (_: Exception) {}
            identity.clear()
            userProfileDao.clearAllProfiles()
            sessionDao.clearAll()
            NetworkResult.Success(Unit)
        } catch (e: Exception) {
            identity.clear()
            NetworkResult.Success(Unit)
        }
    }
}
