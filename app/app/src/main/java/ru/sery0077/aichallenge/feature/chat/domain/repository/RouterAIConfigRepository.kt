package ru.sery0077.aichallenge.feature.chat.domain.repository

interface RouterAIConfigRepository {
    fun getBaseUrl(): String
    fun getModel(): String
    fun getApiKey(): String
    fun updateBaseUrl(value: String)
    fun updateModel(value: String)
    fun updateApiKey(value: String)
}
