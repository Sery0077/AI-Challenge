package ru.sery0077.aichallenge.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

@Composable
fun AppScaffold(
    topBar: @Composable () -> Unit = {},
    content: @Composable (padding: androidx.compose.foundation.layout.PaddingValues) -> Unit,
) {
    Scaffold(
        topBar = {
            Box(modifier = Modifier.windowInsetsPadding(WindowInsets.statusBars)) {
                topBar()
            }
        },
        contentWindowInsets = WindowInsets.safeDrawing,
        content = content,
    )
}
