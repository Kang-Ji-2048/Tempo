package com.tempo.app.repository

import com.tempo.app.network.TempoApi
import com.tempo.app.network.models.NetworkResult
import com.tempo.app.network.models.OnboardingStepRequestDto
import com.tempo.app.network.models.OnboardingStepResponseDto
import javax.inject.Inject
import javax.inject.Singleton

interface OnboardingRepository {
    suspend fun getNextStep(request: OnboardingStepRequestDto): NetworkResult<OnboardingStepResponseDto>
}

@Singleton
class OnboardingRepositoryImpl @Inject constructor(
    private val api: TempoApi
) : OnboardingRepository {

    override suspend fun getNextStep(request: OnboardingStepRequestDto): NetworkResult<OnboardingStepResponseDto> {
        return try {
            val response = api.nextOnboardingStep(request)
            NetworkResult.Success(response)
        } catch (e: Exception) {
            NetworkResult.Error(exception = e, message = e.message)
        }
    }
}
