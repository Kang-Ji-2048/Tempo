package com.tempo.app

import com.tempo.app.data.PlayerIdentity
import com.tempo.app.data.local.SessionDao
import com.tempo.app.data.local.SessionEntity
import com.tempo.app.data.local.UserProfileDao
import com.tempo.app.data.local.UserProfileEntity
import com.tempo.app.network.MockTempoApi
import com.tempo.app.network.TempoApi
import com.tempo.app.network.models.AuthResponseDto
import com.tempo.app.network.models.LoginRequestDto
import com.tempo.app.network.models.NetworkResult
import com.tempo.app.network.models.RegisterRequestDto
import com.tempo.app.repository.AuthRepositoryImpl
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.runBlocking
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response

class FakePlayerIdentity : PlayerIdentity {
    override var userId: String = ""
    override var playerId: String = ""
    override var accessToken: String = ""
    override var email: String = ""
    override var displayName: String = ""
    override var sport: String? = null
    override var skill: String? = null

    override fun clear() {
        userId = ""
        playerId = ""
        accessToken = ""
        email = ""
        displayName = ""
        sport = null
        skill = null
    }
}

class FakeUserProfileDao : UserProfileDao {
    var cleared = false
    override fun getUserProfile(userId: String): Flow<UserProfileEntity?> = flowOf(null)
    override suspend fun getUserProfileOnce(userId: String): UserProfileEntity? = null
    override suspend fun saveUserProfile(profile: UserProfileEntity) {}
    override suspend fun clearAllProfiles() { cleared = true }
}

class FakeSessionDao : SessionDao {
    var cleared = false
    override suspend fun insertSession(session: SessionEntity) {}
    override suspend fun updateSession(session: SessionEntity) {}
    override suspend fun getSessionById(sessionId: String): SessionEntity? = null
    override fun observeSessionById(sessionId: String): Flow<SessionEntity?> = flowOf(null)
    override fun observeAllSessions(): Flow<List<SessionEntity>> = flowOf(emptyList())
    override suspend fun updateStatus(sessionId: String, status: String, updatedAt: Long) {}
    override suspend fun markFailed(sessionId: String, message: String, updatedAt: Long) {}
    override fun observeLatestSession(): Flow<SessionEntity?> = flowOf(null)
    override suspend fun getLatestSession(): SessionEntity? = null
    override suspend fun clearAll() { cleared = true }
}

class AuthRepositoryTest {

    @Test
    fun loginSuccessSavesIdentityAndReturnsToken() = runBlocking {
        val fakeIdentity = FakePlayerIdentity()
        val fakeProfileDao = FakeUserProfileDao()
        val fakeSessionDao = FakeSessionDao()
        val mockApi = object : TempoApi by MockTempoApi() {
            override suspend fun login(request: LoginRequestDto): AuthResponseDto {
                return AuthResponseDto(
                    userId = "user_test_123",
                    accessToken = "mock_jwt_token_abc",
                    displayName = "Test Athlete",
                    email = request.email
                )
            }
        }

        val repository = AuthRepositoryImpl(mockApi, fakeIdentity, fakeProfileDao, fakeSessionDao)
        val result = repository.login("athlete@tempo.app", "Secret123!")

        assertTrue(result is NetworkResult.Success<*>)
        val data = (result as NetworkResult.Success<AuthResponseDto>).data
        assertEquals("user_test_123", data.userId)
        assertEquals("mock_jwt_token_abc", data.accessToken)
        assertEquals("mock_jwt_token_abc", fakeIdentity.accessToken)
        assertEquals("user_test_123", fakeIdentity.userId)
        assertEquals("athlete@tempo.app", fakeIdentity.email)
        assertTrue(repository.isLoggedIn())
    }

    @Test
    fun loginFailureReturnsErrorAndLeavesIdentityEmpty() = runBlocking {
        val fakeIdentity = FakePlayerIdentity()
        val fakeProfileDao = FakeUserProfileDao()
        val fakeSessionDao = FakeSessionDao()
        val mockApi = object : TempoApi by MockTempoApi() {
            override suspend fun login(request: LoginRequestDto): AuthResponseDto {
                throw HttpException(
                    Response.error<Any>(
                        401,
                        """{"detail":"invalid_credentials"}""".toResponseBody("application/json".toMediaType())
                    )
                )
            }
        }

        val repository = AuthRepositoryImpl(mockApi, fakeIdentity, fakeProfileDao, fakeSessionDao)
        val result = repository.login("athlete@tempo.app", "WrongPassword")

        assertTrue(result is NetworkResult.Error)
        assertEquals(401, (result as NetworkResult.Error).code)
        assertEquals("", fakeIdentity.accessToken)
        assertFalse(repository.isLoggedIn())
    }

    @Test
    fun registerSuccessSavesIdentity() = runBlocking {
        val fakeIdentity = FakePlayerIdentity()
        val fakeProfileDao = FakeUserProfileDao()
        val fakeSessionDao = FakeSessionDao()
        val mockApi = object : TempoApi by MockTempoApi() {
            override suspend fun register(request: RegisterRequestDto): AuthResponseDto {
                return AuthResponseDto(
                    userId = "user_new_456",
                    accessToken = "new_user_token_xyz",
                    displayName = request.displayName,
                    email = request.email
                )
            }
        }

        val repository = AuthRepositoryImpl(mockApi, fakeIdentity, fakeProfileDao, fakeSessionDao)
        val result = repository.register("new@tempo.app", "Pass123456", "New Athlete")

        assertTrue(result is NetworkResult.Success<*>)
        assertEquals("user_new_456", fakeIdentity.userId)
        assertEquals("new_user_token_xyz", fakeIdentity.accessToken)
        assertEquals("new@tempo.app", fakeIdentity.email)
        assertEquals("New Athlete", fakeIdentity.displayName)
        assertTrue(repository.isLoggedIn())
    }

    @Test
    fun logoutClearsIdentityAndRoom() = runBlocking {
        val fakeIdentity = FakePlayerIdentity().apply {
            userId = "user_1"
            accessToken = "active_token"
            email = "demo@tempo.app"
        }
        val fakeProfileDao = FakeUserProfileDao()
        val fakeSessionDao = FakeSessionDao()
        val mockApi = MockTempoApi()

        val repository = AuthRepositoryImpl(mockApi, fakeIdentity, fakeProfileDao, fakeSessionDao)
        assertTrue(repository.isLoggedIn())

        repository.logout()
        assertFalse(repository.isLoggedIn())
        assertEquals("", fakeIdentity.accessToken)
        assertEquals("", fakeIdentity.userId)
        assertTrue(fakeProfileDao.cleared)
        assertTrue(fakeSessionDao.cleared)
    }
}
