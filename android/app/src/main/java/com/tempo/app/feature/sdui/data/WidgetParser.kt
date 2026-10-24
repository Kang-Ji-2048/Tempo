package com.tempo.app.feature.sdui.data

import com.tempo.app.feature.sdui.model.CapturePromptWidget
import com.tempo.app.feature.sdui.model.CheckInScheduleWidget
import com.tempo.app.feature.sdui.model.ChoiceWidget
import com.tempo.app.feature.sdui.model.ConceptQuizWidget
import com.tempo.app.feature.sdui.model.DrillCardWidget
import com.tempo.app.feature.sdui.model.PathProgressWidget
import com.tempo.app.feature.sdui.model.QuestionWidget
import com.tempo.app.feature.sdui.model.UnknownWidget
import com.tempo.app.feature.sdui.model.Widget
import kotlinx.serialization.DeserializationStrategy
import kotlinx.serialization.PolymorphicSerializer
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.modules.SerializersModule
import kotlinx.serialization.modules.polymorphic
import kotlinx.serialization.modules.subclass
import javax.inject.Inject
import javax.inject.Singleton

const val WIDGET_DISCRIMINATOR = "widget_type"

/** Polymorphic module: known subclasses + a default that maps anything else to [UnknownWidget]. */
val sduiSerializersModule = SerializersModule {
    polymorphic(Widget::class) {
        subclass(PathProgressWidget::class)
        subclass(DrillCardWidget::class)
        subclass(ConceptQuizWidget::class)
        subclass(CheckInScheduleWidget::class)
        subclass(QuestionWidget::class)
        subclass(ChoiceWidget::class)
        subclass(CapturePromptWidget::class)
        defaultDeserializer { type -> UnknownWidgetDeserializer(type) }
    }
}

val SduiJson: Json = Json {
    classDiscriminator = WIDGET_DISCRIMINATOR
    serializersModule = sduiSerializersModule
    ignoreUnknownKeys = true
    coerceInputValues = true
    explicitNulls = false
    isLenient = true
}

/** Captures the raw JSON of an unrecognised widget instead of throwing. */
private class UnknownWidgetDeserializer(private val type: String?) : DeserializationStrategy<Widget> {
    override val descriptor: SerialDescriptor = JsonObject.serializer().descriptor

    override fun deserialize(decoder: Decoder): Widget {
        val raw = (decoder as? JsonDecoder)?.decodeJsonElement() as? JsonObject ?: JsonObject(emptyMap())
        return UnknownWidget(widgetType = type ?: "missing", raw = raw)
    }
}

/**
 * Turns raw SDUI JSON into [Widget]s. Each element is decoded in isolation, so a
 * single bad widget (unknown type, missing field, wrong shape) degrades to
 * [UnknownWidget] without affecting its neighbours.
 */
@Singleton
class WidgetParser @Inject constructor() {

    private val json: Json = SduiJson

    fun parse(elements: List<JsonElement>): List<Widget> = elements.map(::parseOne)

    fun parseFeed(rawJson: String): List<Widget> {
        val root = runCatching { json.parseToJsonElement(rawJson) }.getOrNull() ?: return emptyList()
        val array = when (root) {
            is JsonArray -> root
            is JsonObject -> root["widgets"] as? JsonArray ?: JsonArray(emptyList())
            else -> JsonArray(emptyList())
        }
        return parse(array)
    }

    fun parseOne(element: JsonElement): Widget {
        val obj = element as? JsonObject ?: return UnknownWidget("not_an_object")
        return try {
            json.decodeFromJsonElement(PolymorphicSerializer(Widget::class), obj)
        } catch (e: Exception) {
            val type = (obj[WIDGET_DISCRIMINATOR] as? JsonPrimitive)?.contentOrNull ?: "missing"
            UnknownWidget(widgetType = type, raw = obj)
        }
    }
}
