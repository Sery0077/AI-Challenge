package ru.sery0077.aichallenge.data.repository

import ru.sery0077.aichallenge.BuildConfig
import ru.sery0077.aichallenge.domain.repository.RouterAIConfigRepository

class RouterAIConfigRepositoryImpl : RouterAIConfigRepository {
    private var baseUrl: String = "https://routerai.ru/api/v1/"
    private var model: String = "deepseek/deepseek-v3.2"
    private var apiKey: String = BuildConfig.ROUTERAI_API_KEY

    override fun getBaseUrl(): String = baseUrl
    override fun getModel(): String = model
    override fun getApiKey(): String = apiKey

    override fun updateBaseUrl(value: String) {
        baseUrl = value
    }

    override fun updateModel(value: String) {
        model = value
    }

    override fun updateApiKey(value: String) {
        apiKey = value
    }
}
