package com.tempo.app.feature.saint

import com.tempo.app.network.models.NetworkResult
import kotlinx.coroutines.CancellationException
import retrofit2.HttpException
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import javax.inject.Inject
import javax.inject.Singleton

interface SaintApi {
    @POST("command") suspend fun command(@Body body: SaintCommand): SaintReply
    @GET("api/v1/saint/preferences/{user}") suspend fun preferences(@Path("user") user: String): SaintPreferenceRecord
    @PUT("api/v1/saint/preferences/{user}") suspend fun savePreferences(@Path("user") user: String, @Body body: SaintPreferences): SaintPreferenceRecord
    @POST("api/v1/saint/actions/decision") suspend fun decide(@Body body: SaintDecision): SaintActionRecord
    @GET("api/v1/saint/actions/{key}") suspend fun action(@Path("key") key: String): SaintActionRecord
}

interface SaintRepository {
    suspend fun command(user: String, text: String): NetworkResult<SaintReply>
    suspend fun preferences(user: String): NetworkResult<SaintPreferenceRecord>
    suspend fun savePreferences(user: String, preferences: SaintPreferences): NetworkResult<SaintPreferenceRecord>
    suspend fun decide(proposal: SaintProposal, approved: Boolean): NetworkResult<SaintActionRecord>
    suspend fun action(key: String): NetworkResult<SaintActionRecord>
}

@Singleton class SaintRepositoryImpl @Inject constructor(private val api: SaintApi): SaintRepository {
    private suspend fun <T> request(block: suspend () -> T): NetworkResult<T> = try {
        NetworkResult.Success(block())
    } catch (e: CancellationException) { throw e
    } catch (e: Exception) {
        val code = (e as? HttpException)?.code()
        NetworkResult.Error(e, code, when(code) {
            401, 403 -> "Sign in with this player's Tempo credential to use Saint."
            409 -> "This action has expired or already has a decision. Check its status or prepare a new proposal."
            400 -> "This proposal is no longer valid. Prepare a new one."
            410 -> "This proposal expired. Prepare a fresh proposal."
            422 -> "Check the request and preference fields, then try again."
            else -> "Saint's backend is unavailable. For an approval, check the action status before retrying."
        })
    }
    override suspend fun command(user: String, text: String) = request { api.command(SaintCommand(user,text)) }
    override suspend fun preferences(user: String) = request { api.preferences(user) }
    override suspend fun savePreferences(user: String, preferences: SaintPreferences) = request { api.savePreferences(user,preferences) }
    override suspend fun decide(proposal: SaintProposal, approved: Boolean) = request { api.decide(SaintDecision(proposal,approved)) }
    override suspend fun action(key: String) = request { api.action(key) }
}

/** Test double: fixtures are explicit and never claim an external service call. */
class MockSaintRepository(private var prefs: SaintPreferences = SaintPreferences()): SaintRepository {
    var reply = SaintReply("question", "Mock Saint: choose a court search or mock booking.")
    var decision: SaintActionRecord? = null
    override suspend fun command(user: String,text: String) = NetworkResult.Success(reply)
    override suspend fun preferences(user: String) = NetworkResult.Success(SaintPreferenceRecord(user,prefs,"test_memory"))
    override suspend fun savePreferences(user: String,preferences: SaintPreferences): NetworkResult<SaintPreferenceRecord> {
        prefs=preferences; return NetworkResult.Success(SaintPreferenceRecord(user,prefs,"test_memory"))
    }
    override suspend fun decide(proposal: SaintProposal,approved: Boolean): NetworkResult<SaintActionRecord> {
        val result=decision ?: SaintActionRecord(proposal.action.user,proposal.action,approved,if(approved) "executed_mock" else "declined")
        decision=result;return NetworkResult.Success(result)
    }
    override suspend fun action(key: String): NetworkResult<SaintActionRecord> = decision?.let { NetworkResult.Success(it) }
        ?: NetworkResult.Error(IllegalStateException("No test action"),404,"No test action")
}
