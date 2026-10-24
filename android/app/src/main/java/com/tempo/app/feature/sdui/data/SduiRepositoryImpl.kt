package com.tempo.app.feature.sdui.data

import com.tempo.app.feature.sdui.model.Widget
import com.tempo.app.feature.sdui.model.WidgetAction
import com.tempo.app.network.models.NetworkResult
import kotlinx.coroutines.CancellationException
import retrofit2.HttpException

class SduiRepositoryImpl(
    private val api: SduiApi,
    private val parser: WidgetParser,
) : SduiRepository {

    override suspend fun getFeed(sessionId: String): NetworkResult<List<Widget>> = safeCall {
        parser.parse(api.getFeed(sessionId).widgets)
    }

    override suspend fun postAction(sessionId: String, action: WidgetAction): NetworkResult<List<Widget>> =
        safeCall { parser.parse(api.postAction(action.toRequest(sessionId)).widgets) }

    private inline fun <T> safeCall(block: () -> T): NetworkResult<T> = try {
        NetworkResult.Success(block())
    } catch (e: CancellationException) {
        throw e
    } catch (e: HttpException) {
        NetworkResult.Error(exception = e, code = e.code(), message = e.message())
    } catch (e: Exception) {
        NetworkResult.Error(exception = e, message = e.message)
    }
}
