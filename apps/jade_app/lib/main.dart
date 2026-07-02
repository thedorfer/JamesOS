import 'package:flutter/material.dart';
import 'screens/chat_screen.dart';

void main() => runApp(const JadeApp());

class JadeApp extends StatelessWidget {
  const JadeApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Jade',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark(useMaterial3: true).copyWith(
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.tealAccent,
          brightness: Brightness.dark,
        ),
      ),
      home: const ChatScreen(),
    );
  }
}
