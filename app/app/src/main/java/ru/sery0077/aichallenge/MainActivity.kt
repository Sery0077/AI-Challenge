package ru.sery0077.aichallenge

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import ru.sery0077.aichallenge.presentation.MainScreen
import ru.sery0077.aichallenge.ui.theme.AIChallengeTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            AIChallengeTheme {
                MainScreen()
            }
        }
    }
}
