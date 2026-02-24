package ru.sery0077.aichallenge.feature.chat.domain.repository

import kotlinx.coroutines.flow.Flow
import ru.sery0077.aichallenge.feature.chat.domain.model.ChatMessage
import ru.sery0077.aichallenge.feature.chat.domain.model.RequestSettings

interface RouterAIRepository {
    fun streamChat(messages: List<ChatMessage>, settings: RequestSettings): Flow<String>
}
