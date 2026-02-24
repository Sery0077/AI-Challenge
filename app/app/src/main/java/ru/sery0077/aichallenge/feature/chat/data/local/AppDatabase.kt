package ru.sery0077.aichallenge.feature.chat.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import ru.sery0077.aichallenge.feature.chat.data.local.dao.ChatMessageDao
import ru.sery0077.aichallenge.feature.chat.data.local.dao.ChatSessionDao
import ru.sery0077.aichallenge.feature.chat.data.local.entity.ChatMessageEntity
import ru.sery0077.aichallenge.feature.chat.data.local.entity.ChatSessionEntity

@Database(
    entities = [
        ChatSessionEntity::class,
        ChatMessageEntity::class,
    ],
    version = 1,
    exportSchema = false,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun chatSessionDao(): ChatSessionDao
    abstract fun chatMessageDao(): ChatMessageDao
}
